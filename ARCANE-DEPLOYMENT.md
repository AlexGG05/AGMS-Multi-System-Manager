# CodeX Homelab: GitHub + Arcane deployment (ARM64)

## 1. Publish source to GitHub
Create a new GitHub repository (for example `codex-homelab`). Upload the **contents** of this folder, including `.github/workflows/publish.yml`, and commit to `main`. Do not upload `.env` or passwords.

Example using Git (after creating an empty repo):
```bash
git init
git add .
git commit -m "Initial CodeX Homelab"
git branch -M main
git remote add origin https://github.com/YOUR_GITHUB_USERNAME/codex-homelab.git
git push -u origin main
```

## 2. Build an ARM64 image automatically
Go to **GitHub > Actions > Build and publish ARM64 Docker image**. The workflow builds `linux/arm64` using Buildx/QEMU and publishes to `ghcr.io/YOUR_GITHUB_USERNAME/codex-homelab:latest` on every push to `main`.
Check that the action succeeded and the image exists under GitHub Packages. GHCR package names are normally lowercase. For easy Arcane deployment, change package visibility to **public** in GitHub package settings. If private, configure registry credentials in Arcane instead. Do not place a GitHub personal access token inside Compose YAML.

For versioned releases, push a Git tag such as `v1.0.0` and change the Compose image tag to that release to avoid surprise upgrades.

## 3. Deploy in Arcane
In your existing Arcane UI, choose the **Pi4b** environment (verify it is online and ARM64). Create a new Compose project/stack named `codex-homelab`. Paste `compose.arcane.yaml` and replace the image placeholder with the GHCR path from step 2.

Set these **project environment variables** in Arcane (names may vary by Arcane release):
- `ADMIN_USERNAME=admin`
- `ADMIN_PASSWORD=` unique random password **at least 16 characters**
- `SESSION_SECRET=` output of `openssl rand -hex 32` (64 hex characters)
- `PUBLIC_ORIGIN=https://homelab.your-domain.example` (the exact external browser origin)
- Optional `PVE_URL=https://proxmox-host:8006`, `PVE_TOKEN_ID`, `PVE_TOKEN_SECRET`, `PVE_CA_BUNDLE`

Ensure Arcane substitutes `${...}` before deploying. Keep these values out of screenshots, GitHub, and shared compose files. Deploy, then inspect container logs. The app listens on container port 8080; the example publishes port 8080 on the Pi.

## 4. HTTPS and network access
This Compose example publishes `8080` on the Pi's network interfaces so Docker-Edge's reverse proxy can reach it. **Before deploying**, restrict inbound TCP/8080 on the Pi/network firewall to only the reverse proxy's IP (Docker published ports can bypass some host firewall configurations; verify rules with your Docker setup). Prefer a private network/VPN where possible.

Configure Nginx on Docker-Edge to proxy `https://homelab.your-domain.example` to `http://PI_LAN_IP:8080`, preserving Host and forwarding X-Forwarded-Proto. If using Cloudflare Tunnel, point the tunnel at the HTTPS reverse proxy and protect the site with Cloudflare Access/MFA. Do not publicly expose TCP/8080.

For local and remote access, use the **same HTTPS hostname**, resolving internally to your reverse proxy using split DNS. The backend enforces `PUBLIC_ORIGIN` on login and write requests, and secure cookies require HTTPS.

## 5. Proxmox cluster
Create a dedicated read-only Proxmox API token with audit rights, configured in Arcane project variables. For self-signed Proxmox certificates, mount your trusted CA certificate read-only (see commented mount in Compose), then set `PVE_CA_BUNDLE=/certs/ca.pem`. Do not disable TLS verification.

## 6. Updates, rollback and backup
To update: push to `main`, wait for GitHub Actions to publish, then in Arcane pull/redeploy the image. The `latest` tag alone does **not** cause an automatic update. Prefer release tags for controlled upgrades.
To roll back: change `image:` to a known working `vX.Y.Z` tag and redeploy. The named Docker volume `dashboard_data` holds your SQLite DB; back it up before upgrades. Do not delete the volume when redeploying.

## Known limitations
Arcane API live stats, update counts, terminal access, container controls, and TrueNAS/FRITZ!Box monitoring are **not implemented** in this version. Arcane is the deployment manager, not yet a data source for this dashboard.
Admin password is seeded only on first startup; changing `ADMIN_PASSWORD` after the DB exists will not change the account password.
