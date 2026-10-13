"""Multi-user workspace API. Existing login/session and legacy dashboard remain intact."""
import os, re, json, time, secrets, hashlib, sqlite3, socket, ssl, ipaddress, asyncio
from urllib.parse import urlparse
import bcrypt
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from .mailer import send_email

EMAIL = re.compile(r"^[^\s@]{1,64}@[^\s@]{1,190}\.[^\s@]{2,}$")
ROLES = {"owner", "editor", "viewer"}
PLANS = {"user", "premium", "admin"}
attempts = {}

def install(db):
    db.executescript("""
    CREATE TABLE IF NOT EXISTS account_profiles(
      username TEXT PRIMARY KEY REFERENCES users(username),
      email TEXT UNIQUE, role TEXT NOT NULL DEFAULT 'user',
      created_at INTEGER NOT NULL DEFAULT (unixepoch())
    );
    CREATE TABLE IF NOT EXISTS workspaces(
      id TEXT PRIMARY KEY, name TEXT NOT NULL, owner TEXT NOT NULL REFERENCES users(username),
      created_at INTEGER NOT NULL DEFAULT (unixepoch())
    );
    CREATE TABLE IF NOT EXISTS workspace_members(
      workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
      username TEXT NOT NULL REFERENCES users(username),
      role TEXT NOT NULL CHECK(role IN ('owner','editor','viewer')),
      PRIMARY KEY(workspace_id,username)
    );
    CREATE TABLE IF NOT EXISTS workspace_navigation(
      id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
      parent_id TEXT, title TEXT NOT NULL, icon TEXT NOT NULL DEFAULT 'globe',
      url TEXT, position INTEGER NOT NULL DEFAULT 0, min_role TEXT NOT NULL DEFAULT 'viewer'
    );
    CREATE TABLE IF NOT EXISTS workspace_invitations(
      id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
      email TEXT NOT NULL, role TEXT NOT NULL, token_hash TEXT NOT NULL UNIQUE,
      expires_at INTEGER NOT NULL, created_by TEXT NOT NULL, accepted_at INTEGER
    );
    CREATE TABLE IF NOT EXISTS workspace_notifications(id TEXT PRIMARY KEY,username TEXT NOT NULL,workspace_id TEXT, message TEXT NOT NULL,created_at INTEGER NOT NULL DEFAULT (unixepoch()),read_at INTEGER);
    CREATE INDEX IF NOT EXISTS idx_notifications_user ON workspace_notifications(username,read_at,created_at);
    CREATE TABLE IF NOT EXISTS account_security(username TEXT PRIMARY KEY, verified_at INTEGER, tier INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS account_tokens(token_hash TEXT PRIMARY KEY, username TEXT NOT NULL, purpose TEXT NOT NULL, expires_at INTEGER NOT NULL, used_at INTEGER);
    CREATE INDEX IF NOT EXISTS idx_members_username ON workspace_members(username);
    CREATE INDEX IF NOT EXISTS idx_nav_workspace ON workspace_navigation(workspace_id,position);
    """)
    columns={row[1] for row in db.execute("PRAGMA table_info(workspace_navigation)").fetchall()}
    if "open_mode" not in columns:
        db.execute("ALTER TABLE workspace_navigation ADD COLUMN open_mode TEXT NOT NULL DEFAULT 'embed'")
    for column,definition in (("favorite","INTEGER NOT NULL DEFAULT 0"),("color","TEXT NOT NULL DEFAULT ''"),("icon_url","TEXT NOT NULL DEFAULT ''")):
        if column not in {row[1] for row in db.execute("PRAGMA table_info(workspace_navigation)").fetchall()}:
            db.execute("ALTER TABLE workspace_navigation ADD COLUMN "+column+" "+definition)
    db.execute("INSERT OR IGNORE INTO account_security(username,verified_at,tier) SELECT username,unixepoch(),0 FROM users WHERE username=?", (os.getenv("ADMIN_USERNAME","admin"),))
    db.execute("INSERT OR IGNORE INTO account_profiles(username,email,role) SELECT username, CASE WHEN instr(username,'@')>0 THEN lower(username) ELSE NULL END, 'admin' FROM users WHERE username=?", (os.getenv("ADMIN_USERNAME","admin"),))

def router(connect, require, csrf, serializer, secure, origin):
    api = APIRouter()
    def identity(request):
        username=require(request)
        if username!=os.getenv("ADMIN_USERNAME","admin"):
            with connect() as db:
                row=db.execute("SELECT verified_at FROM account_security WHERE username=?",(username,)).fetchone()
            if not row or not row["verified_at"]: raise HTTPException(403,"Email verification required")
        return username
    def membership(db, wsid, username, edit=False, owner=False):
        row=db.execute("SELECT role FROM workspace_members WHERE workspace_id=? AND username=?", (wsid,username)).fetchone()
        if not row: raise HTTPException(404,"Workspace not found")
        if owner and row["role"]!="owner": raise HTTPException(403,"Owner permission required")
        if edit and row["role"] not in ("owner","editor"): raise HTTPException(403,"Editor permission required")
        return row["role"]
    def ensure_default(db, username):
        if db.execute("SELECT 1 FROM workspaces WHERE owner=? LIMIT 1",(username,)).fetchone(): return
        wid=secrets.token_hex(12)
        db.execute("INSERT INTO workspaces(id,name,owner) VALUES(?,?,?)",(wid,"Mein Homelab",username))
        db.execute("INSERT INTO workspace_members(workspace_id,username,role) VALUES(?,?,'owner')",(wid,username))
        db.execute("INSERT OR IGNORE INTO account_profiles(username,email,role) VALUES(?,?,?)",(username,username.lower() if '@' in username else None,'admin' if username==os.getenv('ADMIN_USERNAME','admin') else 'user'))
    def clean_url(url):
        if url is None or url=="": return None
        if not isinstance(url,str) or len(url)>2048: raise HTTPException(400,"Invalid URL")
        u=urlparse(url)
        if u.scheme not in ("http","https") or not u.hostname or u.username or u.password: raise HTTPException(400,"Invalid http(s) URL")
        return url
    @api.post("/api/register")
    async def register(request:Request):
        if request.headers.get("origin","").rstrip("/")!=origin: raise HTTPException(403,"Origin mismatch")
        ip=request.client.host if request.client else "unknown"
        now=time.monotonic()
        recent=[t for t in attempts.get(ip,[]) if now-t<3600]
        if len(recent)>=5: raise HTTPException(429,"Too many registrations")
        attempts[ip]=recent+[now]
        body=await request.json()
        email=str(body.get("email","")).strip().lower()
        password=str(body.get("password",""))
        if not EMAIL.fullmatch(email) or len(password)<16 or len(password)>128: raise HTTPException(400,"Valid email and password of 16–128 characters required")
        hashed=bcrypt.hashpw(password.encode(),bcrypt.gensalt()).decode()
        with connect() as db:
            try:
                db.execute("INSERT INTO users(username,password_hash) VALUES(?,?)",(email,hashed))
                db.execute("INSERT INTO account_profiles(username,email,role) VALUES(?,?,'user')",(email,email))
                db.execute("INSERT INTO account_security(username) VALUES(?)",(email,))
                token=secrets.token_urlsafe(32)
                db.execute("INSERT INTO account_tokens VALUES(?,?,?,?,NULL)",(hashlib.sha256(token.encode()).hexdigest(),email,"verify",int(time.time())+86400))
            except sqlite3.IntegrityError: raise HTTPException(409,"Account already exists")
        send_email(email,"CodeX Homelab: E-Mail bestätigen","Bestätige deine E-Mail-Adresse: "+origin+"/static/verify.html?token="+token+" (24 Stunden gültig)")
        return {"ok":True,"message":"Verification email sent"}
    @api.get("/api/workspaces")
    def list_workspaces(request:Request):
        username=identity(request)
        with connect() as db:
            ensure_default(db,username)
            rows=db.execute("SELECT w.id,w.name,m.role FROM workspaces w JOIN workspace_members m ON w.id=m.workspace_id WHERE m.username=? ORDER BY w.created_at,w.name",(username,)).fetchall()
            profile=db.execute("SELECT role FROM account_profiles WHERE username=?",(username,)).fetchone()
        return {"workspaces":[dict(x) for x in rows],"account_role":profile["role"] if profile else "user"}
    @api.post("/api/workspaces")
    async def create_workspace(request:Request):
        username=identity(request);csrf(request)
        body=await request.json();name=str(body.get("name","")).strip()
        if not 1<=len(name)<=80: raise HTTPException(400,"Name must be 1–80 characters")
        wid=secrets.token_hex(12)
        with connect() as db:
            if username!=os.getenv("ADMIN_USERNAME","admin"):
                row=db.execute("SELECT tier FROM account_security WHERE username=?",(username,)).fetchone()
                tier=row["tier"] if row else 0
                limit={0:1,1:3,2:5,3:10}[tier]
                if db.execute("SELECT COUNT(*) FROM workspaces WHERE owner=?",(username,)).fetchone()[0]>=limit: raise HTTPException(403,"Homepage limit reached")
            db.execute("INSERT INTO workspaces(id,name,owner) VALUES(?,?,?)",(wid,name,username))
            db.execute("INSERT INTO workspace_members(workspace_id,username,role) VALUES(?,?,'owner')",(wid,username))
        return {"id":wid,"name":name,"role":"owner"}
    @api.patch("/api/workspaces/{wsid}")
    async def rename_workspace(request:Request,wsid:str):
        username=identity(request);csrf(request)
        body=await request.json();name=str(body.get("name","")).strip()
        if not 1<=len(name)<=80: raise HTTPException(400,"Name must be 1-80 characters")
        with connect() as db:
            membership(db,wsid,username,owner=True)
            db.execute("UPDATE workspaces SET name=? WHERE id=?",(name,wsid))
        return {"ok":True,"name":name}
    @api.get("/api/notifications")
    def notifications(request:Request):
        username=identity(request)
        with connect() as db:
            rows=db.execute("SELECT id,workspace_id,message,created_at FROM workspace_notifications WHERE username=? AND read_at IS NULL ORDER BY created_at DESC LIMIT 30",(username,)).fetchall()
        return {"notifications":[dict(x) for x in rows]}
    @api.post("/api/notifications/{nid}/read")
    def notification_read(request:Request,nid:str):
        username=identity(request);csrf(request)
        with connect() as db:
            db.execute("UPDATE workspace_notifications SET read_at=unixepoch() WHERE id=? AND username=?",(nid,username))
        return {"ok":True}
    @api.delete("/api/workspaces/{wsid}")
    def delete_workspace(request:Request,wsid:str):
        username=identity(request);csrf(request)
        with connect() as db:
            membership(db,wsid,username,owner=True)
            db.execute("DELETE FROM workspace_invitations WHERE workspace_id=?",(wsid,))
            db.execute("DELETE FROM workspace_navigation WHERE workspace_id=?",(wsid,))
            db.execute("DELETE FROM workspace_members WHERE workspace_id=?",(wsid,))
            db.execute("DELETE FROM workspaces WHERE id=? AND owner=?",(wsid,username))
        return {"ok":True}
    @api.delete("/api/workspaces/{wsid}/members/{member}")
    def remove_member(request:Request,wsid:str,member:str):
        username=identity(request);csrf(request)
        with connect() as db:
            membership(db,wsid,username,owner=True)
            if member==username: raise HTTPException(400,"Owner cannot be removed")
            db.execute("DELETE FROM workspace_members WHERE workspace_id=? AND username=? AND role!='owner'",(wsid,member))
        return {"ok":True}
    @api.get("/api/workspaces/{wsid}")
    def workspace(request:Request,wsid:str):
        username=identity(request)
        with connect() as db:
            role=membership(db,wsid,username)
            w=db.execute("SELECT id,name FROM workspaces WHERE id=?",(wsid,)).fetchone()
            nav=db.execute("SELECT id,parent_id,title,icon,url,position,min_role,open_mode,favorite,color,icon_url FROM workspace_navigation WHERE workspace_id=? ORDER BY position,id",(wsid,)).fetchall()
        order={"viewer":0,"editor":1,"owner":2}
        return {"workspace":dict(w),"role":role,"navigation":[dict(n) for n in nav if order[role]>=order[n["min_role"]]]}
    @api.get("/api/workspaces/{wsid}/status/{item_id}")
    async def navigation_status(request:Request,wsid:str,item_id:str):
        username=identity(request)
        with connect() as db:
            role=membership(db,wsid,username)
            item=db.execute("SELECT url,min_role FROM workspace_navigation WHERE workspace_id=? AND id=?",(wsid,item_id)).fetchone()
        if not item or not item["url"]: raise HTTPException(404,"WebUI not found")
        if {"viewer":0,"editor":1,"owner":2}[role]<{"viewer":0,"editor":1,"owner":2}.get(item["min_role"],3):
            raise HTTPException(404,"WebUI not found")
        target=urlparse(item["url"])
        if target.scheme not in ("http","https") or not target.hostname: return {"status":"unknown"}
        if target.username or target.password: return {"status":"unknown"}
        port=target.port or (443 if target.scheme=="https" else 80)
        if port not in (80,443,8080,8443): return {"status":"unknown","reason":"port"}
        def check():
            try:
                hostname=target.hostname
                addresses=socket.getaddrinfo(hostname,port,type=socket.SOCK_STREAM)
                ips={address[4][0] for address in addresses}
                if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):
                    return {"status":"unknown","reason":"private"}
                ip=sorted(ips)[0]
                sock=socket.create_connection((ip,port),timeout=3)
                try:
                    sock.settimeout(3)
                    if target.scheme=="https":
                        sock=ssl.create_default_context().wrap_socket(sock,server_hostname=hostname)
                    path=target.path or "/"
                    if target.query:path+="?"+target.query
                    host_header=hostname if port in (80,443) else hostname+":"+str(port)
                    request_line="HEAD "+path+" HTTP/1.1\\r\\nHost: "+host_header+"\\r\\nConnection: close\\r\\nUser-Agent: AGMS-Status/1.0\\r\\n\\r\\n"
                    sock.sendall(request_line.encode("utf-8"))
                    response=sock.recv(256)
                    if response.startswith(b"HTTP/"):return {"status":"online"}
                    return {"status":"unknown"}
                finally:sock.close()
            except (OSError,ssl.SSLError,ValueError,UnicodeError):
                return {"status":"offline"}
        return await asyncio.to_thread(check)
    @api.put("/api/workspaces/{wsid}/navigation")
    async def update_navigation(request:Request,wsid:str):
        username=identity(request);csrf(request)
        body=await request.json();items=body.get("items")
        if not isinstance(items,list) or len(items)>150: raise HTTPException(400,"Invalid navigation")
        cleaned=[];ids=set()
        for i,item in enumerate(items):
            if not isinstance(item,dict): raise HTTPException(400,"Invalid item")
            ident=str(item.get("id") or secrets.token_hex(12))
            title=str(item.get("title","")).strip();icon=str(item.get("icon","globe")).strip()
            parent=item.get("parent_id");parent=str(parent) if parent else None
            min_role=str(item.get("min_role","viewer"))
            open_mode=str(item.get("open_mode","embed"))
            if open_mode not in ("embed","external"): raise HTTPException(400,"Invalid open mode")
            favorite=1 if item.get("favorite") else 0
            color=str(item.get("color") or "")
            if color and not re.fullmatch(r"#[0-9a-fA-F]{6}",color): raise HTTPException(400,"Invalid color")
            icon_url=str(item.get("icon_url") or "").strip()
            if icon_url:
                parsed=urlparse(icon_url)
                if parsed.scheme!="https" or not parsed.hostname or parsed.username or parsed.password or len(icon_url)>2048: raise HTTPException(400,"Invalid icon URL")
            if ident in ids or not 1<=len(title)<=80 or len(icon)>40 or min_role not in ROLES or (parent and parent==ident): raise HTTPException(400,"Invalid item")
            ids.add(ident);cleaned.append((ident,wsid,parent,title,icon,clean_url(item.get("url")),i,min_role,open_mode,favorite,color,icon_url))
        for row in cleaned:
            if row[2] and row[2] not in ids: raise HTTPException(400,"Unknown parent")
            if row[2] and next(x for x in cleaned if x[0]==row[2])[2]: raise HTTPException(400,"Nested groups are not supported")
        with connect() as db:
            membership(db,wsid,username,edit=True)
            db.execute("DELETE FROM workspace_navigation WHERE workspace_id=?",(wsid,))
            db.executemany("INSERT INTO workspace_navigation(id,workspace_id,parent_id,title,icon,url,position,min_role,open_mode,favorite,color,icon_url) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",cleaned)
        return {"ok":True}
    @api.get("/api/workspaces/{wsid}/members")
    def members(request:Request,wsid:str):
        username=identity(request)
        with connect() as db:
            membership(db,wsid,username)
            rows=db.execute("SELECT m.username,p.email,m.role FROM workspace_members m LEFT JOIN account_profiles p ON p.username=m.username WHERE m.workspace_id=? ORDER BY m.role,m.username",(wsid,)).fetchall()
        return {"members":[dict(x) for x in rows]}
    @api.post("/api/workspaces/{wsid}/invitations")
    async def invite(request:Request,wsid:str):
        username=identity(request);csrf(request)
        body=await request.json();email=str(body.get("email","")).strip().lower();role=str(body.get("role","viewer"))
        if not EMAIL.fullmatch(email) or role not in ("editor","viewer"): raise HTTPException(400,"Invalid invitation")
        token=secrets.token_urlsafe(32);ident=secrets.token_hex(12);expiry=int(time.time())+7*86400
        with connect() as db:
            membership(db,wsid,username,owner=True)
            existing=db.execute("SELECT p.username FROM account_profiles p JOIN account_security s ON s.username=p.username WHERE p.email=? AND s.verified_at IS NOT NULL",(email,)).fetchone()
            if existing:
                member=existing["username"]
                if member==username: raise HTTPException(400,"Cannot invite yourself")
                previous=db.execute("SELECT role FROM workspace_members WHERE workspace_id=? AND username=?",(wsid,member)).fetchone()
                if previous: raise HTTPException(409,"User is already a member")
                db.execute("INSERT INTO workspace_members(workspace_id,username,role) VALUES(?,?,?)",(wsid,member,role))
                home=db.execute("SELECT name FROM workspaces WHERE id=?",(wsid,)).fetchone()
                db.execute("INSERT INTO workspace_notifications(id,username,workspace_id,message) VALUES(?,?,?,?)",(secrets.token_hex(12),member,wsid,"Du wurdest zur Homepage „"+home["name"]+"“ hinzugefügt."))
                return {"ok":True,"delivery":"in_app","added":True}
            db.execute("INSERT INTO workspace_invitations(id,workspace_id,email,role,token_hash,expires_at,created_by) VALUES(?,?,?,?,?,?,?)",(ident,wsid,email,role,hashlib.sha256(token.encode()).hexdigest(),expiry,username))
        send_email(email,"CodeX Homelab: Team-Einladung","Einladung annehmen: "+origin+"/static/invite.html?token="+token)
        return {"id":ident,"expires_at":expiry,"delivery":"smtp","added":False}
    @api.post("/api/invitations/accept")
    async def accept(request:Request):
        username=identity(request);csrf(request)
        body=await request.json();token=str(body.get("token",""))
        with connect() as db:
            invite=db.execute("SELECT * FROM workspace_invitations WHERE token_hash=?",(hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
            profile=db.execute("SELECT email FROM account_profiles WHERE username=?",(username,)).fetchone()
            if not invite or invite["accepted_at"] or invite["expires_at"]<time.time(): raise HTTPException(400,"Invalid or expired invitation")
            if not profile or profile["email"]!=invite["email"]: raise HTTPException(403,"Invitation belongs to another email")
            db.execute("INSERT OR IGNORE INTO workspace_members(workspace_id,username,role) VALUES(?,?,?)",(invite["workspace_id"],username,invite["role"]))
            db.execute("UPDATE workspace_invitations SET accepted_at=? WHERE id=?",(int(time.time()),invite["id"]))
        return {"ok":True,"workspace_id":invite["workspace_id"]}

    def token_action(db, token, purpose):
        hashed=hashlib.sha256(token.encode()).hexdigest()
        row=db.execute("SELECT username FROM account_tokens WHERE token_hash=? AND purpose=? AND used_at IS NULL AND expires_at>?",(hashed,purpose,int(time.time()))).fetchone()
        if not row: raise HTTPException(400,"Invalid or expired token")
        db.execute("UPDATE account_tokens SET used_at=? WHERE token_hash=?",(int(time.time()),hashed))
        return row["username"]
    def guard(request,kind,limit=5):
        if request.headers.get("origin","").rstrip("/")!=origin: raise HTTPException(403,"Origin mismatch")
        key=(kind,request.client.host if request.client else "unknown")
        now=time.monotonic();recent=[x for x in attempts.get(key,[]) if now-x<3600]
        if len(recent)>=limit: raise HTTPException(429,"Too many requests")
        attempts[key]=recent+[now]
    @api.post("/api/account/verify")
    async def verify(request:Request):
        guard(request,"verify",20)
        body=await request.json()
        with connect() as db:
            username=token_action(db,str(body.get("token","")),"verify")
            db.execute("UPDATE account_security SET verified_at=? WHERE username=?",(int(time.time()),username))
        return {"ok":True}
    @api.post("/api/account/forgot-password")
    async def forgot(request:Request):
        guard(request,"forgot",4)
        body=await request.json();email=str(body.get("email","")).strip().lower()
        if EMAIL.fullmatch(email):
            with connect() as db:
                row=db.execute("SELECT username FROM account_profiles WHERE email=?",(email,)).fetchone()
                if row:
                    token=secrets.token_urlsafe(32)
                    db.execute("INSERT INTO account_tokens VALUES(?,?,?,?,NULL)",(hashlib.sha256(token.encode()).hexdigest(),row["username"],"reset",int(time.time())+1800))
            if row: send_email(email,"CodeX Homelab: Passwort zurücksetzen","Passwort zurücksetzen (30 Minuten): "+origin+"/static/reset-password.html?token="+token)
        return {"ok":True,"message":"If this email exists, a reset message will be sent"}
    @api.post("/api/account/reset-password")
    async def reset(request:Request):
        guard(request,"reset",8)
        body=await request.json();password=str(body.get("password",""))
        if not 16<=len(password)<=72: raise HTTPException(400,"Password must be 16-72 characters")
        with connect() as db:
            username=token_action(db,str(body.get("token","")),"reset")
            db.execute("UPDATE users SET password_hash=? WHERE username=?",(bcrypt.hashpw(password.encode(),bcrypt.gensalt()).decode(),username))
        return {"ok":True}
    @api.get("/api/admin/accounts")
    def accounts(request:Request):
        if identity(request)!=os.getenv("ADMIN_USERNAME","admin"): raise HTTPException(403,"Admin only")
        with connect() as db:
            rows=db.execute("SELECT p.username,p.email,p.role,COALESCE(s.tier,0) tier,s.verified_at FROM account_profiles p LEFT JOIN account_security s ON s.username=p.username ORDER BY p.created_at DESC LIMIT 500").fetchall()
        return {"accounts":[dict(x) for x in rows]}
    @api.delete("/api/admin/accounts/{username}")
    def delete_account(request:Request,username:str):
        admin=identity(request);csrf(request)
        if admin!=os.getenv("ADMIN_USERNAME","admin"): raise HTTPException(403,"Admin only")
        if username==admin: raise HTTPException(400,"Admin account cannot be deleted")
        with connect() as db:
            if not db.execute("SELECT 1 FROM users WHERE username=?",(username,)).fetchone(): raise HTTPException(404,"Account not found")
            owned=[x[0] for x in db.execute("SELECT id FROM workspaces WHERE owner=?",(username,)).fetchall()]
            for wsid in owned:
                db.execute("DELETE FROM workspace_notifications WHERE workspace_id=?",(wsid,))
                db.execute("DELETE FROM workspace_invitations WHERE workspace_id=?",(wsid,))
                db.execute("DELETE FROM workspace_navigation WHERE workspace_id=?",(wsid,))
                db.execute("DELETE FROM workspace_members WHERE workspace_id=?",(wsid,))
                db.execute("DELETE FROM workspaces WHERE id=?",(wsid,))
            db.execute("DELETE FROM workspace_members WHERE username=?",(username,))
            db.execute("DELETE FROM workspace_notifications WHERE username=?",(username,))
            db.execute("DELETE FROM account_tokens WHERE username=?",(username,))
            db.execute("DELETE FROM account_security WHERE username=?",(username,))
            db.execute("DELETE FROM account_profiles WHERE username=?",(username,))
            db.execute("DELETE FROM users WHERE username=?",(username,))
        return {"ok":True}
    @api.put("/api/admin/accounts/{username}/tier")
    async def tier(request:Request,username:str):
        if identity(request)!=os.getenv("ADMIN_USERNAME","admin"): raise HTTPException(403,"Admin only")
        csrf(request);body=await request.json();level=body.get("tier")
        if type(level)!=int or level not in (0,1,2,3): raise HTTPException(400,"Tier must be 0-3")
        if username==os.getenv("ADMIN_USERNAME","admin"): raise HTTPException(400,"Cannot change admin tier")
        with connect() as db:
            if not db.execute("SELECT 1 FROM users WHERE username=?",(username,)).fetchone(): raise HTTPException(404,"Unknown user")
            db.execute("INSERT INTO account_security(username,tier) VALUES(?,?) ON CONFLICT(username) DO UPDATE SET tier=excluded.tier",(username,level))
            db.execute("UPDATE account_profiles SET role=? WHERE username=?",("premium" if level else "user",username))
        return {"ok":True,"tier":level}
    return api
