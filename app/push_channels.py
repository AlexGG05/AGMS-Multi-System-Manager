"""User opt-in push channels, encrypted secrets and durable retry queue."""
import json,time
from urllib.parse import urlsplit,quote
from fastapi import APIRouter,Request,HTTPException
from .integrations import cipher
from . import public_net

PROVIDERS=('ntfy','gotify','telegram','discord')


def queue(db,notification,username):
    for row in db.execute('SELECT provider FROM push_channels WHERE username=? AND enabled=1',(username,)):
        db.execute('INSERT OR IGNORE INTO push_outbox(notification_id,provider) VALUES(?,?)',(notification,row['provider']))


def validate(provider,settings):
    if not isinstance(settings,dict):raise ValueError('Invalid settings')
    token=settings.get('token','');url=settings.get('url','');chat=settings.get('chat_id','')
    if any(not isinstance(v,str) or len(v)>2000 for v in (token,url,chat)):raise ValueError('Invalid settings')
    if provider=='telegram':
        import re
        if not re.fullmatch(r'[0-9]+:[a-zA-Z0-9_-]+',token) or not re.fullmatch(r'-?[0-9]+|@[a-zA-Z0-9_]+',chat):raise ValueError('Enter bot token and chat ID')
    else:
        parsed=public_net.endpoint(url)
        if provider=='discord' and (parsed.hostname!='discord.com' or not parsed.path.startswith('/api/webhooks/')):raise ValueError('Use a Discord webhook URL')
        if provider=='gotify' and not token:raise ValueError('Enter a Gotify application token')
    return {'url':url,'token':token,'chat_id':chat}


def send(provider,settings,text):
    if provider=='telegram':return public_net.request('https://api.telegram.org/bot'+settings['token']+'/sendMessage','POST',{'chat_id':settings['chat_id'],'text':text[:4000]})
    if provider=='discord':return public_net.request(settings['url'],'POST',{'content':text[:1900],'allowed_mentions':{'parse':[]}})
    if provider=='gotify':return public_net.request(settings['url'].rstrip('/')+'/message','POST',{'title':'AGMS','message':text,'priority':5},{'X-Gotify-Key':settings['token']})
    return public_net.request(settings['url'],'POST',text.encode(),{'Content-Type':'text/plain; charset=utf-8',**({'Authorization':'Bearer '+settings['token']} if settings['token'] else {})})


def deliver(connect):
    with connect() as db:
        # Include non-ticket bell events created after channel activation.
        for row in db.execute('''SELECT n.id,n.username,c.provider FROM workspace_notifications n JOIN push_channels c ON c.username=n.username WHERE c.enabled=1 AND n.created_at>=c.enabled_at AND n.created_at>unixepoch()-86400 AND n.read_at IS NULL ORDER BY n.created_at DESC LIMIT 100'''):
            db.execute('INSERT OR IGNORE INTO push_outbox(notification_id,provider) VALUES(?,?)',(row['id'],row['provider']))
        pending=db.execute('''SELECT o.*,n.username,n.message,n.ticket_comment,c.settings FROM push_outbox o JOIN workspace_notifications n ON n.id=o.notification_id JOIN push_channels c ON c.username=n.username AND c.provider=o.provider WHERE c.enabled=1 AND o.sent_at IS NULL AND o.attempts<5 AND o.next_attempt_at<=unixepoch() LIMIT 10''').fetchall()
    for row in pending:
        with connect() as db:
            claimed=db.execute('UPDATE push_outbox SET attempts=attempts+1,next_attempt_at=unixepoch()+300 WHERE notification_id=? AND provider=? AND attempts=? AND sent_at IS NULL',(row['notification_id'],row['provider'],row['attempts'])).rowcount
        if not claimed:continue
        try:send(row['provider'],json.loads(cipher().decrypt(row['settings'])),row['message']+'\n\n'+(row['ticket_comment'] or ''))
        except Exception:continue
        with connect() as db:db.execute('UPDATE push_outbox SET sent_at=unixepoch() WHERE notification_id=? AND provider=?',(row['notification_id'],row['provider']))


def router(connect,identity,csrf):
    from .features import json_body
    api=APIRouter()

    @api.get('/api/account/push')
    def channels(request:Request):
        username=identity(request)
        with connect() as db:
            rows={r['provider']:r for r in db.execute('SELECT * FROM push_channels WHERE username=?',(username,))}
        return {'channels':[{'provider':p,'configured':p in rows,'enabled':bool(rows[p]['enabled']) if p in rows else False} for p in PROVIDERS]}

    @api.put('/api/account/push/{provider}')
    async def save(request:Request,provider:str):
        username=identity(request);csrf(request);body=await json_body(request)
        if provider not in PROVIDERS or type(body.get('enabled')) is not bool:raise HTTPException(400,'Invalid push channel')
        with connect() as db:
            old=db.execute('SELECT settings FROM push_channels WHERE username=? AND provider=?',(username,provider)).fetchone()
            if body.get('keep_settings') and old:encrypted=old['settings']
            else:
                try:settings=validate(provider,body.get('settings'));encrypted=cipher().encrypt(json.dumps(settings).encode())
                except ValueError as e:raise HTTPException(400,str(e))
            db.execute('INSERT INTO push_channels(username,provider,settings,enabled,enabled_at) VALUES(?,?,?,?,unixepoch()) ON CONFLICT(username,provider) DO UPDATE SET settings=excluded.settings,enabled=excluded.enabled,enabled_at=excluded.enabled_at',(username,provider,encrypted,int(body['enabled'])))
            if not body['enabled']:db.execute('DELETE FROM push_outbox WHERE sent_at IS NULL AND provider=? AND notification_id IN (SELECT id FROM workspace_notifications WHERE username=?)',(provider,username))
        return {'ok':True}

    @api.post('/api/account/push/{provider}/test')
    async def test(request:Request,provider:str):
        username=identity(request);csrf(request)
        from .security_keys import throttle
        throttle(request)
        with connect() as db:row=db.execute('SELECT settings FROM push_channels WHERE username=? AND provider=?',(username,provider)).fetchone()
        if not row:raise HTTPException(404,'Save this channel first')
        import asyncio
        try:await asyncio.to_thread(send,provider,json.loads(cipher().decrypt(row['settings'])),'AGMS test notification')
        except Exception:raise HTTPException(502,'Push test failed. Check credentials and public HTTPS endpoint.')
        return {'ok':True}

    return api
