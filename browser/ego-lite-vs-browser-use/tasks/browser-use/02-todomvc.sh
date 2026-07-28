#!/usr/bin/env bash
set -euo pipefail
time browser-use <<'PY'
new_tab("https://demo.playwright.dev/todomvc/")
wait_for_element("input.new-todo")
for t in ["buy milk", "write report", "call bank"]:
    fill_input("input.new-todo", t)
    press_key("Enter")
js("document.querySelectorAll('.todo-list li .toggle')[1].click()")
print("count:", js("document.querySelector('.todo-count')?.innerText"))
print("items:", js("Array.from(document.querySelectorAll('.todo-list li')).map(li => li.innerText + (li.classList.contains('completed') ? ' [done]' : ''))"))
PY
