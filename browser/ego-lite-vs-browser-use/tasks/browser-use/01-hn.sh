#!/usr/bin/env bash
set -euo pipefail
time browser-use <<'PY'
new_tab("https://news.ycombinator.com")
items = js("""
Array.from(document.querySelectorAll('tr.athing')).slice(0,5).map(r => {
  const title = r.querySelector('.titleline a')?.innerText;
  const score = r.nextElementSibling?.querySelector('.score')?.innerText || 'n/a';
  return `${score} | ${title}`;
})
""")
print(items)
PY
