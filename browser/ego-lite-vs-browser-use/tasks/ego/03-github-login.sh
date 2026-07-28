#!/usr/bin/env bash
set -euo pipefail
time ego-browser nodejs <<'EOF'
await useOrCreateTaskSpace('benchmark suite')
await openOrReuseTab('https://github.com', { wait: true, timeout: 30 })
cliLog('github user: ' + await js(String.raw`document.querySelector('meta[name="user-login"]')?.content || '(not logged in)'`))
EOF
