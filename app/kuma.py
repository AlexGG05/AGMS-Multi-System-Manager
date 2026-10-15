"""Personal dashboards using published Uptime Kuma status pages."""
import http.client
import ipaddress
import json
import re
import socket
import ssl
from urllib.parse import urlsplit, quote
from fastapi import APIRouter, HTTPException, Request


def source(value):
    if not isinstance(value, str) or len(value) > 1000:
        raise HTTPException(400, 'Enter a public Kuma status page URL')
    try:
        url = urlsplit(value)
        port = url.port
    except ValueError:
        raise HTTPException(400, 'Invalid status page URL')
    match = re.fullmatch(r'(.*)/status/([a-zA-Z0-9_-]+)/*', url.path)
    if url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password or port not in (None, 80, 443, 8080, 8443) or any(c.isspace() for c in value) or not match or url.query or url.fragment:
        raise HTTPException(400, 'Use the full public URL ending in /status/page-slug')
    return url, match[1], match[2].lower()


def public_json(url, path):
    """Resolve once and connect to that exact public IP; never follow redirects."""
    port = url.port or (443 if url.scheme == 'https' else 80)
    addresses = socket.getaddrinfo(url.hostname, port, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError('Public addresses required')
    address = addresses[0]
    with socket.socket(address[0], socket.SOCK_STREAM) as raw:
        raw.settimeout(5)
        raw.connect(address[4])
        stream = ssl.create_default_context().wrap_socket(raw, server_hostname=url.hostname) if url.scheme == 'https' else raw
        try:
            host = url.netloc.encode('idna').decode('ascii')
            stream.sendall(('GET ' + path + ' HTTP/1.1\r\nHost: ' + host + '\r\nAccept: application/json\r\nConnection: close\r\n\r\n').encode('ascii'))
            response = http.client.HTTPResponse(stream); response.begin()
            if response.status != 200:
                raise ValueError('Status page unavailable')
            payload = response.read(2 * 1024 * 1024 + 1)
            if len(payload) > 2 * 1024 * 1024:
                raise ValueError('Response too large')
            result = json.loads(payload)
            if not isinstance(result, dict):
                raise ValueError('Invalid response')
            return result
        finally:
            if stream is not raw:
                stream.close()


def read_page(value):
    url, prefix, slug = source(value)
    try:
        page = public_json(url, quote(prefix, safe='/') + '/api/status-page/' + slug)
        pulse = public_json(url, quote(prefix, safe='/') + '/api/status-page/heartbeat/' + slug)
        monitors = []
        for group in page.get('publicGroupList', []):
            for monitor in group.get('monitorList', []):
                ident = str(monitor['id'])
                history = pulse.get('heartbeatList', {}).get(ident, [])
                beat = history[-1] if history else {}
                monitors.append({'id': ident, 'name': str(monitor.get('name', ident)), 'group': str(group.get('name', '')), 'status': {0:'offline', 1:'online', 2:'pending', 3:'maintenance'}.get(beat.get('status'), 'unknown'), 'time': beat.get('time'), 'uptime': pulse.get('uptimeList', {}).get(ident + '_24')})
        return {'monitors': monitors}
    except (OSError, ValueError, KeyError, TypeError, AttributeError, http.client.HTTPException):
        raise HTTPException(502, 'Cannot load Kuma. Use a published status page on a public address with a valid TLS certificate; redirects are not followed.')


def router(connect, identity, csrf):
    api = APIRouter()

    @api.get('/api/kuma')
    def settings(request: Request):
        username = identity(request)
        with connect() as db:
            row = db.execute('SELECT settings FROM kuma_dashboards WHERE username=?', (username,)).fetchone()
        return {'entries': json.loads(row['settings']) if row else []}

    @api.put('/api/kuma')
    async def save(request: Request):
        username = identity(request); csrf(request)
        from .features import json_body
        body = await json_body(request)
        entries = body.get('entries')
        if not isinstance(entries, list) or len(entries) > 30:
            raise HTTPException(400, 'Choose up to 30 status entries')
        clean = []
        for entry in entries:
            if not isinstance(entry, dict) or any(not isinstance(entry.get(k), str) or not 1 <= len(entry[k].strip()) <= 100 for k in ('title', 'category')):
                raise HTTPException(400, 'Enter a title and category')
            source(entry.get('url'))
            ids = entry.get('monitors', [])
            if not isinstance(ids, list) or len(ids) > 500 or any(not isinstance(i, str) or not re.fullmatch(r'[0-9]{1,12}', i) for i in ids):
                raise HTTPException(400, 'Invalid monitor selection')
            header = entry.get('header_monitor')
            if header is not None and (not isinstance(header, str) or not re.fullmatch(r'[0-9]{1,12}', header)):
                raise HTTPException(400, 'Invalid header monitor')
            cleaned = {k: entry[k].strip() for k in ('title', 'category', 'url')} | {'monitors': list(dict.fromkeys(ids))}
            if header is not None:
                cleaned['header_monitor'] = header
            clean.append(cleaned)
        with connect() as db:
            from .operations import audit
            old=db.execute('SELECT settings FROM kuma_dashboards WHERE username=?',(username,)).fetchone()
            previous=json.loads(old['settings']) if old else []
            if previous!=clean:audit(db,'kuma:'+username,username,'status.updated',{'before':', '.join(e['title'] for e in previous),'after':', '.join(e['title'] for e in clean)})
            db.execute('INSERT INTO kuma_dashboards VALUES (?,?) ON CONFLICT(username) DO UPDATE SET settings=excluded.settings', (username, json.dumps(clean)))
        return {'ok': True}

    @api.post('/api/kuma/preview')
    async def preview(request: Request):
        identity(request); csrf(request)
        from .features import json_body
        import asyncio
        body = await json_body(request)
        return await asyncio.to_thread(read_page, body.get('url'))

    return api
