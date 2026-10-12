import os, sqlite3, secrets, time, json, re
from pathlib import Path
from urllib.parse import urlparse
import bcrypt, httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from .inventory import GROUPS

DB = "/data/homelab.sqlite3"
SECRET = os.environ.get("SESSION_SECRET", "")
ADMIN = os.environ.get("ADMIN_USERNAME", "admin")
PASSWORD = os.environ.get("ADMIN_PASSWORD", "")
ORIGIN = os.environ.get("PUBLIC_ORIGIN", "").rstrip("/")
SECURE = os.environ.get("COOKIE_SECURE", "true").lower() == "true"
if len(SECRET) < 32 or len(PASSWORD) < 16 or not ORIGIN.startswith(("https://", "http://")):
    raise RuntimeError("Set SESSION_SECRET (>=32 chars), ADMIN_PASSWORD (>=16 chars), and PUBLIC_ORIGIN")
serializer = URLSafeTimedSerializer(SECRET, salt="codex-session-v1")
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=Path(__file__).parent/"static"), name="static")
failures = {}

def connect():
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    return db

@app.on_event("startup")
def init():
    with connect() as db:
        db.execute("CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password_hash TEXT NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS links (name TEXT PRIMARY KEY, url TEXT NOT NULL)")
        if not db.execute("SELECT 1 FROM users WHERE username=?", (ADMIN,)).fetchone():
            db.execute("INSERT INTO users VALUES (?,?)", (ADMIN, bcrypt.hashpw(PASSWORD.encode(), bcrypt.gensalt()).decode()))

def user(request):
    cookie = request.cookies.get("session", "")
    try:
        value = serializer.loads(cookie, max_age=8*3600)
        return value.get("u") if isinstance(value, dict) else None
    except (BadSignature, SignatureExpired):
        return None

def require(request):
    u = user(request)
    if not u: raise HTTPException(401, "Authentication required")
    return u

def csrf(request):
    # Same-origin check on all modifying routes, plus CSRF header matching session token
    if request.headers.get("origin", "").rstrip("/") != ORIGIN:
        raise HTTPException(403, "Origin mismatch")
    token = request.cookies.get("csrf", "")
    if not token or not secrets.compare_digest(request.headers.get("x-csrf-token",""), token):
        raise HTTPException(403, "CSRF verification failed")

@app.get("/", response_class=HTMLResponse)
def home():
    return FileResponse(Path(__file__).parent/"static"/"index.html")

@app.get("/api/me")
def me(request:Request):
    return {"username":user(request)}

@app.post("/api/login")
async def login(request:Request):
    # Origin protection for login; no CSRF cookie needed before authentication
    if request.headers.get("origin","").rstrip("/") != ORIGIN:
        raise HTTPException(403,"Origin mismatch")
    ip = request.client.host if request.client else "unknown"
    now = time.monotonic()
    recent = [t for t in failures.get(ip,[]) if now-t<300]
    if len(recent)>=8: raise HTTPException(429,"Too many attempts; try again later")
    body = await request.json()
    username, password = str(body.get("username","")),str(body.get("password",""))
    with connect() as db:
        row = db.execute("SELECT password_hash FROM users WHERE username=?",(username,)).fetchone()
    if not row or not bcrypt.checkpw(password.encode(),row["password_hash"].encode()):
        failures[ip] = recent+[now]
        raise HTTPException(401,"Invalid credentials")
    failures.pop(ip,None)
    response=JSONResponse({"ok":True})
    response.set_cookie("session",serializer.dumps({"u":username}),httponly=True,secure=SECURE,samesite="lax",max_age=28800,path="/")
    response.set_cookie("csrf",secrets.token_urlsafe(32),httponly=False,secure=SECURE,samesite="lax",max_age=28800,path="/")
    return response

@app.post("/api/logout")
def logout(request:Request):
    require(request);csrf(request)
    r=JSONResponse({"ok":True})
    r.delete_cookie("session",path="/");r.delete_cookie("csrf",path="/")
    return r

@app.get("/api/inventory")
def inventory(request:Request):
    require(request)
    with connect() as db:
        links={r["name"]:r["url"] for r in db.execute("SELECT name,url FROM links")}
    return {"groups":GROUPS,"links":links}

@app.put("/api/links")
async def save_link(request:Request):
    require(request);csrf(request)
    body=await request.json()
    name,url=str(body.get("name","")).strip(),str(body.get("url","")).strip()
    allowed={item for group in GROUPS for item in group["items"]}
    if name not in allowed: raise HTTPException(400,"Unknown service")
    if len(url)>2048: raise HTTPException(400,"URL too long")
    if url:
        parsed=urlparse(url)
        if parsed.scheme not in ("https","http") or not parsed.hostname or parsed.username or parsed.password:
            raise HTTPException(400,"Use a valid http(s) URL without embedded credentials")
    with connect() as db:
        if url: db.execute("INSERT OR REPLACE INTO links VALUES (?,?)",(name,url))
        else: db.execute("DELETE FROM links WHERE name=?",(name,))
    return {"ok":True}

@app.get("/api/proxmox")
async def proxmox(request:Request):
    require(request)
    url=os.environ.get("PVE_URL","").rstrip("/")
    token_id=os.environ.get("PVE_TOKEN_ID","")
    token_secret=os.environ.get("PVE_TOKEN_SECRET","")
    if not all((url,token_id,token_secret)):
        return {"configured":False,"nodes":[],"guests":[]}
    verify=os.environ.get("PVE_CA_BUNDLE") or True
    try:
        async with httpx.AsyncClient(verify=verify,timeout=8) as client:
            response=await client.get(url+"/api2/json/cluster/resources",
                headers={"Authorization":f"PVEAPIToken={token_id}={token_secret}"},
                params={"type":"vm"})
            response.raise_for_status()
            guests=[{"name":v.get("name") or str(v.get("vmid")),
                     "vmid":v.get("vmid"),"node":v.get("node"),"kind":v.get("type"),
                     "status":v.get("status"),"cpu":v.get("cpu",0),
                     "mem":v.get("mem",0),"maxmem":v.get("maxmem",0)}
                    for v in response.json().get("data",[])]
            node_resp=await client.get(url+"/api2/json/cluster/resources",
                headers={"Authorization":f"PVEAPIToken={token_id}={token_secret}"},
                params={"type":"node"})
            node_resp.raise_for_status()
            nodes=[{"name":v.get("node"),"status":v.get("status"),"cpu":v.get("cpu",0),
                    "mem":v.get("mem",0),"maxmem":v.get("maxmem",0)}
                   for v in node_resp.json().get("data",[])]
        return {"configured":True,"nodes":nodes,"guests":guests}
    except (httpx.HTTPError,ValueError) as e:
        return JSONResponse({"configured":True,"error":"Unable to contact Proxmox API. Check URL, TLS trust, token and connectivity."},status_code=502)

@app.get("/health")
def health():
    return {"status":"ok"}
