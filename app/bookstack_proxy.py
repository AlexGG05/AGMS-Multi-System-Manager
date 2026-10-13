"""Opt-in, fixed-origin BookStack proxy for authenticated AGMS users."""
import os
import re
from urllib.parse import urlsplit
import httpx
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import Response

UPSTREAM = "https://book.agrosskopf.de"
PREFIX = "/bookstack-proxy"
router = APIRouter()
ASSET_TYPES = ("text/html", "text/css", "application/javascript", "text/javascript")
BLOCKED = {"host", "connection", "transfer-encoding", "content-length", "content-encoding", "accept-encoding", "cookie", "authorization"}
STRIP_RESPONSE = {"content-security-policy", "content-security-policy-report-only", "x-frame-options", "content-length", "transfer-encoding", "content-encoding", "set-cookie", "location", "access-control-allow-origin"}
UPSTREAM_HOST = urlsplit(UPSTREAM).hostname

def rewrite_url(value):
    if value.startswith(UPSTREAM):
        return PREFIX + value[len(UPSTREAM):]
    if value.startswith("//" + UPSTREAM_HOST):
        return PREFIX + value[len("//" + UPSTREAM_HOST):]
    if value.startswith("/") and not value.startswith("//"):
        return PREFIX + value
    return value

def rewrite_html(html):
    # Rewrite URL-bearing HTML attributes, not arbitrary prose or JavaScript.
    html = re.sub(r'(?i)(\\b(?:href|src|action|poster)=)(["\\\'])([^"\\\']*)(\\2)', lambda m: m.group(1)+m.group(2)+rewrite_url(m.group(3))+m.group(4), html)
    return html.replace(UPSTREAM + "/", PREFIX + "/")

@router.api_route(PREFIX + "/{path:path}", methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"])
async def proxy(request: Request, path: str):
    if os.getenv("AGMS_BOOKSTACK_PROXY", "false").lower() != "true":
        raise HTTPException(404, "BookStack test proxy disabled")
    if not getattr(request.state, "agms_user", None):
        raise HTTPException(401, "Login required")
    if request.method not in ("GET", "HEAD"):
        origin = request.headers.get("origin", "")
        referer = request.headers.get("referer", "")
        host_origin = os.getenv("PUBLIC_ORIGIN", "").rstrip("/")
        if origin != host_origin and not referer.startswith(host_origin + PREFIX + "/"):
            raise HTTPException(403, "Cross-origin request rejected")
    if ".." in path.split("/") or "\\\\" in path:
        raise HTTPException(400, "Invalid path")
    url = UPSTREAM + "/" + path
    if request.url.query:
        url += "?" + request.url.query
    headers = {k:v for k,v in request.headers.items() if k.lower() not in BLOCKED}
    headers["accept-encoding"] = "identity"
    headers["host"] = UPSTREAM_HOST
    cookies = {}
    for key, value in request.cookies.items():
        if key.startswith("agms_book_"):
            cookies[key[len("agms_book_"):]] = value
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=False, trust_env=False) as client:
            upstream = await client.request(request.method, url, headers=headers, cookies=cookies, content=await request.body())
    except httpx.HTTPError:
        raise HTTPException(502, "BookStack upstream unavailable")
    response_headers = {k:v for k,v in upstream.headers.items() if k.lower() not in STRIP_RESPONSE}
    ctype = upstream.headers.get("content-type", "").lower()
    data = upstream.content
    if "text/html" in ctype:
        data = rewrite_html(data.decode("utf-8", errors="replace")).encode("utf-8")
    elif "text/css" in ctype:
        css = data.decode("utf-8", errors="replace")
        css = css.replace(UPSTREAM + "/", PREFIX + "/")
        css = re.sub(r'url\\(\\s*(["\\\']?)(/[^/)]+)\\1\\s*\\)',lambda m: "url("+m.group(1)+PREFIX+m.group(2)+m.group(1)+")",css)
        data = css.encode("utf-8")
    result = Response(content=data, status_code=upstream.status_code, headers=response_headers)
    if "location" in upstream.headers:
        loc = upstream.headers["location"]
        result.headers["location"] = rewrite_url(loc)
    for cookie in upstream.headers.get_list("set-cookie"):
        # Store BookStack cookies separately from AGMS session/CSRF cookies.
        name, _, rest = cookie.partition("=")
        if not name or not rest: continue
        cookie_value = rest.split(";",1)[0]
        attributes = rest.split(";")[1:]
        attrs = "; ".join(a for a in attributes if not a.strip().lower().startswith(("domain=", "path=", "samesite=", "secure", "httponly")))
        result.headers.append("set-cookie", "agms_book_" + name + "=" + cookie_value + "; Path=" + PREFIX + "/; Secure; HttpOnly; SameSite=Lax" + ("; " + attrs if attrs else ""))
    return result
