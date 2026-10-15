# Browser SSH and RDP

SSH is served by AGMS using AsyncSSH and the vendored xterm.js client. RDP uses Apache Guacamole's official JavaScript client and the bundled `guacd` service. No Guacamole web application, additional login or Guacamole database is required. Both use the existing AGMS account, homepage membership and tile minimum role. A homepage owner/editor explicitly shares use of its saved credentials with members allowed to open that tile; members cannot retrieve the secret.

## Deploy without changing existing data

Keep the existing `/data` volume, `SESSION_SECRET`, administrator credentials and public origin. Back up the SQLite database and encryption secret before upgrading. The migration only adds tables/columns; it does not recreate accounts, change tiers or reset homepages. Deploy both stacked changes together after review.

SSH needs no additional container. To enable RDP as well, use the provided override:

```sh
docker compose -f compose.yaml -f compose.remote.yaml up -d --build
```

For the ARM64 Arcane/image configuration, use `-f compose.arcane.yaml -f compose.remote.yaml` instead. `guacamole/guacd:1.6.0` provides both amd64 and arm64 images. Existing compose files continue working without the override; RDP then reports that the gateway is not configured. The guacd port is not published. Keep Docker's internal network and the AGMS server trusted; guacd is an internal protocol service, not a publicly authenticated API. Existing published-port/volume names are unchanged. The new override starts a second service, not a replacement volume or database.

The reverse proxy must support WebSocket upgrades on `/api/remote/tunnel` and preserve the public `Origin` and session cookie. A typical Nginx location has `proxy_http_version 1.1`, `proxy_set_header Upgrade $http_upgrade`, `proxy_set_header Connection "upgrade"` and a suitable `proxy_read_timeout`. Keep HTTPS enabled at the public origin. Access logs should omit query strings on the tunnel route: session tickets are single-use and cookie-bound, but should still not be logged unnecessarily.

## Configure a tile

1. Select the homepage and **Edit**. Add a connection or open its existing connection editor.
2. Select **SSH terminal** or **RDP (Guacamole)** as opening mode. Existing iFrame, external-tab and approved AGMS-Proxy modes remain available.
3. Choose **Configure connection**. The tile/mode is saved first; then enter host, port and account. Use a service account with the minimum required remote permissions.
4. An administrator approves the exact protocol/host/port in **Admin Panel → Remote destinations**, or with **Approve destination** in the connection dialog. LAN addresses are supported. Approval resolves and pins current IPs; revoke and reapprove after an IP change. Loopback, link-local, metadata, multicast, unspecified and reserved destinations cannot be approved.
5. Save credentials, leave editing and open the tile. Remote connections open inside AGMS's window manager. Opening an SSH/RDP tile again creates a separate session, subject to limits.

Passwords, private keys and passphrases are stored encrypted and never returned to the browser. Host, port, username and public key/certificate fingerprints are connection metadata visible only to members allowed to use the tile. Leaving all secret fields empty preserves credentials only for the unchanged protocol, host, port and username. Changing the target/account requires credentials again. **Remove saved credentials** erases the connection configuration and ends its sessions. Export/import includes tile metadata, never SSH/RDP credentials; imported or duplicated remote tiles require configuration again.

### SSH host key verification

Passwords and private keys (including encrypted keys with a passphrase) are supported. Paste the complete PEM/OpenSSH private key. Host verification is mandatory: obtain the server's SHA256 host-key fingerprint through a trusted channel, for example at the server console with:

```sh
ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub -E sha256
```

Enter just the `SHA256:…` fingerprint. Key decoding runs in a separate process with CPU/memory/time limits; excessively costly encrypted-key parameters are rejected rather than blocking the application. AGMS does not silently accept new/changed keys, use the server's SSH agent, load local default keys or run an interpolated shell command. On failure, check host reachability, key fingerprint, account credentials and the destination approval. Terminal data is streamed rather than stored in the database; the remote host may have its own logging policies.

### RDP certificate trust

RDP requires NLA and validates the remote TLS certificate. A Windows domain is optional. The recommended method for self-signed certificates, or certificates whose names differ from the pinned IP, is to enter the RDP certificate's **verified SHA256 fingerprint**. Obtain it from the server administrator through a trusted channel or inspect a trusted copy of the certificate:

```sh
openssl x509 -in server.crt -noout -fingerprint -sha256
```

Paste the fingerprint value (64 hexadecimal digits, optionally separated by colons), not a Windows SHA1 thumbprint. AGMS pins that exact certificate via Guacamole's `cert-fingerprints` parameter; `ignore-cert` remains false and trust-on-first-use remains disabled. A changed certificate requires explicit re-verification and configuration update. Guacamole/FreeRDP's certificate-name handling for IP connections can differ between releases, so an IP SAN alone may be insufficient.

Without a pin, the certificate must match the pinned destination as checked by FreeRDP and chain to a CA trusted by guacd. For a private CA, build a derived image; do not disable certificate verification:

```dockerfile
FROM guacamole/guacd:1.6.0
USER root
COPY rdp-ca.crt /usr/local/share/ca-certificates/rdp-ca.crt
RUN update-ca-certificates
USER guacd
```

Override `guacd.image` with that image. Remote targets never come from the browser tunnel payload. Certificate, NLA and login errors are shown as a failed connection without exposing upstream error details or credentials. The gateway's home is a temporary filesystem for FreeRDP runtime files; no credentials or trust-on-first-use store is persisted there. HTTP proxy variables are cleared for guacd because approved RDP destinations must be reached directly.

Clipboard, drive mapping, upload/download and audio redirection are deliberately disabled for this initial RDP integration. The browser receives the display stream and sends keyboard, mouse, resize, acknowledgement and sync instructions; connection-selection instructions are rejected after the server-controlled handshake. Display resize input is capped at 3840×2160, and mouse/key/acknowledgement input is validated before forwarding.

## Sessions and permissions

* At most eight pending/active remote sessions per account and twenty connection attempts per minute. These limits are enforced server-side in SQLite. The web desktop separately limits mounted windows to eight per tab.
* A connection ticket expires after thirty seconds and can be used once, only with the requesting user's exact signed session cookie and the configured public Origin. A remote session cannot outlive the eight-hour AGMS sign-in session.
* Every five seconds, active remote sessions recheck account existence, email verification, membership, tile minimum role, opening mode, connection version, target approval and logout revocation. Lost access ends the session. Credential changes and removal revoke existing leases.
* Closing a window releases its transport; minimizing or switching preserves it. Logout revokes leases belonging to that browser sign-in. Credentials and session tickets are not written to audit details. Account/homepage/tile deletion cleans up saved remote connections and active leases.
* A tier downgrade still preserves/read-enables existing homepages as before; editing their remote configuration obeys the same homepage limit rules as other edits.
* Use the existing single Uvicorn worker. SQLite stores limits/revocation, while each worker owns its live sockets. A reverse proxy restart or page refresh ends transports; remote-session resume across refresh/server restart is not implemented.

The SSH/RDP network path runs from the AGMS/guacd containers, so those containers must be able to reach approved LAN hosts. Apply network firewall rules in addition to the application allowlist. The Docker resource limits are starting points, not a capacity guarantee for eight high-resolution RDP desktops.

If an existing deployment uses a custom service name (for example `codex-homelab`), add the `GUACD_HOST`/`GUACD_PORT` environment to that existing service and add `guacd` on its Docker network. Do not launch a second dashboard with a fresh volume. The repository override uses the repository's existing service name `dashboard`.

For a development/build environment with an intercepting HTTPS proxy, the Dockerfile accepts an optional BuildKit secret `build_ca` containing the trusted CA bundle (`docker build --secret id=build_ca,src=/trusted/ca-bundle.pem ...`). It is used only during dependency installation and is not copied into the image. Normal builds do not require the secret.
