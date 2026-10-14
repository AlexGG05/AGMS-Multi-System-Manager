# CodeX Homelab v1 — Raspberry Pi 4B

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
git clone YOUR_REPOSITORY_URL codex-homelab
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

The homepage sidebar offers **Create Ticket** to signed-in users. Tickets receive a sequential ticket number and contain a subject (1–200 characters), a description (1–10,000 characters) and a category: Problem, Idea, Wish or Other. They are stored in SQLite. The ticket overview shows number and subject; selecting a ticket opens its description and details.

Accounts with the `admin` role can open **Admin Panel**, then select **Proxy requests**, **Users** or **Tickets**. Administrative APIs enforce that role server-side. English is the default language; the language selector switches the interface to German.

Run the admin/ticket API regression tests after installing `requirements.txt`:

```bash
python -m unittest discover -s tests -v
```

The tests use an isolated temporary SQLite database and do not need external integrations.
