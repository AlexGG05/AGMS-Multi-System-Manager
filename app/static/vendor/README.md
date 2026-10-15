# Vendored browser dependencies

Served locally: no CDN requests, remote code loading or runtime npm installation.

* `xterm/xterm.js`, `xterm/xterm.css`: @xterm/xterm 6.0.0, npm tarball integrity checked by npm pack; MIT license in LICENSE-xterm.
* `xterm/addon-fit.js`: @xterm/addon-fit 0.11.0; MIT license in LICENSE-addon-fit.
* `guacamole/guacamole.js`: Apache guacamole-client tag 1.6.0, commit 0537c89cd783681b986ff8f8c4e0b97ec6873371, concatenated `guacamole-common-js/src/main/webapp/modules/*.js` in filename order. Apache License and NOTICE are retained.

`SHA256SUMS.json` records the checked-in file hashes. Upgrade sources deliberately and rerun the real browser tests. The original module license headers remain in the concatenated Guacamole source.
