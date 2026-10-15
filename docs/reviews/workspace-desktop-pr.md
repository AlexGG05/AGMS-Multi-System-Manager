## Summary

Closes #8 after the remote-session foundation is merged. Add an explicit Edit/Done homepage mode with pointer dragging, keyboard/touch ordering, persistent tile sizes, draft cancellation and stale-write rejection. Normal mode locks layout changes; existing viewer and tier restrictions remain enforced.

Add an optional web desktop with up to eight retained iframe/proxy/SSH/RDP windows, movement/resize, minimize/maximize/fullscreen, split layout, taskbar and a mobile full-area/tab view. Existing single-view routes and password-manager setup remain available. Add local terminal/Guacamole clients, connection configuration, administrator destination approval, English/German strings, documentation and browser PR checks.

## Validation

- Full Python regression suite, including live SSH transport/security and additive migration tests.
- Real-browser pointer edit/order/size persistence, viewer lock and four simultaneous iframe/proxy windows retaining their input state.
- Browser SSH and Guacamole display/keyboard, mobile view, German strings, secret-field masking and existing Kuma/profile/security/legal-page regressions.
- Real guacd/FreeRDP NLA desktop with certificate pinning, rendered image data and rejection of a wrong pin.
- Docker build and non-root/read-only smoke checks.

Depends on the foundation branch. Existing data volumes and SESSION_SECRET must be preserved. Window/remote-session state survives switching/minimizing within a page, but not refresh or server restart. Windows-specific enterprise authentication and ARM64 execution remain deployment-environment checks.
