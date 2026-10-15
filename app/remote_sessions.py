"""Permission-bound SSH/Guacamole gateway. No arbitrary browser-supplied targets."""
import asyncio
import hashlib
import ipaddress
import json
import os
import re
import secrets
import socket
import time
import sys
import weakref
from pathlib import Path
from urllib.parse import urlsplit

import asyncssh
from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from .integrations import cipher
from . import operations, guacamole_protocol

ORDER={'viewer':0,'editor':1,'owner':2}
SESSION_LIMIT=8
MAX_MESSAGE=65536
RECHECK_SECONDS=5


def install(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS remote_connections(
      workspace_id TEXT NOT NULL,item_id TEXT NOT NULL,kind TEXT NOT NULL,
      host TEXT NOT NULL,port INTEGER NOT NULL,username TEXT NOT NULL,
      fingerprint TEXT NOT NULL DEFAULT '',secret BLOB NOT NULL,version INTEGER NOT NULL DEFAULT 1,
      PRIMARY KEY(workspace_id,item_id));
    CREATE TABLE IF NOT EXISTS remote_targets(
      kind TEXT NOT NULL,host TEXT NOT NULL,port INTEGER NOT NULL,addresses TEXT NOT NULL,
      approved_by TEXT NOT NULL,PRIMARY KEY(kind,host,port));
    CREATE TABLE IF NOT EXISTS remote_sessions(
      id TEXT PRIMARY KEY,username TEXT NOT NULL,workspace_id TEXT NOT NULL,item_id TEXT NOT NULL,
      cookie_hash TEXT NOT NULL,version INTEGER NOT NULL,state INTEGER NOT NULL DEFAULT 0,
      expires_at INTEGER NOT NULL,heartbeat INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS remote_session_attempts(username TEXT NOT NULL,started_at INTEGER NOT NULL);
    CREATE INDEX IF NOT EXISTS remote_attempts_user ON remote_session_attempts(username,started_at);
    CREATE INDEX IF NOT EXISTS remote_sessions_user ON remote_sessions(username,heartbeat);
    ''')


async def json_body(request):
    raw=bytearray()
    async for part in request.stream():
        raw.extend(part)
        if len(raw)>65536:raise HTTPException(413,'Remote configuration too large')
    try:body=json.loads(raw)
    except (ValueError,UnicodeError):raise HTTPException(400,'Invalid JSON')
    if not isinstance(body,dict):raise HTTPException(400,'Invalid remote configuration')
    return body


def cookie_hash(request):
    return hashlib.sha256(request.cookies.get('session','').encode()).hexdigest()


def revoke_cookie(connect,request):
    with connect() as db:db.execute('DELETE FROM remote_sessions WHERE cookie_hash=?',(cookie_hash(request),))


def validate_address(value):
    address=ipaddress.ip_address(value)
    if address.is_loopback or address.is_link_local or address.is_multicast or address.is_unspecified or address.is_reserved:
        raise ValueError('Unsafe remote destination')
    if not (address.is_global or address in ipaddress.ip_network('10.0.0.0/8') or address in ipaddress.ip_network('172.16.0.0/12') or address in ipaddress.ip_network('192.168.0.0/16') or address in ipaddress.ip_network('fc00::/7')):
        raise ValueError('Unsafe remote destination')
    return str(address)


def resolve_target(host,port):
    rows=socket.getaddrinfo(host,port,type=socket.SOCK_STREAM)
    result=sorted({validate_address(row[4][0]) for row in rows})
    if not result or len(result)>16:raise ValueError('Invalid remote destination')
    return result


def approved_address(db,config):
    row=db.execute('SELECT addresses FROM remote_targets WHERE kind=? AND host=? AND port=?',(config['kind'],config['host'],config['port'])).fetchone()
    if not row:raise HTTPException(403,'An administrator must approve this remote destination first')
    addresses=json.loads(row['addresses'])
    if not addresses:raise HTTPException(403,'Remote destination is not approved')
    # Pin to the administrator-approved addresses; never resolve again while connecting.
    return validate_address(addresses[0])


def access(db,username,wsid,itemid,edit=False):
    user=db.execute('SELECT p.role,s.verified_at FROM account_profiles p LEFT JOIN account_security s ON s.username=p.username WHERE p.username=?',(username,)).fetchone()
    member=db.execute('SELECT role FROM workspace_members WHERE workspace_id=? AND username=?',(wsid,username)).fetchone()
    item=db.execute('SELECT * FROM workspace_navigation WHERE workspace_id=? AND id=?',(wsid,itemid)).fetchone()
    if not user or (username!=os.getenv('ADMIN_USERNAME','admin') and not user['verified_at']) or not member or not item or ORDER.get(member['role'],-1)<ORDER.get(item['min_role'],99):
        raise HTTPException(404,'Remote connection not found')
    if item['open_mode']=='rdp' and user['role']!='admin':raise HTTPException(403,'RDP is currently available to administrators only')
    if edit and member['role'] not in ('owner','editor'):raise HTTPException(403,'Editor permission required')
    return item


def metadata(row):
    return {k:row[k] for k in ('kind','host','port','username','fingerprint')}|{'configured':True}


def unpack(row):
    data=json.loads(cipher().decrypt(row['secret']))
    if data.pop('workspace_id')!=row['workspace_id'] or data.pop('item_id')!=row['item_id']:raise ValueError('Credential binding mismatch')
    return dict(row)|data


KEY_WORKERS=0
KEY_LOCKS=weakref.WeakKeyDictionary()

async def decode_key(private_key,passphrase):
    global KEY_WORKERS
    if KEY_WORKERS>=8:raise HTTPException(429,'SSH key validation is busy. Try again shortly.')
    KEY_WORKERS+=1
    worker=None;acquired=False
    lock=KEY_LOCKS.setdefault(asyncio.get_running_loop(),asyncio.Semaphore(1))
    try:
        try:await asyncio.wait_for(lock.acquire(),10);acquired=True
        except asyncio.TimeoutError:raise HTTPException(429,'SSH key validation is busy. Try again shortly.')
        worker=await asyncio.create_subprocess_exec(sys.executable,str(Path(__file__).with_name('remote_key.py')),
            stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL,
            env={'PATH':os.environ.get('PATH',''),'PYTHONDONTWRITEBYTECODE':'1'})
        output,_=await asyncio.wait_for(worker.communicate(json.dumps({'private_key':private_key,'passphrase':passphrase}).encode()),8)
        if worker.returncode or not output or len(output)>65536:raise ValueError('Invalid SSH key')
        return asyncssh.import_private_key(output)
    finally:
        if worker and worker.returncode is None:
            worker.kill();await worker.wait()
        if acquired:lock.release()
        KEY_WORKERS-=1


class PinnedSSHClient(asyncssh.SSHClient):
    def __init__(self,fingerprint):self.fingerprint=fingerprint
    def validate_host_public_key(self,host,addr,port,key):
        return secrets.compare_digest(key.get_fingerprint('sha256'),self.fingerprint)


async def ssh_bridge(ws,config,address):
    keys=[]
    if config.get('private_key'):
        keys=[await decode_key(config['private_key'],config.get('passphrase'))]
    async with asyncssh.connect(address,port=config['port'],username=config['username'],
            password=config.get('password') or None,client_keys=keys,agent_path=None,config=None,
            known_hosts=(),client_factory=lambda:PinnedSSHClient(config['fingerprint']),
            login_timeout=15,connect_timeout=15,keepalive_interval=20,keepalive_count_max=3) as connection:
        process=await connection.create_process(term_type='xterm-256color',term_size=(100,30),encoding=None)
        async def output():
            while True:
                data=await process.stdout.read(32768)
                if not data:return
                await ws.send_bytes(data)
        async def input():
            while True:
                message=await ws.receive_json()
                if not isinstance(message,dict):raise ValueError('Invalid terminal message')
                if message.get('type')=='input':
                    data=message.get('data')
                    if not isinstance(data,str) or len(data.encode())>MAX_MESSAGE:raise ValueError('Terminal input too large')
                    process.stdin.write(data.encode());await process.stdin.drain()
                elif message.get('type')=='resize':
                    cols,rows=message.get('cols'),message.get('rows')
                    if type(cols)!=int or type(rows)!=int or not (2<=cols<=500 and 2<=rows<=300):raise ValueError('Invalid terminal dimensions')
                    process.change_terminal_size(cols,rows)
                else:raise ValueError('Invalid terminal operation')
        try:await race(output(),input())
        finally:process.close()


async def race(*coroutines):
    tasks=[asyncio.create_task(c) for c in coroutines]
    try:
        done,_=await asyncio.wait(tasks,return_when=asyncio.FIRST_COMPLETED)
        for task in done:task.result()
    finally:
        for task in tasks:task.cancel()
        await asyncio.gather(*tasks,return_exceptions=True)


async def rdp_bridge(ws,config,address,width,height):
    host=os.getenv('GUACD_HOST','')
    if not host:raise ValueError('Guacamole is not enabled')
    reader,writer=await asyncio.wait_for(asyncio.open_connection(host,int(os.getenv('GUACD_PORT','4822')),limit=2*1024*1024),10)
    try:
        ident=await guacamole_protocol.handshake(reader,writer,config,address,width,height)
        await ws.send_text('0.,'+str(len(ident))+'.'+ident+';')
        async def output():
            import codecs
            decoder=codecs.getincrementaldecoder('utf-8')()
            while True:
                data=await reader.read(65536)
                if not data:return
                text=decoder.decode(data)
                if text:await ws.send_text(text)
        async def input():
            parser=guacamole_protocol.ClientParser()
            while True:
                data=await ws.receive_text()
                if len(data.encode())>MAX_MESSAGE:raise ValueError('Guacamole input too large')
                for args in parser.feed(data):
                    args=guacamole_protocol.client_instruction(args)
                    if args[0]=='' and len(args)==3 and args[1]=='ping':
                        await ws.send_text(guacamole_protocol.instruction(*args).decode())
                    elif args[0] in ('key','mouse','size','sync','ack','nop'):
                        writer.write(guacamole_protocol.instruction(*args));await writer.drain()
                    else:raise ValueError('Unsupported Guacamole input')
        await race(output(),input())
    finally:writer.close();await writer.wait_closed()


def router(connect,identity,csrf,membership,editable,serializer,origin):
    api=APIRouter()
    def admin(request):
        username=identity(request)
        with connect() as db:r=db.execute('SELECT role FROM account_profiles WHERE username=?',(username,)).fetchone()
        if not r or r['role']!='admin':raise HTTPException(403,'Admin only')
        return username

    @api.get('/api/remote/targets')
    def targets(request:Request):
        admin(request)
        with connect() as db:return {'targets':[dict(r) for r in db.execute('SELECT kind,host,port,approved_by FROM remote_targets ORDER BY host,port')]}

    @api.post('/api/remote/targets')
    async def approve(request:Request):
        username=admin(request);csrf(request);body=await json_body(request)
        kind=body.get('kind');host=body.get('host');port=body.get('port')
        if kind not in ('ssh','rdp') or not isinstance(host,str) or not re.fullmatch(r'[A-Za-z0-9_.:\[\]-]{1,253}',host) or type(port)!=int or not 1<=port<=65535:raise HTTPException(400,'Invalid remote destination')
        try:addresses=await asyncio.to_thread(resolve_target,host,port)
        except (OSError,ValueError):raise HTTPException(400,'Remote destination cannot be approved')
        with connect() as db:
            db.execute('INSERT INTO remote_targets VALUES(?,?,?,?,?) ON CONFLICT(kind,host,port) DO UPDATE SET addresses=excluded.addresses,approved_by=excluded.approved_by',(kind,host.lower(),port,json.dumps(addresses),username))
        return {'ok':True,'addresses':addresses}

    @api.delete('/api/remote/targets')
    async def unapprove(request:Request):
        admin(request);csrf(request);body=await json_body(request)
        with connect() as db:db.execute('DELETE FROM remote_targets WHERE kind=? AND host=? AND port=?',(body.get('kind'),body.get('host'),body.get('port')))
        return {'ok':True}

    @api.get('/api/workspaces/{wsid}/remote/{itemid}')
    def configuration(request:Request,wsid:str,itemid:str):
        username=identity(request)
        with connect() as db:
            access(db,username,wsid,itemid)
            row=db.execute('SELECT * FROM remote_connections WHERE workspace_id=? AND item_id=?',(wsid,itemid)).fetchone()
        return metadata(row) if row else {'configured':False}

    @api.put('/api/workspaces/{wsid}/remote/{itemid}')
    async def configure(request:Request,wsid:str,itemid:str):
        username=identity(request);csrf(request);body=await json_body(request)
        if not isinstance(body,dict) or len(json.dumps(body))>50000:raise HTTPException(400,'Invalid remote configuration')
        kind=body.get('kind');host=body.get('host','');host=host.lower() if isinstance(host,str) else host;port=body.get('port');login=body.get('username')
        if kind not in ('ssh','rdp') or not isinstance(host,str) or not re.fullmatch(r'[a-z0-9_.:\[\]-]{1,253}',host) or type(port)!=int or not 1<=port<=65535 or not isinstance(login,str) or not 1<=len(login)<=128 or any(c in login for c in '\r\n\x00'):raise HTTPException(400,'Invalid remote configuration')
        fingerprint=body.get('fingerprint','')
        if kind=='ssh' and (not isinstance(fingerprint,str) or not re.fullmatch(r'SHA256:[A-Za-z0-9+/]{43}=?',fingerprint)):raise HTTPException(400,'SSH host key SHA256 fingerprint is required')
        if kind=='ssh':fingerprint=fingerprint.rstrip('=')
        if kind=='rdp':
            if not isinstance(fingerprint,str) or (fingerprint and not re.fullmatch(r'(?:[A-Fa-f0-9]{64}|(?:[A-Fa-f0-9]{2}:){31}[A-Fa-f0-9]{2})',fingerprint)):raise HTTPException(400,'Use the RDP certificate SHA256 fingerprint (64 hexadecimal digits)')
            fingerprint=fingerprint.replace(':','').lower()
        secrets_data={key:body.get(key,'') for key in ('password','private_key','passphrase','domain')}
        if any(not isinstance(v,str) or len(v)>32768 for v in secrets_data.values()):raise HTTPException(400,'Invalid remote credentials')
        with connect() as db:
            item=access(db,username,wsid,itemid,edit=True);editable(db,wsid)
        if kind=='ssh' and secrets_data['private_key']:
            try:await decode_key(secrets_data['private_key'],secrets_data['passphrase'])
            except (ValueError,asyncssh.KeyImportError,asyncio.TimeoutError):raise HTTPException(400,'Invalid SSH key or passphrase')
        with connect() as db:
            item=access(db,username,wsid,itemid,edit=True);editable(db,wsid)
            if item['open_mode']!=kind:raise HTTPException(409,'Save the tile opening mode first')
            existing=db.execute('SELECT * FROM remote_connections WHERE workspace_id=? AND item_id=?',(wsid,itemid)).fetchone()
            if not secrets_data['password'] and not secrets_data['private_key']:
                if not existing or (existing['kind'],existing['host'],existing['port'],existing['username'])!=(kind,host,port,login):raise HTTPException(400,'Credentials are required for this connection')
                old=unpack(existing)
                for key in secrets_data:secrets_data[key]=old.get(key,'')
            if kind=='rdp' and (not secrets_data['password'] or secrets_data['private_key']):raise HTTPException(400,'RDP requires a password')
            encrypted=cipher().encrypt(json.dumps(secrets_data|{'workspace_id':wsid,'item_id':itemid}).encode())
            db.execute('INSERT INTO remote_connections(workspace_id,item_id,kind,host,port,username,fingerprint,secret) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(workspace_id,item_id) DO UPDATE SET kind=excluded.kind,host=excluded.host,port=excluded.port,username=excluded.username,fingerprint=excluded.fingerprint,secret=excluded.secret,version=remote_connections.version+1',(wsid,itemid,kind,host,port,login,fingerprint,encrypted))
            db.execute('DELETE FROM remote_sessions WHERE workspace_id=? AND item_id=?',(wsid,itemid))
            operations.audit(db,wsid,username,'remote.configured',{'service':itemid,'kind':kind})
        return {'ok':True}

    @api.delete('/api/workspaces/{wsid}/remote/{itemid}')
    def remove(request:Request,wsid:str,itemid:str):
        username=identity(request);csrf(request)
        with connect() as db:
            access(db,username,wsid,itemid,edit=True);editable(db,wsid)
            db.execute('DELETE FROM remote_connections WHERE workspace_id=? AND item_id=?',(wsid,itemid))
            db.execute('DELETE FROM remote_sessions WHERE workspace_id=? AND item_id=?',(wsid,itemid))
        return {'ok':True}

    @api.post('/api/workspaces/{wsid}/remote/{itemid}/sessions')
    def start(request:Request,wsid:str,itemid:str):
        username=identity(request);csrf(request);now=int(time.time())
        with connect() as db:
            db.execute('BEGIN IMMEDIATE')
            item=access(db,username,wsid,itemid)
            config=db.execute('SELECT * FROM remote_connections WHERE workspace_id=? AND item_id=?',(wsid,itemid)).fetchone()
            if not config or config['kind']!=item['open_mode']:raise HTTPException(409,'Configure the remote connection first')
            approved_address(db,config)
            if config['kind']=='rdp' and not os.getenv('GUACD_HOST'):raise HTTPException(503,'Start the bundled Guacamole Docker service first')
            db.execute('DELETE FROM remote_sessions WHERE expires_at<? OR heartbeat<?',(now,now-60))
            count=db.execute('SELECT count(*) FROM remote_sessions WHERE username=?',(username,)).fetchone()[0]
            if count>=SESSION_LIMIT:raise HTTPException(429,'Remote session limit reached')
            db.execute('DELETE FROM remote_session_attempts WHERE started_at<?',(now-60,))
            if db.execute('SELECT count(*) FROM remote_session_attempts WHERE username=? AND started_at>=?',(username,now-60)).fetchone()[0]>=20:raise HTTPException(429,'Too many remote connection attempts. Try again in a minute.')
            db.execute('INSERT INTO remote_session_attempts VALUES(?,?)',(username,now))
            ticket=secrets.token_urlsafe(32)
            db.execute('INSERT INTO remote_sessions VALUES(?,?,?,?,?,?,0,?,?)',(hashlib.sha256(ticket.encode()).hexdigest(),username,wsid,itemid,cookie_hash(request),config['version'],now+30,now))
        return {'ticket':ticket,'kind':config['kind']}

    @api.delete('/api/remote/sessions')
    def close_sessions(request:Request):
        identity(request);csrf(request);revoke_cookie(connect,request);return {'ok':True}

    @api.websocket('/api/remote/tunnel')
    async def tunnel(ws:WebSocket):
        if ws.headers.get('origin')!=origin:
            await ws.close(code=1008);return
        try:
            signed=serializer.loads(ws.cookies.get('session',''),max_age=8*3600)
            username=signed['u'];ticket=ws.query_params.get('ticket','')
            if not 20<=len(ticket)<=100:raise ValueError()
            sid=hashlib.sha256(ticket.encode()).hexdigest();now=int(time.time())
            with connect() as db:
                lease=db.execute('SELECT * FROM remote_sessions WHERE id=? AND username=? AND cookie_hash=? AND state=0 AND expires_at>=?',(sid,username,cookie_hash(ws),now)).fetchone()
                if not lease:raise ValueError()
                item=access(db,username,lease['workspace_id'],lease['item_id'])
                row=db.execute('SELECT * FROM remote_connections WHERE workspace_id=? AND item_id=?',(lease['workspace_id'],lease['item_id'])).fetchone()
                if not row or row['kind']!=item['open_mode'] or row['version']!=lease['version']:raise ValueError()
                address=approved_address(db,row);config=unpack(row)
                updated=db.execute('UPDATE remote_sessions SET state=1,expires_at=? WHERE id=? AND state=0',(now+8*3600,sid))
                if updated.rowcount!=1:raise ValueError()
            kind=config['kind']
            protocol='guacamole' if kind=='rdp' else None
            if kind=='rdp' and 'guacamole' not in ws.scope.get('subprotocols',[]):raise ValueError()
            await ws.accept(subprotocol=protocol)
        except Exception:
            await ws.close(code=1008);return
        async def guard():
            while True:
                await asyncio.sleep(RECHECK_SECONDS)
                serializer.loads(ws.cookies.get('session',''),max_age=8*3600)
                with connect() as db:
                    current=db.execute('SELECT * FROM remote_sessions WHERE id=? AND expires_at>=?',(sid,int(time.time()))).fetchone()
                    if not current:raise ValueError('Session ended')
                    item=access(db,username,current['workspace_id'],current['item_id'])
                    row=db.execute('SELECT * FROM remote_connections WHERE workspace_id=? AND item_id=?',(current['workspace_id'],current['item_id'])).fetchone()
                    if not row or row['version']!=current['version'] or row['kind']!=item['open_mode'] or approved_address(db,row)!=address:raise ValueError('Connection changed')
                    db.execute('UPDATE remote_sessions SET heartbeat=? WHERE id=?',(int(time.time()),sid))
        try:
            width=max(320,min(3840,int(ws.query_params.get('width','1280'))));height=max(240,min(2160,int(ws.query_params.get('height','720'))))
            bridge=ssh_bridge(ws,config,address) if kind=='ssh' else rdp_bridge(ws,config,address,width,height)
            await race(guard(),bridge)
        except Exception:
            # Never expose upstream exceptions: they can include passwords or keys.
            try:
                if kind=='ssh':await ws.send_json({'error':'Remote session ended. Check destination, credentials, host key and permissions.'})
                else:await ws.send_text(guacamole_protocol.instruction('error','Remote connection failed',512).decode())
            except Exception:pass
        finally:
            with connect() as db:db.execute('DELETE FROM remote_sessions WHERE id=?',(sid,))
            try:await ws.close()
            except Exception:pass
    return api
