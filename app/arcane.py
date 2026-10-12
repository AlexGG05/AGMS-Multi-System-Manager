"""Read-only Arcane connection. Never expose credentials or forward arbitrary URLs."""
import os
import httpx
from fastapi import HTTPException

def _settings():
    base = os.getenv("ARCANE_URL", "").strip().rstrip("/")
    key = os.getenv("ARCANE_API_KEY", "").strip()
    if not base or not key:
        return None
    if not base.startswith(("https://", "http://")):
        raise HTTPException(503, "ARCANE_URL must be an http(s) URL")
    if base.startswith("http://") and os.getenv("ARCANE_ALLOW_HTTP", "false").lower() != "true":
        raise HTTPException(503, "Arcane HTTP requires explicit ARCANE_ALLOW_HTTP=true on trusted LAN")
    return base, key

def _items(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for name in ("data", "items", "environments", "containers", "results"):
            value = payload.get(name)
            if isinstance(value, list):
                return value
            if isinstance(value, dict):
                nested = _items(value)
                if nested:
                    return nested
    return []

async def _get(client, base, key, path):
    resp = await client.get(base + path, headers={"X-Api-Key": key, "Accept": "application/json"})
    resp.raise_for_status()
    return resp.json()

async def get_arcane():
    settings = _settings()
    if not settings:
        return {"configured": False, "environments": [], "containers": [], "error": None}
    base, key = settings
    verify = os.getenv("ARCANE_CA_BUNDLE") or True
    try:
        async with httpx.AsyncClient(timeout=10, verify=verify, follow_redirects=False) as client:
            environments = _items(await _get(client, base, key, "/api/environments"))
            # An invalid / unauthorized response never gets misreported as an empty fleet.
            safe_envs = []
            for env in environments:
                if not isinstance(env, dict):
                    continue
                ident = str(env.get("id", ""))
                if not ident or not ident.replace("-", "").isalnum():
                    continue
                safe_envs.append({
                    "id": ident, "name": str(env.get("name") or env.get("displayName") or ident),
                    "status": str(env.get("status") or "unknown"),
                })
            return {"configured": True, "environments": safe_envs, "containers": [],
                    "error": None, "note": "Environment discovery active. Container endpoint awaits version-specific OpenAPI verification."}
    except (httpx.HTTPError, ValueError):
        raise HTTPException(502, "Arcane unavailable. Check network, TLS CA and API key.")
