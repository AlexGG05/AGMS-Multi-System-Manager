# CodeX Homelab — GitHub/Arcane Deployment

**Status:** This is the existing v1 project repackaged for repository `codex-agrosskopf-dashboard`. It is **not** a completed v2 management implementation and has **not** been pushed to GitHub.

1. Create or use your existing GitHub repository `codex-agrosskopf-dashboard`.
2. Upload all project files including `.github/workflows/publish.yml` (never upload `.env` or credentials).
3. In GitHub Actions, ensure workflow permissions allow `packages: write`; run the build workflow.
4. In GitHub Packages, make the container package public or configure GHCR credentials in Arcane.
5. In `compose.arcane.yaml`, replace `YOUR_GITHUB_USERNAME` with the lowercase GitHub owner.
6. In Arcane select the Pi4b environment and create a project using `compose.arcane.yaml`.
7. Set `ADMIN_USERNAME`, a unique `ADMIN_PASSWORD` (at least 16 characters), `SESSION_SECRET` (generate with `openssl rand -hex 32`), and `PUBLIC_ORIGIN` (your exact HTTPS origin).
8. Optionally configure `PVE_URL`, `PVE_TOKEN_ID`, `PVE_TOKEN_SECRET` with a read-only token and a trusted CA certificate.
9. Deploy and check container logs and `/health`. Configure your reverse proxy with HTTPS and restrict direct port 8080 access.

## Next development work (not yet implemented)
- Arcane API integration: obtain version-specific OpenAPI specification, add server-side key auth, environment mapping, live metrics, update checks, explicit confirmations for updates.
- Proxmox management: least-privilege API tokens, node/VM/LXC detail views, audited actions, backup/restore workflows, task progress, resource editing with validation.
- Browser terminal: Guacamole SSO or authenticated reverse-proxy integration, separate SSH permissions, session auditing.
- Security: role-based access, rate limiting, action confirmation, CSRF validation, secret storage and TLS verification.

Do not expose Proxmox root tokens, Docker sockets or SSH keys to the browser.
