# AGMS — Multi System Manager

Lightweight, self-hosted homelab dashboard. Runs on Raspberry Pi OS 64-bit (ARM64) with Docker Compose.

## Implemented
- Username/password login, bcrypt password hash, signed HTTP-only session cookie, 8-hour expiry
- CSRF and Origin protection for mutations, basic login rate limiting
- Dark responsive dashboard; seeded inventory of your Docker LXCs, Pi, dedicated LXCs, and infrastructure
- Save web links for every service and open them in a new tab
- Read-only Proxmox **cluster** monitoring: nodes, VMs, LXCs, CPU and RAM via official API
- SQLite persistent storage; Docker health endpoint

## Not implemented yet
- Live Docker/Arcane running/stopped/update counts (needs a verified Arcane API contract and access)
- TrueNAS and FRITZ!Box telemetry
- Browser SSH/console, container lifecycle actions, automatic updates, alerting, user management
- Guacamole SSO; its dashboard entry is an external link

The UI deliberately labels inventory counts separately from live metrics. Do not interpret static service counts as live health.

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
- This v1 supports one seeded admin user, not multiple accounts or password recovery.
- Login rate limiting is in memory per process; put rate limits and MFA/Access in the reverse proxy for internet-facing deployment.
- Restrict dashboard access to trusted users; all logged-in users can edit service links.
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
- **Status overview** is a separate left-navigation tab, with homepage/search filters and refresh controls. Public destinations are checked from the AGMS server with TLS verification; HTTP 5xx responses are marked Degraded. Private addresses and unsupported ports remain Not checked. This reports reachability rather than deep application health. Status requests use at most four concurrent checks, with a short browser cache.

Existing users, ticket numbers, descriptions and comments are preserved by additive SQLite migrations. No additional Compose volume or dependency is required.

### Uptime Kuma dashboards

Open **Status overview → Add status entry**. Enter a title, your own category
(for example `vHosts`), and the full published Kuma URL such as
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
path too. Existing AGMS service reachability remains available below Kuma.

### Proxy start paths and Uptime Kuma administration

A proxied WebUI can use a start path, for example
`https://kuma.example.com/dashboard`. Approval still applies only to the HTTPS
origin (`https://kuma.example.com`); requests for assets and WebSockets remain
rooted at that origin. AGMS supplies a proxy-aware HTML base for applications
such as Uptime Kuma whose Vue Router otherwise interprets the AGMS prefix as an
unknown route. Existing application base tags are preserved and rewritten.
The Kuma administration dashboard is separate from public status-page entries:
those still require a published `/status/<slug>` URL.
