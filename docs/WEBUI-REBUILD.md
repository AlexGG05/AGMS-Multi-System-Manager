# CodeX Homelab – WebUI-only Rebuild

Development branch: `feat/webui-only-rebuild`.

## Product scope
- Email login, registration, email verification and password reset retained.
- Per-user homepages, groups, WebUI tiles, iframe viewer, drag-and-drop navigation.
- Team invitation by email; owner/editor/viewer roles.
- Owner can delete a homepage, remove members, and delete groups and tiles.
- Premium tier limits remain enforced by backend: free 1, tier 1 3, tier 2 5, tier 3 10; platform admin unlimited.
- No CPU, RAM, Docker, LXC, VM, or Proxmox statistics in the new dashboard.
- The original service APIs remain in the code for compatibility but are not exposed in the new UI.

## Important deployment notes
The existing database is reused. **Back up the persistent `dashboard_data` volume before testing.** Do not delete the volume or overwrite `.env`. SMTP credentials must be stored only in the local environment; never commit them.

The existing platform administrator now opens the same WebUI homepage as regular accounts; manual tier assignment remains at `/static/admin-premium.html`.

Some third-party interfaces, including TrueNAS, prohibit iframe embedding via CSP or X-Frame-Options. The external-open link is provided as a fallback. A public HTTPS dashboard may block private HTTP iframe targets.

## Security / test gate
Not production approved. Integration tests, email delivery failure handling, durable abuse protection, password-reset session invalidation, and tenant isolation review are still needed before enabling public registration.
