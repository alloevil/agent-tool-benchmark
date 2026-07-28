#!/usr/bin/env bash
set -euo pipefail
(time ego-browser nodejs <<'EOF'
await useOrCreateTaskSpace('parallel-A')
await openOrReuseTab('https://example.com', { wait: true, timeout: 20 })
cliLog('A: ' + await js(String.raw`document.title`))
EOF
) & (time ego-browser nodejs <<'EOF'
await useOrCreateTaskSpace('parallel-B')
await openOrReuseTab('https://httpbin.org/html', { wait: true, timeout: 20 })
cliLog('B: ' + await js(String.raw`document.querySelector('h1')?.innerText`))
EOF
) & wait
