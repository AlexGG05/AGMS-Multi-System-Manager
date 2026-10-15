"""Isolated browser fixture: real SSH transport, simulated guacd (not a real RDP host)."""
import os,sys,json,tempfile,asyncio,time
from pathlib import Path
os.environ.update(SESSION_SECRET='remote-fixture-session-secret-long-enough',ADMIN_PASSWORD='browser-test-password-long-enough',ADMIN_USERNAME='admin@example.test',PUBLIC_ORIGIN='http://localhost:8083',COOKIE_SECURE='false')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import asyncssh,uvicorn
from app import main,remote_sessions,guacamole_protocol
from app.integrations import cipher
main.DB=tempfile.mktemp(suffix='.sqlite3',prefix='agms-remote-fixture-');main.init()
original_validate=remote_sessions.validate_address
# Loopback bypass belongs ONLY to this isolated fixture, never to application code.
remote_sessions.validate_address=lambda value:value if value=='127.0.0.1' else original_validate(value)
key=asyncssh.generate_private_key('ssh-ed25519')
class Server(asyncssh.SSHServer):
 def begin_auth(self,user):return True
 def password_auth_supported(self):return True
 def validate_password(self,user,password):return user=='fixture' and password=='fixture-password'
async def process(p):
 p.stdout.write(b'AGMS SSH fixture ready\r\n')
 while True:
  try:data=await p.stdin.readline()
  except asyncssh.TerminalSizeChanged:continue
  if not data:return
  p.stdout.write(b'fixture: '+data)
async def fake_guacd(reader,writer):
 try:
  await guacamole_protocol.read_instruction(reader)
  writer.write(guacamole_protocol.instruction('args','VERSION_1_5_0','hostname','port','username','password','security','ignore-cert'));await writer.drain()
  for _ in range(5):await guacamole_protocol.read_instruction(reader)
  for args in [('ready','browser-fixture'),('size',0,640,480),('rect',0,0,0,640,480),('cfill',12,0,20,70,110,255),('sync',int(time.time()*1000))]:writer.write(guacamole_protocol.instruction(*args))
  await writer.drain()
  while True:await guacamole_protocol.read_instruction(reader)
 except (asyncio.IncompleteReadError,ConnectionError):pass
 finally:writer.close();await writer.wait_closed()
@main.app.on_event('startup')
async def fixture_start():
 main.app.state.fixture_ssh=await asyncssh.create_server(Server,'127.0.0.1',0,server_host_keys=[key],process_factory=process,encoding=None)
 main.app.state.fixture_guac=await asyncio.start_server(fake_guacd,'127.0.0.1',0)
 os.environ['GUACD_HOST']='127.0.0.1';os.environ['GUACD_PORT']=os.getenv('AGMS_TEST_GUACD_PORT') or str(main.app.state.fixture_guac.sockets[0].getsockname()[1])
 with main.connect() as db:
  db.execute("INSERT OR IGNORE INTO workspaces(id,name,owner) VALUES('remote-fixture','Remote fixture',?)",(main.ADMIN,));db.execute("INSERT OR IGNORE INTO workspace_members VALUES('remote-fixture',?,'owner')",(main.ADMIN,))
  for ident,kind,port in [('ssh-test','ssh',main.app.state.fixture_ssh.get_port()),('rdp-test','rdp',3389)]:
   db.execute('INSERT OR IGNORE INTO workspace_navigation(id,workspace_id,title,url,open_mode) VALUES(?,?,?,?,?)',(ident,'remote-fixture',kind.upper()+' fixture',kind+'://connection',kind))
   secret=cipher().encrypt(json.dumps({'password':'fixture-password','workspace_id':'remote-fixture','item_id':ident}).encode())
   db.execute('INSERT OR REPLACE INTO remote_connections(workspace_id,item_id,kind,host,port,username,fingerprint,secret) VALUES(?,?,?,?,?,?,?,?)',('remote-fixture',ident,kind,'fixture-'+kind,port,'fixture',key.get_fingerprint() if kind=='ssh' else os.getenv('AGMS_TEST_RDP_FINGERPRINT',''),secret))
   db.execute('INSERT OR REPLACE INTO remote_targets VALUES(?,?,?,?,?)',(kind,'fixture-'+kind,port,json.dumps([os.getenv('AGMS_TEST_RDP_ADDRESS','127.0.0.1') if kind=='rdp' else '127.0.0.1']),main.ADMIN))
@main.app.on_event('shutdown')
async def fixture_stop():
 main.app.state.fixture_ssh.close();await main.app.state.fixture_ssh.wait_closed();main.app.state.fixture_guac.close();await main.app.state.fixture_guac.wait_closed()
uvicorn.run(main.app,host='127.0.0.1',port=8083)
