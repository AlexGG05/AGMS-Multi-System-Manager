## Summary

Add the server foundation for permission-bound browser SSH and Apache Guacamole RDP. Saved secrets use the existing encryption key; destinations require administrator approval and pinned addresses. Single-use cookie-bound tickets, live permission/logout revocation, session/attempt limits, SSH host-key checking and RDP certificate pinning/validation keep targets and secrets server-side.

Additive migrations retain existing accounts, tiers, homepages and integration data. Homepage sizes/revisions support the follow-up UI PR; stale revision writes fail with 409. The optional Docker override supplies guacd without another account or database. AsyncSSH requires the coordinated cryptography/pyOpenSSL updates.

This is the foundation of a stacked change: the browser/editing/desktop PR depends on it. Deploy the combined result after review; no production data or credentials are changed.

## Validation

- Existing Python regression suite plus migration, permissions, credential secrecy, session replay/limits, tier restrictions and optimistic revision tests.
- Live SSH password, private key/passphrase, PTY resize, host-key mismatch and permission-revocation tests.
- Guacamole handshake/input filtering tests and real guacd → FreeRDP NLA display with a verified certificate pin; mismatched pin rejected.
- Dockerfile build and non-root/read-only runtime checks. guacd amd64/arm64 manifests verified; ARM64 execution requires target-environment validation.

See `docs/REMOTE-ACCESS.md` for setup and the trust model. Page/server-restart session resume and RDP file/clipboard/audio forwarding are outside this implementation.
