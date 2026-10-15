# AGMS — Multi System Manager

Lightweight, self-hosted homelab dashboard. Runs on Raspberry Pi OS 64-bit (ARM64) with Docker Compose.

## Implemented
- Personal and shared homepages, service groups, favorites, tile/list views and navigation import/export
- Embedded WebUIs, external links and administrator-approved HTTPS proxy origins
- Browser SSH (password/private key), integrated Guacamole RDP and encrypted per-homepage connections
- Explicit homepage edit mode with tile/group pencils, one adaptive creation form, independent favorite sizes and an optional multi-window desktop
- Multi-user accounts, team roles, email verification/recovery and optional TOTP/passkeys
- Administrator panel, support tickets, comments, screenshots, service context and notifications
- Global search, configurable homepage widgets and English/German interface
- Service reachability, public certificate/domain expiry watches and Uptime Kuma pages with native heartbeat strips
- Homepage audit history and opt-in ntfy, Gotify, Telegram and Discord notifications
- Optional API integrations for Proxmox, Arcane and TrueNAS; availability depends on configured endpoints/API compatibility
- Persistent SQLite storage and ARM64 Docker deployment

SSH/RDP setup and security: [Browser remote access](docs/REMOTE-ACCESS.md). Editing, mobile controls and window management: [Workspace desktop](docs/WORKSPACE-DESKTOP.md). FRITZ!Box telemetry and remote-session resume across page/server restart are not implemented.

## Requirements
- Raspberry Pi OS 64-bit, Docker Engine and Compose plugin
- Reachable Proxmox API and, if using remote access, a **proper HTTPS reverse proxy**
- For Proxmox, a dedicated *read-only* API token with audit permissions for the cluster/resources it needs

## Install

```bash
sudo apt update
sudo apt install -y docker.io docker-compose-plugin openssl
sudo systemctl enable --now docker
git clone https://github.com/AlexGG05/AGMS-Multi-System-Manager.git codex-homelab
cd codex-homelab
cp .env.example .env
openssl rand -hex 32
```

If your distro lacks `docker-compose-plugin`, follow Docker's official Debian installation guide for the Compose plugin.

**This archive is the source**, so if downloaded as a ZIP instead of a Git repository, unzip it and skip the `git clone` step.

Edit `.env`:
- `SESSION_SECRET`: output of `openssl rand -hex 32`
- `ADMIN_PASSWORD`: a unique password at least 16 characters long
- `PUBLIC_ORIGIN`: **exact** browser origin of your HTTPS site, e.g. `https://home.example.com`
- `COOKIE_SECURE=true` (required for HTTPS)
- `ADMIN_USERNAME`: your chosen login name
- Optional `PVE_*` variables for Proxmox

Start:

```bash
docker compose up -d --build
docker compose logs -f dashboard
```

Dashboard listens on **127.0.0.1:8080** by default, which is only accessible from the Pi itself. Do not expose it directly to the internet.

### Local + remote HTTPS

Recommended: put the dashboard behind your existing Nginx reverse proxy on Docker-Edge and Cloudflare Tunnel, or another trusted HTTPS reverse proxy. For a reverse proxy on a *different machine*, change the Compose port mapping to:

```yaml
ports:
  - "PI_LAN_IP:8080:8080"
```

Replace `PI_LAN_IP` with the Pi's actual LAN address. Firewall this port so **only your reverse proxy's IP** can connect. Ensure your reverse proxy forwards requests to `http://PI_LAN_IP:8080`, sets `Host` and `X-Forwarded-Proto`, and serves HTTPS. `PUBLIC_ORIGIN` must exactly match the HTTPS URL users browse.

For local clients, use the **same HTTPS hostname** via split DNS / local DNS override pointing to your reverse proxy. If local and remote browser origins differ, login Origin checks will reject the other origin. Avoid bypassing HTTPS or disabling secure cookies.

If you expose the service through Cloudflare, add Cloudflare Access or an equivalent identity/access policy **in front of** the dashboard. Avoid public access to administrative interfaces without an additional access layer.

### Proxmox cluster monitoring

Create a dedicated token in Proxmox (`Datacenter > Permissions > API Tokens`) for a non-root service account. Give it only `PVEAuditor` (or a smaller custom audit role) at the appropriate cluster path, and check token privilege separation / ACL propagation.

```env
PVE_URL=https://proxmox-node-or-cluster-api.example:8006
PVE_TOKEN_ID=dashboard@pve!monitor
PVE_TOKEN_SECRET=YOUR_TOKEN_SECRET
```

Proxmox often uses a self-signed certificate. **Do not disable TLS verification.** Install a valid cert or provide your trusted CA bundle:
1. Put your CA cert in a directory mounted read-only into the container.
2. Set `PVE_CA_BUNDLE=/certs/ca.pem`.
3. Add Compose volume mapping `- ./certs:/certs:ro` under dashboard volumes.

API calls target `/api2/json/cluster/resources` on one reachable cluster node. The cluster API returns resources from all nodes. This is read-only.

### Add application URLs
Log in, choose **Service URLs**, and set a full `https://...` URL for each service (Vaultwarden, Zabbix, Arcane, Guacamole, etc.). Changes persist in the Docker volume.

### Security notes
- Never publish `.env`, API tokens, or the SQLite database.
- The admin password in `.env` is used **only on first startup** to seed the database. Editing it later does not reset the password.
- The configured administrator is seeded on first startup. Additional users register and verify their email; management access is role-based.
- Login rate limiting is in memory per process; put rate limits and MFA/Access in the reverse proxy for internet-facing deployment.
- Homepage membership and owner/editor/viewer roles control access and editing.
- `PUBLIC_ORIGIN` must exactly match your HTTPS site; no trailing slash.
- Back up the Docker volume regularly.

### Backup
```bash
docker compose stop dashboard
docker run --rm -v codex-homelab_dashboard_data:/source:ro -v "$PWD":/backup alpine tar czf /backup/dashboard-backup.tar.gz -C /source .
docker compose start dashboard
```
Volume name can vary by Compose project; verify with `docker volume ls`.

### Upgrade
```bash
docker compose up -d --build
```

### Admin Panel and tickets

The homepage sidebar offers **Create Ticket** to signed-in users. Tickets receive a sequential ticket number and contain a subject (1–200 characters), a description (1–10,000 characters) and a category: Problem, Idea, Wish or Other. They are stored in SQLite. The ticket overview shows number and subject; selecting a ticket opens its description, status and comment history. New tickets start Open and notify administrators through the notification bell. Administrators can set Open, In progress, Waiting for feedback or Resolved. Requesting feedback or resolving a ticket requires a saved comment and notifies the creator with a snapshot of the latest comment. Creators can open their own tickets under My tickets and reply while a ticket is Waiting for feedback; a reply returns it to In progress and notifies administrators. Other users cannot read or comment on the ticket.

Accounts with the `admin` role can open **Admin Panel**, then select **Proxy requests**, **Users** or **Tickets**. Administrative APIs enforce that role server-side. English is the default language; the language selector switches the interface to German.

Run the admin/ticket API regression tests after installing `requirements.txt`:

```bash
python -m unittest discover -s tests -v
```

The tests use an isolated temporary SQLite database and do not need external integrations.

### Bitwarden/Vaultwarden inside embedded WebUIs

Embedded services now open at separate AGMS addresses (`/webui/<workspace>/<item>/`). These links restore the correct service after login or reload and enforce workspace membership and the WebUI's minimum role.

Bitwarden browser 2026.9.3 selects inline-menu login suggestions using the outer tab's URL, not solely the iframe URL ([official source](https://github.com/bitwarden/clients/blob/browser-v2026.9.3/apps/browser/src/autofill/background/overlay.background.ts#L583)). A proxy additionally changes the iframe's URL to an AGMS URL.

Open a service and choose **Password manager setup** in its toolbar. Add the displayed website and AGMS URLs to that service's existing vault entry, using **Starts with** URI matching for each. For a proxied service, also add the displayed proxy URL. Keep the trailing slash, which separates each service's address. Configure each service independently; avoid matching every service to the entire AGMS domain.

AGMS neither reads nor stores vault credentials. The extension still controls field detection, site permissions and whether its inline menu appears. The AGMS routes, copied URLs and iframe/proxy restoration were browser-tested with fixture login pages; the user's installed Bitwarden extension and live remote login pages were not tested from the cloud environment.

The ARM64 workflow publishes `ghcr.io/alexgg05/agms-multi-system-manager:latest` and also retains the previous `codex-agrosskopf-dashboard:latest` tag for existing installations. Switch Compose to the new image only after the GitHub Actions build succeeds. Keep the existing Compose project name and data volume when updating.

### Ticket tools, search and service status

- **Report a problem** in a WebUI's toolbar preselects that service. The ticket stores its title and URL as context. Administrators can set priority and assign an administrator.
- Attach up to three PNG, JPEG or WebP screenshots per submission (2 MB each, at most ten per ticket). Screenshots are stored in SQLite and are only accessible to the creator and administrators. They can also accompany a feedback reply. A reverse proxy must allow the application's maximum 9 MB ticket request size; for Nginx, configure an appropriate `client_max_body_size`, such as `10m`.
- **Search everything** (or Ctrl/Cmd+K on the dashboard) searches permitted services, groups and ticket subjects/numbers across homepages. Normal users see their own tickets; administrators can search all tickets.
- **Notification settings** are available in the sidebar and the bell menu. Bell categories can be switched independently. Ticket emails default to off and require configured SMTP and a verified email address. Email language can be English or German. Failed delivery is queued for up to five attempts, with a five-minute retry delay; ticket actions and bell notifications remain available. SMTP delivery was verified with mocked success/failure, not a live mail server.
- **Monitoring** is the single sidebar tab for Uptime Kuma cards, followed by certificate/domain watches. The duplicate service-reachability list has been removed from this view; reachability remains on individual homepage tiles. Public checks retain TLS verification and private-address restrictions.

Existing users, ticket numbers, descriptions and comments are preserved by additive SQLite migrations. No additional Compose volume or dependency is required.

### Uptime Kuma dashboards

Open **Monitoring → Add status entry**. Choose a custom category name
(for example `vHosts`) or a monitor as the card heading, and the full published Kuma URL such as
`https://status.example.com/status/homelab`. Select **Load monitors** to choose
individual monitors, or leave all unselected to show the entire page with its
Kuma groups. Multiple entries can use the same page with different selections.
Configurations are personal to each AGMS user and can be edited or removed.
**Refresh Kuma** updates the displayed state and 24-hour uptime; Kuma itself may
cache page metadata for five minutes and heartbeat data for one minute.

Only monitors published on the selected public status page are available. AGMS
retrieves the public JSON endpoints without Kuma credentials. The server must
reach the page using a public IP and valid TLS certificate. Private/loopback
addresses, redirects, embedded credentials and unsupported ports are rejected.
Ports 80, 443, 8080 and 8443 are supported. Reverse-proxy subpaths are supported
when the URL ends in `/status/<slug>`; custom-domain root URLs need that explicit
path too. Certificate and domain watches are displayed directly below Kuma.

### Proxy start paths and Uptime Kuma administration

A proxied WebUI can use a start path, for example
`https://kuma.example.com/dashboard`. Approval still applies only to the HTTPS
origin (`https://kuma.example.com`); requests for assets and WebSockets remain
rooted at that origin. AGMS preserves the application's original HTML base and relative navigation.
For HTML explicitly identifying itself as **Uptime Kuma**, the proxy sets a
Kuma-specific Vue Router base so `/dashboard` and subsequent routes remain
inside the AGMS proxy namespace. Other applications, including SABnzbd, do not
receive this added base. Proxied HTML is served with `Cache-Control: no-store`
and without upstream cache validators, so transformed older pages cannot mask
proxy updates. Conditional upstream requests are omitted by the proxy.
The Kuma administration dashboard is separate from public status-page entries:
those still require a published `/status/<slug>` URL.

For a parent/group monitor such as `Hosts`, edit the status entry and set
**Category heading → Monitor as heading**. Load the monitors, then select
**Header monitor**. The card heading displays that monitor's current name,
status and 24-hour uptime; it is excluded from the child rows even when selected
in the monitor list. The remaining selection still controls which children are
shown. **Custom category name** restores a manually named heading using one **Category name** field. Existing entries keep
their manual names until explicitly changed. A removed/unpublished header monitor
shows a warning while retaining the saved title and child list.

Use the **↑ / ↓** buttons in a Kuma card's header to move it earlier or later.
Changes are saved immediately for the current user and survive reloads. The grid
uses the saved entry order, including entries with the same category name.
The first/last position disables the corresponding button. If saving fails,
the existing order remains visible and an error is displayed.

Entire Kuma status-page cards can also be dragged using the **⠿** handle at the
left of their heading. Drag onto another card to insert the entire page at that
position, including its monitor list and header-monitor configuration. This
works with mouse and touch; the destination is highlighted and the order is
saved on release. The arrow buttons remain available for keyboard use.

Kuma cards use a responsive masonry layout: each subsequent entry is placed in
the shortest available column, directly below the preceding card with a 16px
gap (12px on small screens). Cards no longer wait for the tallest card in a row.
The layout updates when card content, translations or available width change.
Saved entry order and drag/move controls remain in effect; narrow screens use a
single column.

### Monitoring and automatic refresh

The **Monitoring** sidebar tab combines Kuma status-page cards with certificate/domain
expiry watches directly below them. The profile controls automatic refresh: disabled, 30 seconds,
1, 2 or 5 minutes; the default is 1 minute. Checks run while the dashboard/status
or monitoring page is visible. Editing a monitoring form pauses its automatic
refresh. Status requests use the existing public-address restrictions and TLS
verification. The latest service check is retained for tile indicators and
summary widgets; the separate AGMS history screen/API has been removed.

Kuma cards instead show the latest **up to 100 actual heartbeats** returned by
Kuma's published status-page API, oldest to newest. Strips appear for individual
monitors and for a monitor used as the card heading. Green means online, red
offline, amber pending and blue maintenance; unknown is gray. Hover a segment for
the source timestamp and latency where available. No local reachability samples
or invented green segments are substituted for missing Kuma history.

Dependencies are within a homepage, require editing rights and reject cycles.
Only relationships between services visible to the viewer are returned.

Certificate watches accept public HTTPS URLs. Domain watches use the public
RDAP registry service (`rdap.org` and safely followed public HTTPS redirects).
Not every registry publishes expiration dates. In particular, `.de` domains do
not publish a public expiry date, so AGMS displays a specific explanation instead
of suggesting a connection failure. A **Registrar renewal date** can be entered
or cleared on each domain card. That date is explicitly labelled manual, persists
across checks and participates in the same 30-day bell/push warnings. Obtain it
from the registrar account or invoice; it is not inferred from a TLS certificate. Unavailable/invalid TLS or registry
responses show an explicit error instead of an invented date. Background checks
run on due watches every six hours, and the bell/opt-in push channels warn within
30 days of a known expiration. Manual checks are available in Monitoring.

### Profile: widgets, push and optional sign-in security

**Dashboard preferences** selects homepage widgets: own ticket counts, service
status, expiry warnings, Proxmox summary, Arcane container counts and SABnzbd
queue summary. Widgets default to off. Each API widget has a personal connection
in the profile: public HTTPS base URL and encrypted API credentials. Proxmox uses
a read-only `user@realm!token-id=token-secret` token; Arcane uses an API key with
read access to environments and containers. The central server configuration is
an administrator-only fallback for Proxmox/Arcane. No service-control actions are
exposed by these widgets. Existing SABnzbd connections are preserved.

**Push notifications** supports any combination of ntfy (full topic URL and
optional bearer token), Gotify (server base URL and application token), Telegram
(bot token and chat ID) and Discord (webhook URL). Each channel is explicitly
opt-in, has a test button and can be disabled independently. Secrets are encrypted
with a key derived from `SESSION_SECRET` and are not returned to the browser.
Existing saved credentials can be retained without re-entering them. Failed
notifications retry up to five times at five-minute intervals. Public HTTPS
endpoints with verified certificates are required; private-IP destinations are
blocked. Tests use fixtures/mocks rather than live external push accounts.

**Sign-in security** offers optional TOTP and passkeys. TOTP enrollment requires
the current password and confirmation of an authenticator code. A QR code/manual
secret and ten single-use recovery codes are provided. TOTP secrets are encrypted;
recovery codes are hashed and TOTP steps cannot be reused. Password sign-in asks
for an authenticator or recovery code when TOTP is enabled. Disabling it requires
the current password and a fresh authentication/recovery code.

Passkey enrollment requires the current password and, if enabled, TOTP/recovery
verification. WebAuthn challenges expire after five minutes and are single-use;
the origin/RP ID and device user verification are checked. A verified passkey can
sign in without the password/TOTP prompt. Passkeys can be named and removed in
the profile. Production requires HTTPS at the stable `PUBLIC_ORIGIN`; changing
the hostname means existing passkeys need re-enrollment for the new RP ID.
Back up the database and `SESSION_SECRET` together: changing the secret prevents
decryption of stored integration/push/TOTP credentials. Browser tests use a
virtual WebAuthn authenticator, not a user's physical device or cloud account.

### Administrator change history

**Admin Panel → Change history** displays homepage/status-page tiles with the
last editing account and timestamp. Opening one shows a paginated event list:
homepage creation/rename/deletion, added/removed/changed/reordered navigation
entries, team membership/invitations and personal Kuma status-page
configuration. Deleted homepages retain their recorded events. Logs are written
with the successful database mutation; rejected changes do not produce events.
This records activity from installation of this feature onward and does not
reconstruct earlier edits. Non-administrators cannot access these logs.

### Regression validation

Run the API, migration and authorization tests in an isolated development environment:

```bash
python -m unittest discover -s tests -v
```

The browser workflow additionally covers TOTP/recovery, virtual-authenticator
WebAuthn registration/sign-in, profile settings, monitoring, widgets and admin
history. Install Playwright outside the repository if needed, provide a Chromium
executable, then run the fixture server and browser in separate terminals:

```bash
python tests/serve_operations_fixture.py
PLAYWRIGHT_MODULE=/path/to/node_modules/playwright CHROMIUM_PATH=/usr/bin/chromium node tests/browser_kuma_history.cjs
PLAYWRIGHT_MODULE=/path/to/node_modules/playwright CHROMIUM_PATH=/usr/bin/chromium node tests/browser_operations.cjs
PLAYWRIGHT_MODULE=/path/to/node_modules/playwright CHROMIUM_PATH=/usr/bin/chromium node tests/browser_refresh.cjs
```

The fixture uses localhost:8082, a temporary database and test-only credentials;
it disables real push delivery and external expiry checks. Use a separate test
process, never import the fixture into a production application process.

Personal homepage API widgets for SABnzbd, Proxmox and Arcane can be configured in Profile → Dashboard preferences. Each connection is private to its account; API credentials are encrypted and never returned to the browser. Use a public HTTPS endpoint with trusted TLS. Proxmox expects a read-only `user@realm!token-id=token-secret` token; Arcane uses an API key with environment/container read access. Blank credentials preserve an existing connection only when the URL is unchanged. The central Proxmox/Arcane server configuration remains an administrator-only fallback. Service dependencies have been removed from Monitoring.

The Proxmox homepage widget separates total/running QEMU VMs and LXC containers, and shows node count, average node CPU utilization, and RAM usage (used/total memory across nodes). Missing utilization data is displayed as an em dash.

### Legal pages

All AGMS pages include a static footer linking to the public `/imprint` and `/privacy` pages (German aliases: `/impressum`, `/datenschutz`). They are accessible without a session, including from registration and sign-in, and use the existing English/German language preference. Footer links and the default English text remain usable without JavaScript. The documents use the operator details and policy supplied in the PDFs, with self-hosting clarified and AGMS account, browser storage, tickets, security, API and optional push processing added. Source attribution is retained. Review the content when infrastructure, external providers or retention practices change. The original PDFs are not published.

### Review and validation for SSH/RDP and issue #8

After validation on review branches, the combined changes are integrated directly into `main` at the project owner’s request. Production deployment remains an operator action. See [implementation notes](docs/REMOTE-DESKTOP-IMPLEMENTATION.md) for the issue analysis, migration scope, checks and remaining limitations. RDP is currently restricted to administrator accounts and enabled with `compose.remote.yaml`; preserve the existing data volume and `SESSION_SECRET`. The default Docker Compose services, credentials, tiers and homepage limits are retained.

Python regression and live SSH tests run with `python -m unittest discover -s tests -q`. `tests/run_browser_checks.sh` runs the browser regressions and isolated desktop/SSH/Guacamole fixtures (requires Python dependencies, Playwright and Chromium). Normal browser CI uses a simulated guacd; a real guacd/FreeRDP NLA desktop with certificate pinning was also exercised during development.
