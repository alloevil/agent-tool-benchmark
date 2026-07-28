#!/usr/bin/env bash
set -euo pipefail
# requires: python3 -m http.server 8973/8974 --directory fixtures
time browser-use <<'PY'
new_tab("http://localhost:8973/outer.html")
wait_for_load()
print("same-origin:", js("document.querySelector('iframe').contentDocument.querySelector('iframe').contentDocument.querySelector('#secret')?.innerText"))
new_tab("http://localhost:8973/outer-x.html")
wait_for_load()
print("cross-origin direct js:", js("document.querySelector('iframe').contentDocument.querySelector('iframe').contentDocument?.querySelector('#secret')?.innerText"))
# cross-origin requires manual CDP frame-target attachment:
targets = cdp("Target.getTargets")
for t in targets.get("targetInfos", []):
    if "8974" in t.get("url", ""):
        sess = cdp("Target.attachToTarget", targetId=t["targetId"], flatten=True)
        r = cdp("Runtime.evaluate", expression="document.querySelector('#secret').innerText", session_id=sess["sessionId"])
        print("cross-origin via CDP:", r["result"]["value"])
PY
