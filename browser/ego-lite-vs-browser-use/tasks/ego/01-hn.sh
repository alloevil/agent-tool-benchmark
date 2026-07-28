#!/usr/bin/env bash
set -euo pipefail
time ego-browser nodejs <<'EOF'
const task = await useOrCreateTaskSpace('benchmark suite')
await openOrReuseTab('https://news.ycombinator.com', { wait: true, timeout: 20 })
const items = await js(String.raw`(() =>
  Array.from(document.querySelectorAll('tr.athing')).slice(0,5).map(r => {
    const title = r.querySelector('.titleline a')?.innerText;
    const score = r.nextElementSibling?.querySelector('.score')?.innerText || 'n/a';
    return score + ' | ' + title;
  })
)()`)
cliLog(JSON.stringify(items, null, 2))
EOF
