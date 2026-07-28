#!/usr/bin/env bash
set -euo pipefail
time browser-use <<'PY'
new_tab("https://github.com")
wait_for_load()
print("github user:", js("document.querySelector('meta[name=\"user-login\"]')?.content || '(not logged in)'"))
PY
