"""Bounded public HTTPS requests with pinned DNS, SNI and certificate verification."""
import http.client
import ipaddress
import json
import socket
import ssl
from urllib.parse import urlsplit, urljoin


def endpoint(value):
    if not isinstance(value, str) or len(value)>2000 or any(c.isspace() for c in value):
        raise ValueError('Invalid HTTPS address')
    url=urlsplit(value)
    if url.scheme!='https' or not url.hostname or url.username or url.password or url.fragment or url.port not in (None,443,8443,8006):
        raise ValueError('Use a public HTTPS address without credentials')
    return url


def connection(url):
    addresses=socket.getaddrinfo(url.hostname,url.port or 443,type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError('Private destinations are not supported')
    address=addresses[0]
    raw=socket.socket(address[0],socket.SOCK_STREAM)
    try:
        raw.settimeout(5);raw.connect(address[4])
        return ssl.create_default_context().wrap_socket(raw,server_hostname=url.hostname)
    except BaseException:
        raw.close();raise


def request(value,method='GET',payload=None,headers=None,redirects=0):
    url=endpoint(value)
    data=payload if isinstance(payload,bytes) else (json.dumps(payload).encode() if payload is not None else b'')
    if len(data)>65536:raise ValueError('Payload too large')
    fields={'Host':url.netloc.encode('idna').decode(),'Connection':'close','User-Agent':'AGMS/1.0','Accept':'application/json',**(headers or {})}
    if payload is not None:fields.update({'Content-Length':str(len(data)),'Content-Type':fields.get('Content-Type','application/json')})
    if any('\r' in str(v) or '\n' in str(v) for v in fields.values()):raise ValueError('Invalid headers')
    path=url.path or '/'
    if url.query:path+='?'+url.query
    with connection(url) as sock:
        sock.sendall((method+' '+path+' HTTP/1.1\r\n'+''.join(k+': '+v+'\r\n' for k,v in fields.items())+'\r\n').encode('ascii')+data)
        response=http.client.HTTPResponse(sock);response.begin()
        if response.status in (301,302,303,307,308) and redirects and method=='GET':
            return request(urljoin(value,response.getheader('Location','')),redirects=redirects-1)
        body=response.read(2*1024*1024+1)
        if len(body)>2*1024*1024:raise ValueError('Response too large')
        if not 200<=response.status<300:raise ValueError('Remote service rejected request')
        return json.loads(body) if body.strip() else {}
