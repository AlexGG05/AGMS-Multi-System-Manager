# Mobile SSH/RDP controls (issue #9)

Each authorized SSH/RDP session has its own **Keyboard** and **Special keys** controls. The special-key panel starts expanded on touch devices/narrow screens and collapsed on desktop. It can be shown or hidden independently for each session. It occupies layout space rather than covering the terminal or remote desktop. With little vertical space, including an open software keyboard, its keys move into one horizontally scrollable row. Touch targets are at least 44 pixels high.

* **Ctrl**, **Alt** and **Shift** latch for the next key. RDP also offers **Win** (Super). A highlighted button and `aria-pressed` indicate the selected modifiers. Tap again to deselect. Combinations can include several modifiers.
* The selected modifiers apply to the next on-screen key or typed character and then clear. Hiding controls, leaving the remote input or ending the session clears the state. Sessions do not share modifier state. Normal physical-keyboard handling continues when no modifier is latched.
* **Esc**, **Tab**, **Enter**, arrows and **Del** are available without a physical keyboard. **F1–F12** expands a function-key row. SSH arrow encoding follows the terminal's application-cursor mode; modified arrows/function keys use standard xterm sequences.
* Direct shortcuts include **Ctrl+C**, **Ctrl+V**, **Alt+Tab**, and **Ctrl+Alt+Del** for RDP. SSH Ctrl+C sends the terminal interrupt byte `0x03`; it does not trigger a browser copy action. SSH Ctrl+V sends `0x16` (normally the shell's literal-next-character command). RDP receives ordered modifier/key press and release events. Win is only offered for RDP because a conventional SSH PTY has no portable standalone Super-key encoding.
* **Keyboard** focuses the SSH input or Guacamole input sink to request the phone's keyboard. The controls preserve that focus when tapped. The RDP input sink and display use one Guacamole keyboard instance to prevent duplicate key events.

Ctrl+V is a remote key combination, not clipboard synchronization. AGMS does not read the phone/browser clipboard. Guacamole clipboard redirection remains disabled. The remote application's own keyboard handling, Windows policy, terminal bindings and platform/browser keyboard behavior still apply.

Controls are created only after the server grants a session ticket, remain hidden until the transport is connected, and are removed or disabled when the session ends. Existing SSH permissions, administrator-only RDP, CSRF/Origin checks, target approval, encrypted credentials and server-side session revocation are unchanged. No new routes, database migrations or persistent browser state are required.

## Verification

`node tests/test_remote_keys.cjs` verifies SSH control bytes, all arrow/function key encodings, Unicode and ordered RDP chords. `tests/browser_remote_controls.cjs` checks the actual SSH/Guacamole WebSocket output, one-shot/reset modifier state, function keys, physical keyboard passthrough, independent controls, German text, denied-session behavior and iPhone/Android device emulation. Compact mode is tested with a reduced viewport representing an open software keyboard. Real iOS/Android keyboards and enterprise Windows shortcut policies still require verification on the deployed devices. Both checks run through `tests/run_browser_checks.sh`.
