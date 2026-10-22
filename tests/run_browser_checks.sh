#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
: "${PYTHON:=python}"
: "${PLAYWRIGHT_MODULE:=playwright}"
export PLAYWRIGHT_MODULE PYTHONDONTWRITEBYTECODE=1
artifacts="$(mktemp -d /tmp/agms-browser-logs.XXXXXX)"
node tests/test_remote_keys.cjs
ops_pid=''
remote_pid=''
cleanup(){
  if [ -n "$ops_pid" ]; then kill "$ops_pid" 2>/dev/null || true; fi
  if [ -n "$remote_pid" ]; then kill "$remote_pid" 2>/dev/null || true; fi
}
trap cleanup EXIT
"$PYTHON" tests/serve_operations_fixture.py > "$artifacts/operations-server.log" 2>&1 &
ops_pid=$!
"$PYTHON" tests/serve_remote_fixture.py > "$artifacts/remote-server.log" 2>&1 &
remote_pid=$!
"$PYTHON" - <<'PY'
import time,urllib.request
for port in [8082,8083]:
 for attempt in range(100):
  try:
   with urllib.request.urlopen(f'http://localhost:{port}/health',timeout=1) as response:
    if response.status==200:break
  except OSError:pass
  time.sleep(.1)
 else:raise SystemExit(f'Fixture on port {port} did not start')
PY
# Fail if a fixture crashed (e.g. an unrelated service already used the port).
kill -0 "$ops_pid" "$remote_pid"
for script in browser_kuma_history browser_operations browser_refresh browser_widget_connections browser_desktop browser_inline_edit browser_group_order browser_remote browser_remote_controls browser_legal; do
  node "tests/$script.cjs"
done
printf 'Browser fixture logs: %s\n' "$artifacts"
