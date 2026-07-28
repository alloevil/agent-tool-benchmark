#!/usr/bin/env bash
set -euo pipefail
time ego-browser nodejs <<'EOF'
await useOrCreateTaskSpace('benchmark suite')
await openOrReuseTab('https://demo.playwright.dev/todomvc/', { wait: true, timeout: 20 })
await js(String.raw`localStorage.clear()`)  // ego migrates Chrome localStorage; start clean
await gotoAndWait('https://demo.playwright.dev/todomvc/', { timeout: 20 })
await waitForElement('input.new-todo')
for (const t of ['buy milk', 'write report', 'call bank']) {
  await fillInput('input.new-todo', t)
  await pressKey('Enter')
}
await js(String.raw`document.querySelectorAll('.todo-list li .toggle')[1].click()`)
cliLog('count: ' + await js(String.raw`document.querySelector('.todo-count')?.innerText`))
cliLog('items: ' + JSON.stringify(await js(String.raw`Array.from(document.querySelectorAll('.todo-list li')).map(li => li.innerText + (li.classList.contains('completed') ? ' [done]' : ''))`)))
EOF
