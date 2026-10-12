"""Encrypted integration profiles. The key is derived from SESSION_SECRET; back it up securely."""
import base64
import hashlib
import json
import os
import sqlite3
from cryptography.fernet import Fernet
from fastapi import HTTPException

KINDS = {"proxmox", "truenas", "arcane", "ssh"}
def cipher():
    secret=os.environ["SESSION_SECRET"].encode()
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(b"codex-homelab-profiles-v1:"+secret).digest()))
def init(db):
    db.execute("""CREATE TABLE IF NOT EXISTS integrations
        (id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, name TEXT NOT NULL,
         url TEXT NOT NULL, secret BLOB NOT NULL, options TEXT NOT NULL DEFAULT '{}')""")
def public(row):
    return {"id":row["id"],"kind":row["kind"],"name":row["name"],"url":row["url"],"configured":True}
def list_profiles(db):
    init(db)
    return [public(row) for row in db.execute("SELECT id,kind,name,url FROM integrations ORDER BY kind,name")]
def save(db, payload):
    from urllib.parse import urlsplit
    kind=payload.get("kind")
    name=str(payload.get("name","")).strip()
    url=str(payload.get("url","")).strip()
    secret=payload.get("secret")
    if kind not in KINDS or not 1<=len(name)<=80 or len(url)>512:
        raise HTTPException(400,"Invalid integration")
    parsed=urlsplit(url)
    if kind=="ssh":
        if parsed.scheme!="ssh" or not parsed.hostname or parsed.username or parsed.password:
            raise HTTPException(400,"Use ssh://hostname without embedded credentials")
    elif parsed.scheme not in ("https","http") or not parsed.hostname or parsed.username or parsed.password:
        raise HTTPException(400,"Invalid endpoint URL")
    ident=payload.get("id")
    init(db)
    existing=db.execute("SELECT secret FROM integrations WHERE id=?",(ident,)).fetchone() if isinstance(ident,int) else None
    if secret:
        if not isinstance(secret,str) or len(secret)>8192: raise HTTPException(400,"Invalid credential")
        encrypted=cipher().encrypt(secret.encode())
    elif existing:
        encrypted=existing["secret"]
    else:
        raise HTTPException(400,"Credential required")
    if existing:
        db.execute("UPDATE integrations SET kind=?,name=?,url=?,secret=? WHERE id=?",(kind,name,url,encrypted,ident))
        return ident
    cursor=db.execute("INSERT INTO integrations(kind,name,url,secret) VALUES (?,?,?,?)",(kind,name,url,encrypted))
    return cursor.lastrowid
