# IONOS SMTP for CodeX Homelab

Add the following to the existing local `.env` file on the Raspberry Pi (do not commit secrets):

```dotenv
SMTP_HOST=smtp.ionos.de
SMTP_PORT=587
SMTP_USER=noreply@agrosskopf.de
SMTP_FROM=noreply@agrosskopf.de
SMTP_PASSWORD=REPLACE_WITH_YOUR_NEW_IONOS_PASSWORD
```

Port 587 uses STARTTLS with certificate validation. Port 465 uses implicit TLS.

The existing `compose.yaml` loads `.env` via `env_file`. Do not overwrite existing `SESSION_SECRET`, `ADMIN_PASSWORD`, `PUBLIC_ORIGIN` or other values.

**Security:** Rotate the previously disclosed mailbox password in IONOS before deploying. Never store SMTP credentials in GitHub or browser storage.

**Development status:** The feature branch has not been integration-tested on Raspberry Pi. Make a backup of `/data/homelab.sqlite3` before testing. Public registration should not be exposed to the internet until persistent rate limiting, email delivery failure recovery, CSRF checks, session revocation, and end-to-end tests are completed. Password resets update the hash but do not yet revoke previously issued signed sessions.
