"""Optional TOTP and WebAuthn credentials; all challenges are one-use and expire."""
import base64,hashlib,hmac,json,secrets,time,struct,io
from urllib.parse import urlsplit,quote
import bcrypt
from fastapi import APIRouter,HTTPException,Request,Depends
from fastapi.responses import Response
from .integrations import cipher


def install(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS account_factors(username TEXT PRIMARY KEY,secret BLOB NOT NULL,enabled INTEGER NOT NULL DEFAULT 0,last_step INTEGER NOT NULL DEFAULT -1);
    CREATE TABLE IF NOT EXISTS security_challenges(id TEXT PRIMARY KEY,username TEXT,purpose TEXT NOT NULL,payload TEXT NOT NULL,expires_at INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS recovery_codes(username TEXT NOT NULL,code_hash TEXT NOT NULL,PRIMARY KEY(username,code_hash));
    CREATE TABLE IF NOT EXISTS passkeys(id TEXT PRIMARY KEY,username TEXT NOT NULL,name TEXT NOT NULL,public_key BLOB NOT NULL,sign_count INTEGER NOT NULL DEFAULT 0,created_at INTEGER NOT NULL DEFAULT (unixepoch()));
    ''')


def totp(secret,step):
    key=base64.b32decode(secret+'='*((8-len(secret)%8)%8))
    digest=hmac.new(key,struct.pack('>Q',step),hashlib.sha1).digest();offset=digest[-1]&15
    return str((struct.unpack('>I',digest[offset:offset+4])[0]&0x7fffffff)%1000000).zfill(6)


def verify_code(db,username,code):
    if not isinstance(code,str) or len(code)>100:return False
    row=db.execute('SELECT * FROM account_factors WHERE username=? AND enabled=1',(username,)).fetchone()
    if not row:return False
    secret=cipher().decrypt(row['secret']).decode();step=int(time.time())//30
    for candidate in (step-1,step,step+1):
        if candidate>row['last_step'] and hmac.compare_digest(totp(secret,candidate),code):
            return bool(db.execute('UPDATE account_factors SET last_step=? WHERE username=? AND last_step<?',(candidate,username,candidate)).rowcount)
    digest=hashlib.sha256(code.replace('-','').lower().encode()).hexdigest()
    return bool(db.execute('DELETE FROM recovery_codes WHERE username=? AND code_hash=?',(username,digest)).rowcount)


def password(db,username,value):
    row=db.execute('SELECT password_hash FROM users WHERE username=?',(username,)).fetchone()
    try:valid=isinstance(value,str) and row and bcrypt.checkpw(value.encode(),row['password_hash'].encode())
    except ValueError:valid=False
    if not valid:raise HTTPException(403,'Current password is incorrect')


def challenge(db,username,purpose,payload):
    db.execute('DELETE FROM security_challenges WHERE expires_at<unixepoch()')
    if db.execute('SELECT count(*) FROM security_challenges').fetchone()[0]>=2000:raise HTTPException(429,'Too many pending security requests')
    ident=secrets.token_urlsafe(32)
    db.execute('INSERT INTO security_challenges VALUES(?,?,?,?,unixepoch()+300)',(ident,username,purpose,json.dumps(payload)))
    return ident


def consume(db,ident,purpose,username=None):
    if not isinstance(ident,str):raise HTTPException(400,'Invalid or expired challenge')
    row=db.execute('SELECT * FROM security_challenges WHERE id=? AND purpose=? AND expires_at>unixepoch()',(ident,purpose)).fetchone()
    if not row or (username is not None and username!=row['username']):raise HTTPException(400,'Invalid or expired challenge')
    if not db.execute('DELETE FROM security_challenges WHERE id=?',(ident,)).rowcount:raise HTTPException(400,'Invalid or expired challenge')
    return row,json.loads(row['payload'])


attempts={}
def throttle(request:Request):
    if request.method=='GET':return
    now=time.monotonic();key=(request.client.host if request.client else 'unknown',request.url.path)
    if len(attempts)>2000:
        for k in list(attempts):
            if not attempts[k] or now-attempts[k][-1]>300:attempts.pop(k,None)
    recent=[t for t in attempts.get(key,[]) if now-t<300]
    if len(recent)>=20:raise HTTPException(429,'Too many security requests. Try again later.')
    attempts[key]=recent+[now]


def router(connect,identity,csrf,origin,session_response):
    from webauthn import generate_registration_options,verify_registration_response,generate_authentication_options,verify_authentication_response,options_to_json
    from webauthn.helpers.structs import PublicKeyCredentialDescriptor,AuthenticatorSelectionCriteria,UserVerificationRequirement,ResidentKeyRequirement
    api=APIRouter(dependencies=[Depends(throttle)]);rp=urlsplit(origin).hostname

    @api.get('/api/account/security')
    def status(request:Request):
        username=identity(request)
        with connect() as db:
            factor=db.execute('SELECT enabled FROM account_factors WHERE username=?',(username,)).fetchone()
            keys=[dict(r) for r in db.execute('SELECT id,name,created_at FROM passkeys WHERE username=? ORDER BY created_at',(username,))]
            count=db.execute('SELECT count(*) FROM recovery_codes WHERE username=?',(username,)).fetchone()[0]
        return {'totp_enabled':bool(factor and factor['enabled']),'passkeys':keys,'recovery_codes_remaining':count}

    @api.post('/api/account/security/totp/setup')
    async def setup(request:Request):
        username=identity(request);csrf(request);body=await request.json()
        secret=base64.b32encode(secrets.token_bytes(20)).decode().rstrip('=')
        with connect() as db:
            password(db,username,body.get('password'))
            if db.execute('SELECT 1 FROM account_factors WHERE username=? AND enabled=1',(username,)).fetchone():raise HTTPException(409,'Two-factor authentication is already enabled')
            db.execute('INSERT INTO account_factors(username,secret) VALUES(?,?) ON CONFLICT(username) DO UPDATE SET secret=excluded.secret,last_step=-1',(username,cipher().encrypt(secret.encode())))
        uri='otpauth://totp/'+quote('AGMS:'+username,safe='')+'?secret='+secret+'&issuer=AGMS&algorithm=SHA1&digits=6&period=30'
        return {'secret':secret,'uri':uri}

    @api.get('/api/account/security/totp/qr')
    def qr(request:Request):
        username=identity(request)
        with connect() as db:
            row=db.execute('SELECT secret FROM account_factors WHERE username=? AND enabled=0',(username,)).fetchone()
        if not row:raise HTTPException(404,'Start setup first')
        import qrcode,qrcode.image.svg
        secret=cipher().decrypt(row['secret']).decode();uri='otpauth://totp/'+quote('AGMS:'+username,safe='')+'?secret='+secret+'&issuer=AGMS'
        output=io.BytesIO();qrcode.make(uri,image_factory=qrcode.image.svg.SvgPathImage).save(output)
        return Response(output.getvalue(),media_type='image/svg+xml',headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})

    @api.post('/api/account/security/totp/enable')
    async def enable(request:Request):
        username=identity(request);csrf(request);body=await request.json()
        with connect() as db:
            row=db.execute('SELECT * FROM account_factors WHERE username=? AND enabled=0',(username,)).fetchone()
            step=int(time.time())//30
            if not row or not any(hmac.compare_digest(totp(cipher().decrypt(row['secret']).decode(),n),str(body.get('code',''))) for n in (step-1,step,step+1)):raise HTTPException(400,'Invalid authentication code')
            matched=max(n for n in (step-1,step,step+1) if hmac.compare_digest(totp(cipher().decrypt(row['secret']).decode(),n),str(body.get('code',''))))
            db.execute('UPDATE account_factors SET enabled=1,last_step=? WHERE username=?',(matched,username))
            codes=[secrets.token_hex(8) for _ in range(10)]
            db.execute('DELETE FROM recovery_codes WHERE username=?',(username,))
            db.executemany('INSERT INTO recovery_codes VALUES(?,?)',[(username,hashlib.sha256(c.encode()).hexdigest()) for c in codes])
        return {'recovery_codes':codes}

    @api.post('/api/account/security/totp/disable')
    async def disable(request:Request):
        username=identity(request);csrf(request);body=await request.json()
        with connect() as db:
            password(db,username,body.get('password'))
            if not verify_code(db,username,body.get('code')):raise HTTPException(403,'Invalid authentication code')
            db.execute('DELETE FROM account_factors WHERE username=?',(username,));db.execute('DELETE FROM recovery_codes WHERE username=?',(username,))
        return {'ok':True}

    @api.post('/api/account/security/passkeys/options')
    async def registration_options(request:Request):
        username=identity(request);csrf(request);body=await request.json()
        with connect() as db:
            password(db,username,body.get('password'))
            if db.execute('SELECT enabled FROM account_factors WHERE username=? AND enabled=1',(username,)).fetchone() and not verify_code(db,username,body.get('code')):raise HTTPException(403,'Invalid authentication code')
            keys=db.execute('SELECT id FROM passkeys WHERE username=?',(username,)).fetchall()
            if len(keys)>=10:raise HTTPException(400,'Maximum 10 passkeys')
            options=generate_registration_options(rp_id=rp,rp_name='AGMS',user_id=hashlib.sha256(username.encode()).digest(),user_name=username,exclude_credentials=[PublicKeyCredentialDescriptor(id=base64.urlsafe_b64decode(k['id']+'='*((4-len(k['id'])%4)%4))) for k in keys],authenticator_selection=AuthenticatorSelectionCriteria(user_verification=UserVerificationRequirement.REQUIRED,resident_key=ResidentKeyRequirement.REQUIRED))
            ident=challenge(db,username,'register',json.loads(options_to_json(options)))
        return {'challenge_id':ident,'options':json.loads(options_to_json(options))}

    @api.post('/api/account/security/passkeys')
    async def register_key(request:Request):
        username=identity(request);csrf(request);body=await request.json()
        with connect() as db:
            _,stored=consume(db,body.get('challenge_id'),'register',username)
        try:
            result=verify_registration_response(credential=body.get('credential'),expected_challenge=base64.urlsafe_b64decode(stored['challenge']+'='*((4-len(stored['challenge'])%4)%4)),expected_rp_id=rp,expected_origin=origin,require_user_verification=True)
        except Exception:raise HTTPException(400,'Passkey verification failed')
        ident=base64.urlsafe_b64encode(result.credential_id).decode().rstrip('=')
        name=body.get('name','Passkey')
        if not isinstance(name,str) or not 1<=len(name.strip())<=80:raise HTTPException(400,'Enter a passkey name')
        with connect() as db:
            if db.execute('SELECT count(*) FROM passkeys WHERE username=?',(username,)).fetchone()[0]>=10:raise HTTPException(400,'Maximum 10 passkeys')
            db.execute('INSERT INTO passkeys(id,username,name,public_key,sign_count) VALUES(?,?,?,?,?)',(ident,username,name.strip(),result.credential_public_key,result.sign_count))
        return {'ok':True}

    @api.delete('/api/account/security/passkeys/{ident}')
    async def delete_key(request:Request,ident:str):
        username=identity(request);csrf(request);body=await request.json()
        with connect() as db:
            password(db,username,body.get('password'))
            if db.execute('SELECT 1 FROM account_factors WHERE username=? AND enabled=1',(username,)).fetchone() and not verify_code(db,username,body.get('code')):raise HTTPException(403,'Invalid authentication code')
            db.execute('DELETE FROM passkeys WHERE id=? AND username=?',(ident,username))
        return {'ok':True}

    @api.post('/api/auth/passkey/options')
    async def authentication_options(request:Request):
        if request.headers.get('origin','').rstrip('/')!=origin:raise HTTPException(403,'Origin mismatch')
        options=generate_authentication_options(rp_id=rp,user_verification=UserVerificationRequirement.REQUIRED)
        with connect() as db:ident=challenge(db,None,'authenticate',json.loads(options_to_json(options)))
        return {'challenge_id':ident,'options':json.loads(options_to_json(options))}

    @api.post('/api/auth/passkey/verify')
    async def authenticate(request:Request):
        if request.headers.get('origin','').rstrip('/')!=origin:raise HTTPException(403,'Origin mismatch')
        body=await request.json();credential=body.get('credential')
        if not isinstance(credential,dict):raise HTTPException(400,'Invalid passkey')
        with connect() as db:
            _,stored=consume(db,body.get('challenge_id'),'authenticate')
            key=db.execute('SELECT k.*,s.verified_at FROM passkeys k JOIN account_security s ON s.username=k.username WHERE k.id=?',(credential.get('id'),)).fetchone()
        if not key or not key['verified_at']:raise HTTPException(401,'Passkey sign-in failed')
        try:
            result=verify_authentication_response(credential=credential,expected_challenge=base64.urlsafe_b64decode(stored['challenge']+'='*((4-len(stored['challenge'])%4)%4)),expected_rp_id=rp,expected_origin=origin,credential_public_key=key['public_key'],credential_current_sign_count=key['sign_count'],require_user_verification=True)
        except Exception:raise HTTPException(401,'Passkey sign-in failed')
        with connect() as db:
            if not db.execute('UPDATE passkeys SET sign_count=? WHERE id=? AND sign_count=?',(result.new_sign_count,key['id'],key['sign_count'])).rowcount:raise HTTPException(401,'Passkey sign-in failed')
        return session_response(key['username'])

    return api
