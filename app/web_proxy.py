"""Restricted, opt-in reverse proxy for configured workspace WebUIs.

Only explicitly allowed HTTPS origins can be contacted. A proxy is not a
guarantee that every third-party application's UI will function embedded.
"""
import os
import re
import socket
import ipaddress
from urllib.parse import urlsplit, urlunsplit, urljoin
import httpx
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import Response

router = APIRouter()
HOP = {"host", "connection", "transfer-encoding", "content-length", "content-encoding",
       "accept-encoding", "cookie", "authorization", "proxy-authorization", "forwarded",
       "x-forwarded-for", "x-forwarded-host", "x-forwarded-proto"}
STRIP = {"content-security-policy", "content-security-policy-report-only", "x-frame-options",
         "content-length", "transfer-encoding", "content-encoding", "set-cookie", "location",
         "access-control-allow-origin", "clear-site-data"}
ROLE = {"viewer": 0, "editor": 1, "owner": 2}

def allowed_origins():
    origins = set()
    for raw in os.getenv("AGMS_PROXY_ALLOWED_ORIGINS", "").split(","):
        raw = raw.strip().rstrip("/")
        u = urlsplit(raw)
        if (u.scheme == "https" and u.hostname and not u.username and not u.password
                and not u.path and not u.query and not u.fragment):
            origins.add(raw.lower())
    return origins

def rewrite_location(location, upstream, prefix):
    absolute = urljoin(upstream + "/", location)
    if absolute == upstream or absolute.startswith(upstream + "/") or absolute.startswith(upstream + "?"):
        return prefix + absolute[len(upstream):]
    return location

def rewrite_markup(text, upstream, prefix):
    text = text.replace(upstream + "/", prefix + "/")
    text = re.sub(r'(?i)(\\b(?:href|src|action|poster)=)(["\\\'])(/[^"\\\']*)(\\2)',
                  lambda m: m.group(0) if m.group(3).startswith(prefix + "/") else m.group(1) + m.group(2) + prefix + m.group(3) + m.group(4), text)
    return text

def setup(connect, require):
    @router.api_route("/web-proxy/{wsid}/{itemid}", methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"])
    @router.api_route("/web-proxy/{wsid}/{itemid}/{path:path}", methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"])
    async def web_proxy(request: Request, wsid: str, itemid: str, path: str = ""):
        username = require(request)
        with connect() as db:
            member = db.execute("SELECT role FROM workspace_members WHERE workspace_id=? AND username=?",
                                (wsid, username)).fetchone()
            item = db.execute("SELECT url,min_role,open_mode FROM workspace_navigation WHERE workspace_id=? AND id=?",
                              (wsid, itemid)).fetchone()
        if not member or not item or item["open_mode"] != "proxy" or ROLE[member["role"]] < ROLE.get(item["min_role"], 99):
            raise HTTPException(404, "WebUI not found")
        base = urlsplit(item["url"])
        origin = urlunsplit((base.scheme, base.netloc, "", "", "")).lower()
        with connect() as db:
            approved = db.execute("SELECT 1 FROM proxy_allowed_origins WHERE origin=?", (origin,)).fetchone()
        if ((not approved and origin not in allowed_origins()) or base.scheme != "https" or base.username or base.password
                or base.path not in ("", "/") or base.query or base.fragment):
            raise HTTPException(403, "Proxy origin not allowed or URL contains a path")
        # Refuse localhost/private/link-local destinations even if an admin accidentally approves them.
        try:
            addresses = socket.getaddrinfo(base.hostname, base.port or 443, type=socket.SOCK_STREAM)
            if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
                raise HTTPException(403, "Private or non-public proxy destinations are blocked")
        except socket.gaierror:
            raise HTTPException(502, "Proxy hostname could not be resolved")
        if ".." in path.split("/") or "\\\\" in path:
            raise HTTPException(400, "Invalid path")
        prefix = f"/web-proxy/{wsid}/{itemid}"
        public_origin = os.getenv("PUBLIC_ORIGIN", "").rstrip("/")
        if request.method not in ("GET", "HEAD"):
            origin_header = request.headers.get("origin", "")
            referer = request.headers.get("referer", "")
            if origin_header != public_origin and not referer.startswith(public_origin + prefix + "/"):
                raise HTTPException(403, "Cross-origin request rejected")
        target = origin + "/" + path
        if request.url.query:
            target += "?" + request.url.query
        headers = {k: v for k, v in request.headers.items() if k.lower() not in HOP and not k.lower().startswith("x-forwarded-")}
        headers["accept-encoding"] = "identity"
        headers["host"] = base.netloc
        cookie_prefix = "agms_proxy_" + itemid + "_"
        cookies = {key[len(cookie_prefix):]: val for key, val in request.cookies.items() if key.startswith(cookie_prefix)}
        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=False, trust_env=False) as client:
                upstream = await client.request(request.method, target, headers=headers, cookies=cookies,
                                                content=await request.body())
        except httpx.HTTPError:
            raise HTTPException(502, "Proxy upstream unavailable")
        response_headers = {k: v for k, v in upstream.headers.items() if k.lower() not in STRIP}
        ctype = upstream.headers.get("content-type", "").lower()
        data = upstream.content
        if "text/html" in ctype or "text/css" in ctype:
            data = rewrite_markup(data.decode("utf-8", errors="replace"), origin, prefix).encode("utf-8")
        result = Response(content=data, status_code=upstream.status_code, headers=response_headers)
        if "location" in upstream.headers:
            result.headers["location"] = rewrite_location(upstream.headers["location"], origin, prefix)
        for cookie in upstream.headers.get_list("set-cookie"):
            name, sep, value = cookie.partition("=")
            if not sep or not name or not re.fullmatch(r"[A-Za-z0-9_\\-]+", name):
                continue
            cookie_value = value.split(";", 1)[0]
            attrs = [a.strip() for a in value.split(";")[1:]]
            expires = [a for a in attrs if a.lower().startswith(("expires=", "max-age="))]
            result.headers.append("set-cookie", cookie_prefix + name + "=" + cookie_value +
                                  "; Path=" + prefix + "/; Secure; HttpOnly; SameSite=Lax" +
                                  ("; " + "; ".join(expires) if expires else ""))
        return result
    return router
