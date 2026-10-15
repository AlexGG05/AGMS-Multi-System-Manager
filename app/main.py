import os, sqlite3, secrets, time, json, re, asyncio, logging
from pathlib import Path
from urllib.parse import urlparse
import bcrypt, httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from .inventory import GROUPS
from .arcane import get_arcane, manage_container
from . import integrations, workspaces, web_proxy, features, operations, security_keys, push_channels

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
        workspaces.install(db)

@app.on_event("startup")
async def start_notification_worker():
    async def retry_emails():
        while True:
            await asyncio.sleep(features.EMAIL_POLL_INTERVAL)
            try:
                await asyncio.to_thread(push_channels.deliver,connect)
            except Exception as exc:
                logging.getLogger(__name__).warning("Background work deferred: %s",type(exc).__name__)
            if os.getenv("SMTP_PASSWORD"):
                try:
                    await asyncio.to_thread(features.deliver_pending,connect)
                except sqlite3.Error as exc:
                    logging.getLogger(__name__).warning("Notification email retry deferred: %s",type(exc).__name__)
    async def expiry_checks():
        while True:
            await asyncio.sleep(60)
            try:await asyncio.to_thread(operations.check_due_watches,connect)
            except Exception as exc:logging.getLogger(__name__).warning('Expiry checks deferred: %s',type(exc).__name__)
    app.state.expiry_worker=asyncio.create_task(expiry_checks())
    app.state.notification_worker=asyncio.create_task(retry_emails())

@app.on_event("shutdown")
async def stop_notification_worker():
    for name in ('notification_worker','expiry_worker'):
        worker=getattr(app.state,name,None)
        if worker:
            worker.cancel()
            try:await worker
            except asyncio.CancelledError:pass

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

@app.middleware("http")
async def bookstack_proxy_identity(request: Request, call_next):
    response=await call_next(request)
    if request.url.path.startswith(('/api/account/','/api/auth/','/api/monitoring','/api/admin/audit')):response.headers['Cache-Control']='no-store'
    return response

app.include_router(web_proxy.setup(connect, require))

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    username = user(request)
    page = "workspaces.html" if username else "index.html"
    return FileResponse(Path(__file__).parent/"static"/page, headers={"Cache-Control":"no-store, no-cache, must-revalidate","Pragma":"no-cache","Vary":"Cookie"})

@app.get("/webui/{wsid}/{itemid}/", response_class=HTMLResponse)
def webui_home(request:Request,wsid:str,itemid:str):
    username=user(request)
    if username:
        with connect() as db:
            row=db.execute("SELECT m.role,n.min_role,n.url FROM workspace_members m JOIN workspace_navigation n ON n.workspace_id=m.workspace_id WHERE m.workspace_id=? AND m.username=? AND n.id=?",(wsid,username,itemid)).fetchone()
        order={"viewer":0,"editor":1,"owner":2}
        if not row or not row["url"] or order.get(row["role"],-1)<order.get(row["min_role"],99):
            raise HTTPException(404,"WebUI not found")
    return home(request)

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
        # Login names are public aliases only; never fall back to the internal users.username key.
        resolved=db.execute("""SELECT username FROM account_profiles
            WHERE lower(email)=lower(?) OR (display_name!='' AND lower(display_name)=lower(?))
            LIMIT 1""",(username.strip(),username.strip())).fetchone()
        username=resolved["username"] if resolved else ""
        row = db.execute("SELECT password_hash FROM users WHERE username=?",(username,)).fetchone()
    valid=False
    if row:
        try:valid=bcrypt.checkpw(password.encode(),row['password_hash'].encode())
        except ValueError:pass
    if not valid:
        failures[ip] = recent+[now]
        raise HTTPException(401,"Invalid credentials")
    with connect() as db:
        status=db.execute("SELECT verified_at FROM account_security WHERE username=?",(username,)).fetchone()
    if username!=ADMIN and (not status or not status["verified_at"]): raise HTTPException(403,"Please verify your email before login")
    with connect() as db:
        factor=db.execute("SELECT 1 FROM account_factors WHERE username=? AND enabled=1",(username,)).fetchone()
        if factor:
            if not body.get('code'):return JSONResponse({'totp_required':True})
            if not security_keys.verify_code(db,username,body.get('code')):
                failures[ip]=recent+[now]
                raise HTTPException(401,'Invalid authentication code or recovery code')
    failures.pop(ip,None)
    return session_response(username)

def session_response(username):
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

@app.get("/api/dashboard")
def dashboard_config(request:Request):
    require(request)
    with connect() as db:
        db.execute("CREATE TABLE IF NOT EXISTS dashboard_config (username TEXT PRIMARY KEY, config TEXT NOT NULL)")
        row=db.execute("SELECT config FROM dashboard_config WHERE username=?",(user(request),)).fetchone()
    return json.loads(row["config"]) if row else {"tabs":["Main","Apps","Media"],"tiles":[]}

@app.put("/api/dashboard")
async def save_dashboard(request:Request):
    require(request);csrf(request)
    data=await request.json()
    if not isinstance(data,dict): raise HTTPException(400,"Invalid dashboard")
    tabs=data.get("tabs",[])
    tiles=data.get("tiles",[])
    if not isinstance(tabs,list) or not 1<=len(tabs)<=20 or any(not isinstance(t,str) or not 1<=len(t)<=40 for t in tabs) or len(set(tabs))!=len(tabs):
        raise HTTPException(400,"Invalid tabs")
    if not isinstance(tiles,list) or len(tiles)>200: raise HTTPException(400,"Too many tiles")
    cleaned=[]
    for tile in tiles:
        if not isinstance(tile,dict): raise HTTPException(400,"Invalid tile")
        name,tab,url,subtitle=(tile.get(k,"") for k in ("name","tab","url","subtitle"))
        if not all(isinstance(x,str) for x in (name,tab,url,subtitle)) or not 1<=len(name)<=80 or tab not in tabs or len(subtitle)>160 or len(url)>2048:
            raise HTTPException(400,"Invalid tile properties")
        if url:
            parsed=urlparse(url)
            if parsed.scheme not in ("https","http") or not parsed.hostname or parsed.username or parsed.password:
                raise HTTPException(400,"Invalid tile URL")
        x,y,w,h=(tile.get("x",0),tile.get("y",len(cleaned)*2),tile.get("w",4),tile.get("h",2))
        if not all(type(v) is int for v in (x,y,w,h)) or not (0<=x<12 and 0<=y<200 and 1<=w<=12 and 1<=h<=12 and x+w<=12):
            raise HTTPException(400,"Invalid tile grid position or size")
        cleaned.append({"name":name,"tab":tab,"url":url,"subtitle":subtitle,"x":x,"y":y,"w":w,"h":h})
    result={"tabs":tabs,"tiles":cleaned}
    with connect() as db:
        db.execute("CREATE TABLE IF NOT EXISTS dashboard_config (username TEXT PRIMARY KEY, config TEXT NOT NULL)")
        db.execute("INSERT OR REPLACE INTO dashboard_config VALUES (?,?)",(user(request),json.dumps(result)))
    return result

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

@app.get("/api/arcane")
async def arcane_status(request: Request):
    require(request)
    return await get_arcane()

@app.post("/api/arcane/environments/{environment_id}/containers/{container_id}/{action}")
async def arcane_manage(request: Request, environment_id: str, container_id: str, action: str):
    require(request)
    csrf(request)
    return await manage_container(environment_id, container_id, action)

@app.get("/api/truenas")
async def truenas_status(request: Request):
    require(request)
    url=os.getenv("TRUENAS_URL","").rstrip("/")
    key=os.getenv("TRUENAS_API_KEY","")
    if not url or not key:
        return {"configured":False,"system":None,"pools":[]}
    if not url.startswith("https://") and not (url.startswith("http://") and os.getenv("TRUENAS_ALLOW_HTTP")=="true"):
        raise HTTPException(503,"TrueNAS requires HTTPS or explicitly permitted LAN HTTP")
    try:
        async with httpx.AsyncClient(timeout=10,verify=os.getenv("TRUENAS_CA_BUNDLE") or True,follow_redirects=False) as client:
            headers={"Authorization":"Bearer "+key}
            sysresp=await client.get(url+"/api/v2.0/system/info",headers=headers)
            poolsresp=await client.get(url+"/api/v2.0/pool",headers=headers)
            sysresp.raise_for_status();poolsresp.raise_for_status()
            info=sysresp.json();pools=poolsresp.json()
            return {"configured":True,"system":{"hostname":info.get("hostname"),"version":info.get("version"),"uptime_seconds":info.get("uptime_seconds"),"physmem":info.get("physmem")},"pools":[{"name":p.get("name"),"status":p.get("status"),"healthy":p.get("healthy")} for p in pools]}
    except (httpx.HTTPError,ValueError,TypeError):
        raise HTTPException(502,"TrueNAS unavailable or API version incompatible")

@app.get("/api/proxmox/guest/{node}/{kind}/{vmid}")
async def proxmox_guest_details(request:Request,node:str,kind:str,vmid:int):
    require(request)
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}",node) or kind not in ("qemu","lxc") or not 1<=vmid<=999999999:
        raise HTTPException(400,"Invalid guest")
    url=os.getenv("PVE_URL","").rstrip("/")
    token_id=os.getenv("PVE_TOKEN_ID","")
    token_secret=os.getenv("PVE_TOKEN_SECRET","")
    if not all((url,token_id,token_secret)):
        raise HTTPException(503,"Proxmox not configured")
    headers={"Authorization":f"PVEAPIToken={token_id}={token_secret}"}
    path=f"/api2/json/nodes/{node}/{kind}/{vmid}"
    try:
        async with httpx.AsyncClient(timeout=10,verify=os.getenv("PVE_CA_BUNDLE") or True,follow_redirects=False) as client:
            status=await client.get(url+path+"/status/current",headers=headers)
            config=await client.get(url+path+"/config",headers=headers)
            status.raise_for_status();config.raise_for_status()
            current=status.json().get("data",{})
            configuration=config.json().get("data",{})
            return {"node":node,"kind":kind,"vmid":vmid,"status":current,"config":configuration}
    except (httpx.HTTPError,ValueError):
        raise HTTPException(502,"Unable to read Proxmox guest")

@app.get("/api/integrations")
def integrations_list(request:Request):
    require(request)
    with connect() as db:
        return {"profiles":integrations.list_profiles(db)}

@app.put("/api/integrations")
async def integrations_save(request:Request):
    require(request);csrf(request)
    payload=await request.json()
    if not isinstance(payload,dict): raise HTTPException(400,"Invalid payload")
    with connect() as db:
        ident=integrations.save(db,payload)
    return {"id":ident,"ok":True}

@app.delete("/api/integrations/{ident}")
def integrations_delete(ident:int,request:Request):
    require(request);csrf(request)
    with connect() as db:
        integrations.init(db)
        db.execute("DELETE FROM integrations WHERE id=?",(ident,))
    return {"ok":True}

# New public accounts must never inherit the legacy single-admin management APIs.
# Workspace APIs enforce membership and roles independently.
app.include_router(workspaces.router(connect, require, csrf, serializer, SECURE, ORIGIN))
app.include_router(security_keys.router(connect, require, csrf, ORIGIN, session_response))

@app.middleware("http")
async def legacy_admin_boundary(request:Request, call_next):
    path=request.url.path
    if path.startswith("/api/") and not (
        path in ("/api/login","/api/logout","/api/me","/api/register","/api/account/verify","/api/account/forgot-password","/api/account/reset-password")
        or path.startswith("/api/account/")
        or path.startswith("/api/auth/passkey/")
        or path.startswith("/api/monitoring")
        or path.startswith("/api/admin/audit")
        or path=="/api/widgets"
        or path.startswith("/api/workspaces")
        or path.startswith("/api/notifications")
        or path in ("/api/kuma", "/api/kuma/preview")
        or path in ("/api/services","/api/search","/api/notification-settings")
        or path=="/api/tickets"
        or path.startswith("/api/tickets/")
        or path.startswith("/api/admin/tickets")
        or path.startswith("/api/admin/accounts")
        or path.startswith("/api/admin/proxy-requests")
        or path=="/api/invitations/accept"
    ):
        username=user(request)
        if username and username!=ADMIN:
            return JSONResponse({"detail":"Legacy management API is administrator-only"},status_code=403)
    return await call_next(request)
