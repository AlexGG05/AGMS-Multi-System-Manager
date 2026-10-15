"""Authorized service discovery, ticket attachments and notification preferences."""
import base64
import binascii
import json
import os
import re
import secrets
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from .mailer import send_email

PRIORITIES = ('low', 'normal', 'high', 'urgent')
MAX_IMAGE = 2 * 1024 * 1024
EMAIL_POLL_INTERVAL = 60
DEFAULT_PREFS = {'ticket_bell': True, 'other_bell': True, 'ticket_email': False, 'email_language': 'en'}


def install(db):
    columns = {r[1] for r in db.execute('PRAGMA table_info(support_tickets)')}
    for name, definition in [('priority', "TEXT NOT NULL DEFAULT 'normal'"), ('assigned_to', 'TEXT'), ('workspace_id', 'TEXT'), ('service_id', 'TEXT'), ('service_title', 'TEXT'), ('service_url', 'TEXT')]:
        if name not in columns:
            db.execute('ALTER TABLE support_tickets ADD COLUMN ' + name + ' ' + definition)
    db.executescript('''
    CREATE TABLE IF NOT EXISTS kuma_dashboards (username TEXT PRIMARY KEY, settings TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS ticket_attachments (
      id TEXT PRIMARY KEY, ticket_id TEXT NOT NULL, filename TEXT NOT NULL,
      content_type TEXT NOT NULL, content BLOB NOT NULL,
      created_at INTEGER NOT NULL DEFAULT (unixepoch())
    );
    CREATE INDEX IF NOT EXISTS attachments_ticket ON ticket_attachments(ticket_id);
    CREATE TABLE IF NOT EXISTS notification_preferences (
      username TEXT PRIMARY KEY, settings TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS notification_email_outbox (
      notification_id TEXT PRIMARY KEY, recipient TEXT NOT NULL,
      language TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, next_attempt_at INTEGER NOT NULL DEFAULT 0, sent_at INTEGER
    );
    ''')


def preferences(db, username):
    row = db.execute('SELECT settings FROM notification_preferences WHERE username=?', (username,)).fetchone()
    return {**DEFAULT_PREFS, **(json.loads(row['settings']) if row else {})}


async def json_body(request):
    content = bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content) > 9 * 1024 * 1024:
            raise HTTPException(413, 'Ticket payload is too large')
    try:
        body = json.loads(content)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(400, 'Invalid ticket JSON')
    if not isinstance(body, dict):
        raise HTTPException(400, 'Invalid ticket JSON')
    return body


def images(body):
    files = body.get('attachments', [])
    if not isinstance(files, list) or len(files) > 3:
        raise HTTPException(400, 'Choose up to 3 screenshots')
    result = []
    for file in files:
        if not isinstance(file, dict) or not isinstance(file.get('data'), str) or not isinstance(file.get('filename'), str):
            raise HTTPException(400, 'Invalid screenshot')
        encoded = file['data']
        if len(encoded) > ((MAX_IMAGE + 2) // 3) * 4:
            raise HTTPException(413, 'Each screenshot must be at most 2 MB')
        try:
            content = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error):
            raise HTTPException(400, 'Invalid screenshot')
        if not content or len(content) > MAX_IMAGE:
            raise HTTPException(413, 'Each screenshot must be at most 2 MB')
        if content.startswith(b'\x89PNG\r\n\x1a\n'):
            mime = 'image/png'
        elif content.startswith(b'\xff\xd8\xff'):
            mime = 'image/jpeg'
        elif content.startswith(b'RIFF') and content[8:12] == b'WEBP':
            mime = 'image/webp'
        else:
            raise HTTPException(400, 'Screenshots must be PNG, JPEG or WebP')
        name = re.sub(r'[^\w. -]', '_', file['filename'])[:120].strip() or 'screenshot'
        result.append((secrets.token_hex(12), name, mime, content))
    return result


def store_images(db, ticket_id, files):
    count = db.execute('SELECT COUNT(*) FROM ticket_attachments WHERE ticket_id=?', (ticket_id,)).fetchone()[0]
    if count + len(files) > 10:
        raise HTTPException(400, 'A ticket can have at most 10 screenshots')
    for ident, filename, mime, content in files:
        db.execute('INSERT INTO ticket_attachments(id,ticket_id,filename,content_type,content) VALUES(?,?,?,?,?)', (ident, ticket_id, filename, mime, content))


def visible_services(db, username):
    return db.execute('''SELECT n.id,n.workspace_id,n.title,n.url,n.open_mode,n.parent_id,w.name workspace_name
      FROM workspace_navigation n JOIN workspace_members m ON m.workspace_id=n.workspace_id
      JOIN workspaces w ON w.id=n.workspace_id WHERE m.username=? AND
      CASE m.role WHEN 'owner' THEN 2 WHEN 'editor' THEN 1 ELSE 0 END >=
      CASE n.min_role WHEN 'owner' THEN 2 WHEN 'editor' THEN 1 WHEN 'viewer' THEN 0 ELSE 99 END
      ORDER BY w.name,n.position,n.id''', (username,)).fetchall()


def ticket_service(db, username, body):
    wsid, ident = body.get('workspace_id'), body.get('service_id')
    if wsid is None and ident is None:
        return (None, None, None, None)
    if not isinstance(wsid, str) or not isinstance(ident, str):
        raise HTTPException(400, 'Choose an accessible service')
    service = next((s for s in visible_services(db, username) if s['workspace_id'] == wsid and s['id'] == ident and s['url']), None)
    if not service:
        raise HTTPException(404, 'WebUI not found')
    return (wsid, ident, service['title'], service['url'])


def queue_email(db, notification_id, username):
    prefs = preferences(db, username)
    if not prefs['ticket_email']:
        return
    row = db.execute('SELECT p.email,s.verified_at FROM account_profiles p LEFT JOIN account_security s ON s.username=p.username WHERE p.username=?', (username,)).fetchone()
    if row and row['email'] and row['verified_at']:
        db.execute('INSERT INTO notification_email_outbox(notification_id,recipient,language) VALUES(?,?,?)', (notification_id, row['email'], prefs['email_language']))


def deliver_pending(connect):
    # Failed SMTP delivery does not undo a ticket or lose the bell notification.
    with connect() as db:
        pending = db.execute('''SELECT o.*,n.message,n.ticket_comment,n.ticket_id,n.username,t.subject,num.number
          FROM notification_email_outbox o JOIN workspace_notifications n ON n.id=o.notification_id
          JOIN support_tickets t ON t.id=n.ticket_id JOIN support_ticket_numbers num ON num.ticket_id=t.id
          WHERE o.sent_at IS NULL AND o.attempts<5 AND o.next_attempt_at<=unixepoch() ORDER BY n.created_at LIMIT 10''').fetchall()
    translations = {'New ticket received': 'Neues Ticket eingegangen', 'Ticket reply received': 'Ticket-Antwort eingegangen', 'Ticket resolved': 'Ticket gelöst', 'More information is needed for your ticket': 'Weitere Informationen zu deinem Ticket werden benötigt'}
    for note in pending:
        with connect() as db:
            profile=db.execute('SELECT p.email,s.verified_at FROM account_profiles p LEFT JOIN account_security s ON s.username=p.username WHERE p.username=?',(note['username'],)).fetchone()
            if not preferences(db,note['username'])['ticket_email'] or not profile or not profile['verified_at'] or profile['email']!=note['recipient']:
                db.execute('DELETE FROM notification_email_outbox WHERE notification_id=?',(note['notification_id'],))
                continue
            claimed = db.execute('UPDATE notification_email_outbox SET attempts=attempts+1,next_attempt_at=unixepoch()+300 WHERE notification_id=? AND attempts=? AND sent_at IS NULL', (note['notification_id'], note['attempts'])).rowcount
        if not claimed:
            continue
        message = translations.get(note['message'], note['message']) if note['language'] == 'de' else note['message']
        origin=os.getenv('PUBLIC_ORIGIN','').rstrip('/')
        link='\n\n'+origin+'/static/tickets.html?ticket='+quote(note['ticket_id']) if origin else ''
        try:
            send_email(note['recipient'], f"AGMS · #{note['number']} · {message}", message + '\n\n' + note['subject'] + '\n\n' + (note['ticket_comment'] or '')+link)
        except (HTTPException,OSError,ValueError):
            continue
        with connect() as db:
            db.execute('UPDATE notification_email_outbox SET sent_at=unixepoch() WHERE notification_id=?', (note['notification_id'],))


def router(connect, identity, csrf, require_admin, authorized_ticket, is_admin):
    api = APIRouter()

    @api.get('/api/services')
    def services(request: Request):
        username = identity(request)
        with connect() as db:
            return {'services': [dict(row) for row in visible_services(db, username) if row['url']]}

    @api.get('/api/search')
    def search(request: Request, q: str = ''):
        username = identity(request)
        q = q.strip().casefold()
        if len(q) > 200:
            raise HTTPException(400, 'Search is too long')
        if not q:
            return {'results': []}
        with connect() as db:
            results = []
            truncated = False
            db.create_function('agms_casefold',1,lambda value:str(value or '').casefold(),deterministic=True)
            for row in visible_services(db, username):
                if q in (row['title'] + ' ' + (row['url'] or '') + ' ' + row['workspace_name']).casefold():
                    if len(results)>=60:
                        truncated=True
                        break
                    results.append({**dict(row), 'type': 'service' if row['url'] else 'group'})
            admin = is_admin(db, username)
            ticket_query = q[1:] if q.startswith("#") and q[1:].isdigit() else q
            rows = db.execute('''SELECT t.id,n.number,t.subject,t.status,t.priority,t.service_title FROM support_tickets t
              JOIN support_ticket_numbers n ON n.ticket_id=t.id WHERE (? OR t.username=?) AND
              instr(agms_casefold(CAST(n.number AS TEXT)||' '||t.subject||' '||COALESCE(t.service_title,'')),?)>0
              ORDER BY n.number DESC LIMIT 41''', (admin, username, ticket_query)).fetchall()
            truncated=truncated or len(rows)>40
            results.extend({**dict(row), 'type': 'ticket'} for row in rows[:40])
        return {'results': results,'truncated':truncated}

    @api.get('/api/notification-settings')
    def get_settings(request: Request):
        username = identity(request)
        with connect() as db:
            settings = preferences(db, username)
            row = db.execute('SELECT p.email,s.verified_at FROM account_profiles p LEFT JOIN account_security s ON s.username=p.username WHERE p.username=?', (username,)).fetchone()
        return {'settings': settings, 'email_available': bool(os.getenv('SMTP_PASSWORD') and row and row['email'] and row['verified_at'])}

    @api.put('/api/notification-settings')
    async def put_settings(request: Request):
        username = identity(request); csrf(request)
        settings = await json_body(request)
        if set(settings) != set(DEFAULT_PREFS) or any(type(settings[k]) is not bool for k in ('ticket_bell', 'other_bell', 'ticket_email')) or settings['email_language'] not in ('en', 'de'):
            raise HTTPException(400, 'Invalid notification settings')
        with connect() as db:
            db.execute('INSERT INTO notification_preferences(username,settings) VALUES(?,?) ON CONFLICT(username) DO UPDATE SET settings=excluded.settings', (username, json.dumps(settings)))
            if not settings['ticket_email']:
                db.execute('DELETE FROM notification_email_outbox WHERE sent_at IS NULL AND notification_id IN (SELECT id FROM workspace_notifications WHERE username=?)',(username,))
        return {'ok': True}

    @api.get('/api/tickets/{ticket_id}/attachments/{attachment_id}')
    def attachment(request: Request, ticket_id: str, attachment_id: str):
        username = identity(request)
        with connect() as db:
            authorized_ticket(db, ticket_id, username)
            row = db.execute('SELECT * FROM ticket_attachments WHERE ticket_id=? AND id=?', (ticket_id, attachment_id)).fetchone()
        if not row:
            raise HTTPException(404, 'Screenshot not found')
        return Response(bytes(row['content']), media_type=row['content_type'], headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff', 'Content-Disposition': "attachment; filename*=UTF-8''" + quote(row['filename']), 'Content-Security-Policy': "sandbox; default-src 'none'"})

    @api.put('/api/admin/tickets/{ticket_id}/metadata')
    async def metadata(request: Request, ticket_id: str):
        require_admin(request); csrf(request)
        body = await json_body(request)
        priority, assigned = body.get('priority'), body.get('assigned_to')
        if not isinstance(priority, str) or priority not in PRIORITIES or (assigned is not None and not isinstance(assigned, str)):
            raise HTTPException(400, 'Invalid ticket assignment')
        with connect() as db:
            authorized_ticket(db, ticket_id, identity(request))
            if assigned is not None and not is_admin(db, assigned):
                raise HTTPException(400, 'Choose an administrator')
            db.execute('UPDATE support_tickets SET priority=?,assigned_to=? WHERE id=?', (priority, assigned, ticket_id))
        return {'ok': True}

    from . import kuma
    api.include_router(kuma.router(connect, identity, csrf))
    return api
