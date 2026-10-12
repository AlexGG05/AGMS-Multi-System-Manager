# Arcane Integration — initial read-only implementation

This branch adds **authenticated environment discovery**. It does not implement container actions, update counts or detailed container telemetry yet.

## Configure

Add these optional variables to your existing deployment environment (do not overwrite your existing `.env`):

```env
ARCANE_URL=http://192.168.178.84:3552
ARCANE_API_KEY=replace-with-arcane-api-key
ARCANE_ALLOW_HTTP=true
```

The HTTP flag is only for a trusted private network. Use HTTPS with certificate verification if possible. `ARCANE_CA_BUNDLE` optionally specifies a CA bundle path within the container.

For an Arcane Compose deployment, set these through Arcane project environment variables; `compose.arcane.yaml` passes them to the dashboard.

## Behavior

- Login is required for `GET /api/arcane`.
- The API key is held on the backend and never sent to the browser.
- Environment discovery requests `GET /api/environments` with `X-Api-Key`.
- Non-success responses yield a server-side error instead of a fabricated empty list.
- No write operations exist in this version.

**Important:** Arcane's API routes and authentication can vary by release. Confirm `GET /api/environments` and `X-Api-Key` against your installed version's OpenAPI specification. Until verified against the real service, this feature should be considered a compatibility prototype.

## Verify

After redeploying, sign in, open **Docker environments**, and check for Arcane environments. If the result is 502, verify your actual Arcane route/authentication, TLS and connectivity. Avoid sharing the API key or authenticated responses.

The inventory cards below the Arcane section remain static; they must not be interpreted as live Docker status.
