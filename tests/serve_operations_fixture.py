import os,sys,tempfile
os.environ.update(SESSION_SECRET='browser-test-session-secret-long-enough',ADMIN_PASSWORD='browser-test-password-long-enough',ADMIN_USERNAME='admin@example.test',PUBLIC_ORIGIN='http://localhost:8082',COOKIE_SECURE='false')
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import main
import uvicorn
from fastapi.responses import JSONResponse
@main.app.middleware("http")
async def fixture_status(request,call_next):
 if request.url.path.startswith("/api/workspaces/") and "/status/" in request.url.path:return JSONResponse({"status":"online"})
 return await call_next(request)
main.DB=tempfile.mktemp(suffix='.sqlite3',prefix='agms-browser-')
main.init()
with main.connect() as db:
 db.execute('INSERT INTO users VALUES (?,?)',('user@example.test',main.bcrypt.hashpw(b'browser-test-password-long-enough',main.bcrypt.gensalt()).decode()))
 db.execute("INSERT INTO account_profiles(username,email,role) VALUES (?,?,'user')",('user@example.test','user@example.test'))
 db.execute("INSERT INTO account_security(username,verified_at,tier) VALUES (?,unixepoch(),0)",('user@example.test',))
with main.connect() as db:
 db.execute("INSERT INTO workspaces(id,name,owner) VALUES ('webui-browser','WebUI browser',?)",(main.ADMIN,))
 db.execute("INSERT INTO workspace_members(workspace_id,username,role) VALUES ('webui-browser',?,'owner')",(main.ADMIN,))
 db.execute("INSERT INTO workspace_members(workspace_id,username,role) VALUES ('webui-browser','user@example.test','viewer')")
 for ident,title,url,mode in [('arcane','Arcane iframe','https://arc.agrosskopf.de/','embed'),('bookstack','BookStack proxy','https://book.agrosskopf.de/','proxy')]:
  db.execute("INSERT INTO workspace_navigation(id,workspace_id,title,icon,url,open_mode,min_role) VALUES (?,'webui-browser',?,'globe',?,?,'viewer')",(ident,title,url,mode))
with main.connect() as db:
 from app import operations
 operations.audit(db,'webui-browser',main.ADMIN,'homepage.created',{'name':'WebUI browser'})
 operations.record(db,'webui-browser','arcane',{'status':'online'})
 operations.record(db,'webui-browser','bookstack',{'status':'offline'})
 db.execute("INSERT INTO workspace_notifications(id,username,message) VALUES ('fixture-expiry','user@example.test','Expiry warning: Example certificate')")
# External delivery is covered by mocked API tests; browser fixtures never send messages.
main.push_channels.send=lambda *args,**kwargs: {}
main.operations.check_due_watches=lambda *args,**kwargs: None
uvicorn.run(main.app,host='127.0.0.1',port=8082)
