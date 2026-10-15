# SSH, RDP and web desktop implementation

## Repository and issues reviewed

Starting point: `main` at `51e52b318fe0556b0a7076eb126ac65d2a68ca08` (public bilingual legal pages). Fetched origin before editing; the working tree was clean. The GitHub open-issue index showed exactly one open issue, [#8](https://github.com/AlexGG05/AGMS-Multi-System-Manager/issues/8), on 2026-10-15. Its full description and all acceptance criteria were read; it had no comments/timeline items. The public GitHub pages were readable; the REST/GraphQL API returned 403 in this environment.

Existing code already provided a legacy `/api/dashboard` grid editor, encrypted integration profiles and a single-view WebUI. The current multi-user homepage used `workspace_navigation`, had an independent group/detail editor, and enabled drag sorting outside explicit editing. There was no integrated SSH/RDP transport or live window manager. The old legacy editor is retained; the new editor extends the active multi-user homepage rather than replacing account/tier/dashboard APIs.

## Implementation order and review split

1. **Server foundation / remote sessions**: additive SQLite schema, optimistic homepage revision, remote configuration/access checks, administrator destination approval, single-use session tickets, SSH transport and Guacamole handshake/tunnel, bounded key decoding, Docker override and API/live SSH tests.
2. **Homepage and browser clients**: vendored terminal/Guacamole clients, connection editor and admin approval UI, opt-in live web desktop, explicit edit mode, touch/keyboard controls, mobile full-area sessions, translations, privacy additions, browser tests and PR CI.
3. **Validation**: preserve existing regression behavior, exercise permission revocation/negative trust cases, build/start the container, and test real guacd/FreeRDP with NLA and a verified certificate pin.

The foundation and browser commits were prepared as stacked review changes. After validation, the project owner explicitly requested direct integration of the combined result into `main` on 2026-10-15. Production deployment remains an operator action. All application/database tests use fresh temporary databases; production volumes and credentials are untouched.

## Additive migration

* `workspace_navigation.tile_width` and `tile_height` default to 1 for existing records.
* `workspaces.layout_revision` defaults to 0; current clients send the loaded revision. Atomic stale-write rejection uses HTTP 409; user drafts stay visible.
* New `remote_connections`, `remote_targets`, `remote_sessions`, `remote_session_attempts` tables. Existing user, security, tier, homepage, ticket, notification and integration tables are not recreated/reset.
* SSH/RDP password, private key, passphrase and domain fields use the existing SESSION_SECRET-derived Fernet cipher. The ciphertext is bound to the homepage/tile. Secrets are not returned through APIs or written to audit details. Metadata is permission-scoped.
* Navigation saves preserve higher-role tiles omitted from an editor’s visible payload and reject attempts to overwrite them. They retain credentials for unchanged tile IDs; deleting a tile/homepage/account cleans up its saved connections and leases. Active sockets revalidate permissions independently.

## Completed functionality

* Homepage SSH tiles, password/key/passphrase authentication, required SSH host-key pin, PTY streaming/resize and parallel sessions.
* Homepage RDP tiles using bundled Apache guacd, NLA, strict certificate checks or an explicitly verified SHA256 certificate pin, local Guacamole browser client, mouse/touch/keyboard support and no separate Guacamole account/database.
* Existing iFrame, external-tab and administrator-approved AGMS-Proxy modes preserved, including single-view password-manager setup and service-specific entry links.
* Explicit per-homepage editing with draft save/cancel, pointer reorder, keyboard/touch arrows, tile width/height controls and persistent layouts.
* Optional multi-window desktop: retained live frames, movement/resize, minimize/maximize/fullscreen, split layout, taskbar/dock and mobile tabs/full-area view. Remote tiles open directly in this desktop; opening them again creates another session.
* Existing roles and homepage edit limits enforced server-side; remote membership/role/approval/session revocation checks every five seconds; ordinary WebUI window access rechecked every fifteen seconds.
* Eight remote sessions/account, twenty connection attempts/minute, eight mounted windows/tab, bounded input and isolated CPU/memory/time-limited SSH key decoding.
* English/German UI and existing public legal footer retained. README and deployment/security instructions updated.

## Validation evidence

The Python suite (60 tests) includes existing ticket, account, tier, proxy, Kuma, profile, notification and security tests plus new migration, conflict, destination, credential, ticket replay, rate/session limit, tier, SSH and Guacamole cases. Live SSH tests cover password, plain/encrypted private keys, terminal resize, wrong-host-key rejection and active membership revocation.

Nine browser test groups cover the existing Kuma/profile/security/legal flows plus viewer lock, explicit edit-mode pointer drag, saved order/sizes after reload, cancel, four simultaneously mounted iframe/proxy windows without losing frame state, minimize/maximize, mobile tabs, SSH keyboard/PTY, Guacamole canvas/mouse/keyboard, German UI and secret-field masking. The normal repeatable CI fixture simulates guacd; a separate real Docker guacd 1.6.0 → FreeRDP 3 shadow desktop was exercised with NLA and a certificate pin, including real rendered image updates and rejection of a wrong pin.

Docker build uses the repository Dockerfile and the existing non-root/read-only runtime. The optional `build_ca` BuildKit secret supplies this environment's trusted build proxy CA without storing it in the image. The guacd image has amd64 and arm64 manifests; the application build is validated on the available amd64 host. ARM64 execution and real Windows-specific enterprise policies still require deployment-environment validation.

## Deliberate limits / remaining integration dependencies

* Remote sockets and window state do not resume after browser refresh, logout or server restart. Switching/minimizing within a page preserves them.
* RDP clipboard, upload/download, drive mapping and audio redirection are disabled. No unverified host-key acceptance or ignore-certificate switch is exposed.
* iFrame-blocking applications still need their existing proxy mode or external-open fallback; browser origin policies are not bypassed.
* Legacy external callers that omit a navigation revision remain compatible, but must send `revision` to opt into conflict protection.
* Administrators must approve actual target addresses and provision credentials/verified SSH host keys or RDP certificate trust. No production endpoints are preapproved and no credentials are invented or replaced.
* Actual deployment, production Windows authentication/certificates and capacity under the user's workload have not been exercised from the development environment.
* GitHub's REST/GraphQL API is blocked in this environment (403). Actual `gh pr create --draft` attempts for both review branches failed; no PRs were created. The review branches and PR descriptions are published for manual PR creation. This is an environment/access limitation, not an automatic approval-review rejection.

## Review branches and PR creation

* Foundation: `feature/remote-sessions-core`, commit `a97a45b`, base `main`. [Open comparison](https://github.com/AlexGG05/AGMS-Multi-System-Manager/compare/main...feature/remote-sessions-core?expand=1), description: [remote-core-pr.md](reviews/remote-core-pr.md).
* Browser/editor/desktop: `feature/remote-sessions-and-workspace-desktop`, based on the foundation branch. [Open stacked comparison](https://github.com/AlexGG05/AGMS-Multi-System-Manager/compare/feature/remote-sessions-core...feature/remote-sessions-and-workspace-desktop?expand=1), description: [workspace-desktop-pr.md](reviews/workspace-desktop-pr.md).

The combined result is integrated directly into `main` following the project owner’s subsequent instruction. The original review branches remain available for comparison. No production deployment is performed from this environment. GitHub-hosted PR checks have been added; local verification is documented above.

## Follow-up: in-place editing and administrator-only RDP

RDP is temporarily restricted to administrators in navigation writes, credential APIs, ticket creation and live tunnel access (including role revocation). Non-admin navigation responses omit RDP entries and visible-only saves preserve them. Two additional regression tests cover the restriction and favorite dimensions.

The central editor and sequential prompt-based entry creation are replaced by tile/group pencils and one adaptive dialog, available only in Edit mode. Favorites have independent stored dimensions. The new browser test covers group and tile edits, type switching, a single-form SSH credential save, draft secret isolation, favorite size persistence, star/status containment and mobile dialogs. The existing desktop and remote browser checks remain in the suite.

## Issue #9: mobile remote key controls

The complete issue body was reviewed; it had no comments/timeline entries. Per-session toggleable SSH/RDP key panels now provide one-shot Ctrl/Alt/Shift, RDP Win, navigation/function keys and direct shortcuts. Normal physical keyboard input remains available. Controls adapt to a shortened keyboard viewport and do not overlay remote content. Protocol-level JavaScript tests and a browser group check the actual SSH/Guacamole WebSocket key sequences, resets, authorization failure, German and iPhone/Android emulation. See [usage, mappings and device-test limits](MOBILE-REMOTE-CONTROLS.md). No server permission, database or credential changes are introduced.
