"""Monitoring settings, API widgets, expiry watches and audit log."""
import asyncio,json,math,re,secrets,time,ssl
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
from urllib.parse import quote
from fastapi import APIRouter,Request,HTTPException
from . import public_net,security_keys

DEFAULT={'refresh_seconds':60,'widgets':[]}
DE_EXPIRY_NOTE='Public expiry dates are not published for .de domains. Enter the renewal date from your registrar.'


def proxmox_summary(nodes,guests,configured=True):
    vms=[g for g in guests if g.get('type',g.get('kind'))=='qemu']
    containers=[g for g in guests if g.get('type',g.get('kind'))=='lxc']
    cpus=[n['cpu'] for n in nodes if isinstance(n.get('cpu'),(int,float))]
    memory=[n for n in nodes if isinstance(n.get('mem'),(int,float)) and isinstance(n.get('maxmem'),(int,float)) and n['maxmem']>0]
    return {'configured':configured,'nodes':len(nodes),
            'vms_total':len(vms),'vms_running':sum(g.get('status')=='running' for g in vms),
            'lxc_total':len(containers),'lxc_running':sum(g.get('status')=='running' for g in containers),
            'cpu_percent':round(sum(cpus)/len(cpus)*100,1) if cpus else None,
            'ram_percent':round(sum(n['mem'] for n in memory)/sum(n['maxmem'] for n in memory)*100,1) if memory else None}


def personal_widget(kind,connection):
    from .integrations import cipher
    token=cipher().decrypt(connection['token']).decode()
    base=connection['url']
    if kind=='proxmox':
        headers={'Authorization':'PVEAPIToken='+token}
        nodes=public_net.request(base+'/api2/json/cluster/resources?type=node',headers=headers)['data']
        guests=public_net.request(base+'/api2/json/cluster/resources?type=vm',headers=headers)['data']
        return proxmox_summary(nodes,guests)
    from .arcane import _items
    headers={'X-Api-Key':token}
    environments=_items(public_net.request(base+'/api/environments',headers=headers))
    if len(environments)>50:raise ValueError('Too many environments')
    containers=[]
    for env in environments:
        ident=str(env.get('id',''))
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,128}',ident):raise ValueError('Invalid environment')
        containers.extend(_items(public_net.request(base+'/api/environments/'+ident+'/containers',headers=headers)))
    return {'configured':True,'containers':len(containers),'running':sum(c.get('state')=='running' for c in containers)}


def install(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS personal_widget_connections(username TEXT NOT NULL,kind TEXT NOT NULL,url TEXT NOT NULL,token BLOB NOT NULL,PRIMARY KEY(username,kind));
    CREATE TABLE IF NOT EXISTS widget_connections(username TEXT PRIMARY KEY,url TEXT NOT NULL,token BLOB NOT NULL);
    CREATE TABLE IF NOT EXISTS user_preferences(username TEXT PRIMARY KEY,settings TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS service_history(workspace_id TEXT NOT NULL,service_id TEXT NOT NULL,checked_at INTEGER NOT NULL,status TEXT NOT NULL,http_status INTEGER,PRIMARY KEY(workspace_id,service_id,checked_at));
    CREATE TABLE IF NOT EXISTS service_dependencies(workspace_id TEXT NOT NULL,service_id TEXT NOT NULL,depends_on TEXT NOT NULL,PRIMARY KEY(workspace_id,service_id,depends_on));
    CREATE TABLE IF NOT EXISTS expiry_watches(id TEXT PRIMARY KEY,username TEXT NOT NULL,kind TEXT NOT NULL,value TEXT NOT NULL,label TEXT NOT NULL,expires_at INTEGER,checked_at INTEGER,error TEXT);
    CREATE TABLE IF NOT EXISTS audit_log(id INTEGER PRIMARY KEY AUTOINCREMENT,workspace_id TEXT NOT NULL,workspace_name TEXT NOT NULL,actor TEXT NOT NULL,action TEXT NOT NULL,details TEXT NOT NULL,created_at INTEGER NOT NULL DEFAULT (unixepoch()));
    CREATE INDEX IF NOT EXISTS audit_workspace ON audit_log(workspace_id,id);
    CREATE TABLE IF NOT EXISTS push_channels(username TEXT NOT NULL,provider TEXT NOT NULL,settings BLOB NOT NULL,enabled INTEGER NOT NULL DEFAULT 0,enabled_at INTEGER NOT NULL DEFAULT (unixepoch()),PRIMARY KEY(username,provider));
    CREATE TABLE IF NOT EXISTS push_outbox(notification_id TEXT NOT NULL,provider TEXT NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,next_attempt_at INTEGER NOT NULL DEFAULT 0,sent_at INTEGER,PRIMARY KEY(notification_id,provider));
    ''')
    if 'manual_expires_at' not in {r[1] for r in db.execute('PRAGMA table_info(expiry_watches)')}:db.execute('ALTER TABLE expiry_watches ADD COLUMN manual_expires_at INTEGER')
    db.execute("UPDATE expiry_watches SET error=?,expires_at=NULL WHERE kind='domain' AND manual_expires_at IS NULL AND lower(value) LIKE '%.de'",(DE_EXPIRY_NOTE,))
    db.execute("INSERT OR IGNORE INTO personal_widget_connections SELECT username,'sabnzbd',url,token FROM widget_connections")
    security_keys.install(db)


def audit(db,workspace,actor,action,details):
    row=db.execute('SELECT name FROM workspaces WHERE id=?',(workspace,)).fetchone()
    db.execute('INSERT INTO audit_log(workspace_id,workspace_name,actor,action,details) VALUES(?,?,?,?,?)',(workspace,row['name'] if row else ('Status pages · '+workspace[5:] if workspace.startswith('kuma:') else 'Deleted homepage'),actor,action,json.dumps(details,ensure_ascii=False)))


def preferences(db,username):
    row=db.execute('SELECT settings FROM user_preferences WHERE username=?',(username,)).fetchone()
    return {**DEFAULT,**(json.loads(row['settings']) if row else {})}


def record(db,workspace,service,result):
    stamp=int(time.time())//60*60
    db.execute('DELETE FROM service_history WHERE workspace_id=? AND service_id=?',(workspace,service))
    db.execute('INSERT INTO service_history VALUES(?,?,?,?,?)',(workspace,service,stamp,result.get('status','unknown'),result.get('http_status')))
    db.execute('DELETE FROM service_history WHERE checked_at<?',(stamp-30*86400,))


class NoPublicExpiry(ValueError):
    pass


def check_watch(kind,value):
    if kind=='certificate':
        url=public_net.endpoint(value)
        with public_net.connection(url) as sock:cert=sock.getpeercert()
        return int(ssl.cert_time_to_seconds(cert['notAfter']))
    if value.lower().endswith('.de'):raise NoPublicExpiry(DE_EXPIRY_NOTE)
    data=public_net.request('https://rdap.org/domain/'+quote(value,safe=''),redirects=4)
    events=[e for e in data.get('events',[]) if e.get('eventAction')=='expiration']
    if not events:raise NoPublicExpiry('The registry does not publish an expiry date. Enter the renewal date from your registrar.')
    return int(datetime.fromisoformat(events[0]['eventDate'].replace('Z','+00:00')).timestamp())


def check_due_watches(connect,force_user=None):
    with connect() as db:
        rows=db.execute('SELECT * FROM expiry_watches WHERE '+('username=?' if force_user else '(checked_at IS NULL OR checked_at<unixepoch()-21600)')+' LIMIT 30', (force_user,) if force_user else ()).fetchall()
    def inspect(row):
        try:return (row['manual_expires_at'] if row['manual_expires_at'] is not None else check_watch(row['kind'],row['value'])),None
        except NoPublicExpiry as exc:return None,str(exc)
        except Exception:return None,'Could not verify expiry. Check address, TLS or registry availability.'
    with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(inspect,rows))
    for row,(expiry,error) in zip(rows,results):
        with connect() as db:
            db.execute('UPDATE expiry_watches SET expires_at=?,checked_at=unixepoch(),error=? WHERE id=?',(expiry,error,row['id']))
            if expiry and expiry-time.time()<30*86400:
                marker='expiry:'+row['id']+':'+str(expiry)
                if not db.execute('SELECT 1 FROM workspace_notifications WHERE id=?',(marker,)).fetchone():
                    db.execute('INSERT INTO workspace_notifications(id,username,message) VALUES(?,?,?)',(marker,row['username'],'Expiry warning: '+row['label']))
                    from .push_channels import queue
                    queue(db,marker,row['username'])


def router(connect,identity,csrf,require_admin,workspace_editable=None):
    from .features import json_body,visible_services
    api=APIRouter()

    @api.get('/api/account/preferences')
    def get_preferences(request:Request):
        username=identity(request)
        with connect() as db:return preferences(db,username)

    @api.put('/api/account/preferences')
    async def save_preferences(request:Request):
        username=identity(request);csrf(request);body=await json_body(request)
        if set(body)!=set(DEFAULT) or type(body['refresh_seconds']) is not int or body['refresh_seconds'] not in (0,30,60,120,300) or not isinstance(body['widgets'],list) or any(w not in ('tickets','status','expiry','proxmox','arcane','sabnzbd') for w in body['widgets']) or len(body['widgets'])>6:
            raise HTTPException(400,'Invalid profile preferences')
        with connect() as db:db.execute('INSERT INTO user_preferences VALUES(?,?) ON CONFLICT(username) DO UPDATE SET settings=excluded.settings',(username,json.dumps(body)))
        return {'ok':True}

    @api.get('/api/monitoring')
    def overview(request:Request):
        username=identity(request)
        with connect() as db:
            services=[dict(s) for s in visible_services(db,username) if s['url']]
            for s in services:
                row=db.execute('SELECT status,checked_at,http_status FROM service_history WHERE workspace_id=? AND service_id=? ORDER BY checked_at DESC LIMIT 1',(s['workspace_id'],s['id'])).fetchone()
                s['latest']=dict(row) if row else None
                member=db.execute('SELECT role FROM workspace_members WHERE workspace_id=? AND username=?',(s['workspace_id'],username)).fetchone()
                s['can_edit']=member['role'] in ('owner','editor') and (workspace_editable(db,s['workspace_id']) if workspace_editable else True)
            watches=[dict(r) for r in db.execute('SELECT * FROM expiry_watches WHERE username=? ORDER BY label',(username,))]
            settings=preferences(db,username)
        return {'services':services,'watches':watches,'preferences':settings,'now':int(time.time())}

    @api.post('/api/monitoring/watches')
    async def add_watch(request:Request):
        username=identity(request);csrf(request);body=await json_body(request);kind=body.get('kind');value=body.get('value');label=body.get('label')
        if kind not in ('certificate','domain') or not isinstance(value,str) or not isinstance(label,str) or not 1<=len(label.strip())<=100:raise HTTPException(400,'Invalid expiry watch')
        try:
            if kind=='certificate':public_net.endpoint(value)
            elif not re.fullmatch(r'(?=.{3,253}$)(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,63}',value):raise ValueError()
        except ValueError:raise HTTPException(400,'Enter an HTTPS URL or a domain such as example.com')
        with connect() as db:
            if db.execute('SELECT count(*) FROM expiry_watches WHERE username=?',(username,)).fetchone()[0]>=30:raise HTTPException(400,'Maximum 30 expiry watches')
            ident=secrets.token_hex(12);db.execute('INSERT INTO expiry_watches(id,username,kind,value,label) VALUES(?,?,?,?,?)',(ident,username,kind,value,label.strip()))
        return {'id':ident}

    @api.put('/api/monitoring/watches/{ident}')
    async def renewal_date(request:Request,ident:str):
        username=identity(request);csrf(request);body=await json_body(request)
        value=body.get('renewal_date')
        try:
            if value is not None and (not isinstance(value,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',value)):raise ValueError()
            expiry=int(datetime.strptime(value,'%Y-%m-%d').replace(tzinfo=timezone.utc).timestamp()) if value else None
        except (ValueError,TypeError,OverflowError):raise HTTPException(400,'Enter a valid renewal date')
        with connect() as db:
            row=db.execute('SELECT * FROM expiry_watches WHERE id=? AND username=?',(ident,username)).fetchone()
            if not row:raise HTTPException(404,'Expiry watch not found')
            if row['kind']!='domain':raise HTTPException(400,'Manual dates are only available for domain renewals')
            db.execute('UPDATE expiry_watches SET manual_expires_at=?,expires_at=?,checked_at=NULL,error=NULL WHERE id=?',(expiry,expiry,ident))
        return {'ok':True}

    @api.delete('/api/monitoring/watches/{ident}')
    def remove_watch(request:Request,ident:str):
        username=identity(request);csrf(request)
        with connect() as db:db.execute('DELETE FROM expiry_watches WHERE id=? AND username=?',(ident,username))
        return {'ok':True}

    @api.post('/api/monitoring/watches/refresh')
    async def refresh_watches(request:Request):
        username=identity(request);csrf(request)
        security_keys.throttle(request)
        await asyncio.to_thread(check_due_watches,connect,username)
        return {'ok':True}

    @api.get('/api/admin/audit')
    def audit_pages(request:Request):
        require_admin(request)
        with connect() as db:
            pages=[dict(r) for r in db.execute('''SELECT w.id,w.name,w.owner,
              (SELECT actor FROM audit_log a WHERE a.workspace_id=w.id ORDER BY id DESC LIMIT 1) last_actor,
              (SELECT created_at FROM audit_log a WHERE a.workspace_id=w.id ORDER BY id DESC LIMIT 1) last_changed
              FROM workspaces w ORDER BY w.name''')]
            for r in db.execute('SELECT username FROM kuma_dashboards'):
                ident='kuma:'+r['username'];last=db.execute('SELECT actor,created_at FROM audit_log WHERE workspace_id=? ORDER BY id DESC LIMIT 1',(ident,)).fetchone()
                pages.append({'id':ident,'name':'Status pages · '+r['username'],'owner':r['username'],'last_actor':last['actor'] if last else None,'last_changed':last['created_at'] if last else None})
            deleted=[dict(r) for r in db.execute('''SELECT workspace_id id,workspace_name name,actor last_actor,created_at last_changed FROM audit_log WHERE action='homepage.deleted' ORDER BY id DESC''')]
        return {'pages':pages,'deleted_pages':deleted}

    @api.get('/api/admin/audit/{workspace}')
    def audit_events(request:Request,workspace:str,before:int=9223372036854775807):
        require_admin(request)
        with connect() as db:rows=[dict(r) for r in db.execute('SELECT * FROM audit_log WHERE workspace_id=? AND id<? ORDER BY id DESC LIMIT 50',(workspace,before))]
        for row in rows:row['details']=json.loads(row['details'])
        return {'events':rows,'next_before':rows[-1]['id'] if len(rows)==50 else None}

    @api.get('/api/account/widget-connections')
    def widget_connections(request:Request):
        username=identity(request)
        with connect() as db:
            return {'connections':{r['kind']:{'url':r['url'],'configured':True} for r in db.execute('SELECT kind,url FROM personal_widget_connections WHERE username=?',(username,))}}

    @api.put('/api/account/widget-connection')
    async def widget_connection(request:Request):
        from .integrations import cipher
        username=identity(request);csrf(request);body=await json_body(request)
        kind=body.get('kind','sabnzbd')
        if kind not in ('sabnzbd','proxmox','arcane'):raise HTTPException(400,'Invalid widget connection')
        try:
            parsed=public_net.endpoint(body.get('url'))
            if parsed.query:raise ValueError()
        except (ValueError,TypeError):raise HTTPException(400,'Use a public HTTPS address without credentials')
        token=body.get('token','')
        if not isinstance(token,str) or len(token)>2000 or any(c in token for c in ('\r','\n')):raise HTTPException(400,'Invalid API credential')
        with connect() as db:
            existing=db.execute('SELECT * FROM personal_widget_connections WHERE username=? AND kind=?',(username,kind)).fetchone()
            url=body['url'].rstrip('/')
            if not token and (not existing or existing['url']!=url):raise HTTPException(400,'Enter the API credential for this endpoint')
            if kind=='proxmox' and token and not re.fullmatch(r'[^\s=]+@[^\s=]+![^\s=]+=[^\s=]+',token):raise HTTPException(400,'Use user@realm!token-id=token-secret')
            encrypted=cipher().encrypt(token.encode()) if token else existing['token']
            db.execute('INSERT INTO personal_widget_connections VALUES(?,?,?,?) ON CONFLICT(username,kind) DO UPDATE SET url=excluded.url,token=excluded.token',(username,kind,url,encrypted))
        return {'ok':True}

    @api.delete('/api/account/widget-connection/{kind}')
    def delete_widget_connection(kind:str,request:Request):
        username=identity(request);csrf(request)
        if kind not in ('sabnzbd','proxmox','arcane'):raise HTTPException(400,'Invalid widget connection')
        with connect() as db:
            db.execute('DELETE FROM personal_widget_connections WHERE username=? AND kind=?',(username,kind))
            if kind=='sabnzbd':db.execute('DELETE FROM widget_connections WHERE username=?',(username,))
        return {'ok':True}

    @api.get('/api/widgets')
    async def widgets(request:Request):
        username=identity(request)
        with connect() as db:
            config=preferences(db,username);data={}
            if 'tickets' in config['widgets']:
                data['tickets']={r['status']:r['total'] for r in db.execute('SELECT status,count(*) total FROM support_tickets WHERE username=? GROUP BY status',(username,))}
            if 'status' in config['widgets']:
                services=[s for s in visible_services(db,username) if s['url']];counts={s:0 for s in ('online','offline','degraded','unknown')}
                for service in services:
                    last=db.execute('SELECT status,checked_at FROM service_history WHERE workspace_id=? AND service_id=? ORDER BY checked_at DESC LIMIT 1',(service['workspace_id'],service['id'])).fetchone()
                    counts[last['status'] if last and time.time()-last['checked_at']<300 else 'unknown']+=1
                data['status']=counts
            if 'expiry' in config['widgets']:data['expiry']={'due':db.execute('SELECT count(*) FROM expiry_watches WHERE username=? AND expires_at<unixepoch()+2592000',(username,)).fetchone()[0]}
            connections={r['kind']:dict(r) for r in db.execute('SELECT * FROM personal_widget_connections WHERE username=?',(username,))}
            connection=connections.get('sabnzbd')
            admin=db.execute("SELECT 1 FROM account_profiles WHERE username=? AND role='admin'",(username,)).fetchone()
        if 'sabnzbd' in config['widgets']:
            if not connection:data['sabnzbd']={'error':'Configure the SABnzbd widget connection in your profile.'}
            else:
                from .integrations import cipher
                try:
                    token=cipher().decrypt(connection['token']).decode()
                    result=await asyncio.to_thread(public_net.request,connection['url']+'/api?mode=queue&output=json&apikey='+quote(token,safe=''))
                    queue=result['queue'];data['sabnzbd']={k:queue.get(k) for k in ('status','speed','sizeleft','timeleft')}
                except Exception:data['sabnzbd']={'error':'SABnzbd is unavailable or the API key is invalid.'}
        for kind in ('proxmox','arcane'):
            if kind not in config['widgets']:continue
            if kind in connections:
                try:
                    data[kind]=await asyncio.to_thread(personal_widget,kind,connections[kind])
                except Exception:data[kind]={'error':'Integration unavailable. Check the configured API connection.'}
                continue
            if not admin:data[kind]={'error':'Configure the widget connection in your profile.'};continue
            try:
                if kind=='proxmox':
                    from .main import proxmox
                    result=await proxmox(request)
                    if not isinstance(result,dict):raise ValueError()
                    data[kind]=proxmox_summary(result['nodes'],result['guests'],result['configured'])
                else:
                    from .arcane import get_arcane
                    result=await get_arcane()
                    data[kind]={'configured':result['configured'],'containers':len(result.get('containers',[])),'running':sum(c['state']=='running' for c in result.get('containers',[]))}
            except Exception:data[kind]={'error':'Integration unavailable. Check the configured API connection.'}
        return {'widgets':config['widgets'],'data':data}

    return api
