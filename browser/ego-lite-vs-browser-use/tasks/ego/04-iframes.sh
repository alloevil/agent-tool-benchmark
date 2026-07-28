#!/usr/bin/env bash
set -euo pipefail
# requires: python3 -m http.server 8973/8974 --directory fixtures
time ego-browser nodejs <<'EOF'
await useOrCreateTaskSpace('benchmark suite')
await openOrReuseTab('http://localhost:8973/outer.html', { wait: true, timeout: 20 })
cliLog('same-origin: ' + await js(String.raw`document.querySelector('iframe').contentDocument.querySelector('iframe').contentDocument.querySelector('#secret')?.innerText`))
await openOrReuseTab('http://localhost:8973/outer-x.html', { wait: true, timeout: 20 })
cliLog(await snapshotText())  // cross-origin content appears directly in the semantic tree
EOF
