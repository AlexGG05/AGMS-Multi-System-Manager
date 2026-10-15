# Homepage editing and web desktop (issue #8)

## Existing behavior retained

The normal homepage still opens a single iFrame or AGMS-Proxy view, preserving `/webui/...` entry links and the password-manager setup flow. External links still open a separate browser tab. The **Multiple windows** toggle is optional. SSH and RDP tiles use integrated windows directly. Free/Tier 1/2/3 limits, team roles, favorites, Kuma, tickets and integrations use their existing APIs and data.

## Edit / Done

Each homepage has its own **Edit / Done** control, visible only to an owner/editor whose homepage is editable under the existing tier rules. Normal mode has no drag/resize handles. Add/import controls and layout gestures are unavailable outside editing. In edit mode:

* Drag a tile/group by its handle onto another tile in the same group. The highlighted target indicates the drop location. Pointer events support mouse and touch.
* Use the up/down controls as the keyboard/touch alternative. All controls are real buttons with accessible labels.
* Drag the corner to resize or use **Size** to choose width/height (1–4 units). Narrow screens clamp the visible width without discarding the saved size.
* **Edit** on a tile opens its existing detail editor; **Minimum role to open** controls access to an individual connection; groups and ungrouped services retain their existing metadata controls. **Manage connections** opens the full editor. SSH/RDP configuration is separate from normal tile metadata.
* **Done** saves the layout; **Cancel** restores the draft snapshot. Unsaved drafts warn before page exit/homepage switching. Explicit connection configuration saves the tile before saving credentials.

Sizes are stored on `workspace_navigation`; old records default to one unit. Existing order, groups, service modes and IDs are preserved. The homepage has an additive `layout_revision` counter. Current AGMS clients send their loaded revision with navigation writes; a stale write gets HTTP 409 and keeps the current user's draft visible. Reload deliberately before reapplying a conflict. Legacy API callers without a revision remain compatible; they should migrate to sending `revision` for optimistic conflict protection. The guarded revision update is atomic. Higher-role tiles that an editor cannot see are preserved rather than erased when their visible navigation is saved; attempts to submit hidden tile IDs or delete a group containing protected tiles are rejected.

## Windows

Turn **Multiple windows** on and open WebUIs from their tiles. Windows retain their iframe/connection DOM while you use Overview, switch groups/homepages, minimize or select another taskbar tab. You can move/resize windows, minimize, maximize, enter browser fullscreen, close them, or use **Tile windows** for split view. An existing WebUI tile focuses its existing window; remote tiles can start separate sessions. The dock reopens the desktop from Overview. There is a maximum of eight windows per tab.

Desktop title bars also support arrow-key movement; Shift+Arrow resizes. On screens up to 700 px, the desktop shows one active full-area window with taskbar tabs, retaining the other sessions in the background. SSH includes touch buttons for Esc, Tab, Ctrl+C and arrows, plus a keyboard button; RDP includes a touchpad and keyboard button.

State is held only in the signed-in page's memory. Another account receives no persisted windows; reload/logout closes the page's transports. No remote password, key or terminal output is persisted in browser storage. WebUI permissions are rechecked every fifteen seconds and on returning to the tab. Deleted/inaccessible tiles and changed URL/mode close their windows. Remote sessions additionally enforce server-side checks every five seconds.

An upstream service can still prohibit iframe embedding. Its window offers **Open externally** and explains the fallback; AGMS cannot override browser origin policies for ordinary iframe mode. The existing approved proxy mode is unchanged. Single-view password-manager integration remains available when an extension needs the service-specific `/webui/...` top-level route.
