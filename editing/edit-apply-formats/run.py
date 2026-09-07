#!/usr/bin/env python3
"""Run the edit-apply-formats matrix.

For each scenario in fixtures/ and each applier, copy the scenario's on-disk
file into a temp workdir, apply the payload, and byte-compare the result with
expected. Records outcome + wall time to results.json and prints a table.

Appliers (all real-world, none invented):
  git-apply        `git apply` on payload.udiff        (strict udiff)
  gnu-patch        `patch -u -F2` on payload.udiff     (udiff with fuzz)
  aider-udiff      aider's flexible udiff applier      (search/replace-ified hunks)
  editblock        aider's SEARCH/REPLACE block applier
  strreplace       openhands-aci OHEditor str_replace  (Anthropic text-editor semantics)
  codex-applypatch OpenAI apply_patch reference impl   (V4A, vendor/apply_patch.py)
  cline-replace    Cline replace_in_file applier       (vendor/cline_diff.ts via bun)
  wholefile        write payload.wholefile over the file

Outcomes:
  PASS         result == expected, byte-for-byte
  REJECT       applier refused / errored, file untouched (safe failure)
  CORRUPT      applier "succeeded" but result != expected (silent damage)

Usage: ../../.venv/bin/python run.py   (or any python with aider + openhands-aci)
"""

import json
import logging
import shutil
import subprocess
import sys
import time
from pathlib import Path

logging.disable(logging.CRITICAL)

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures"

# ---------------------------------------------------------------- appliers

def apply_git(work, payload):
    p = subprocess.run(["git", "apply", "--unsafe-paths", str(payload)],
                       cwd=work, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr.strip().splitlines()[-1])


def apply_patch(work, payload):
    p = subprocess.run(
        ["patch", "-u", "-F2", "--batch", "--no-backup-if-mismatch",
         "-p1", "-i", str(payload)],
        cwd=work, capture_output=True, text=True)
    if p.returncode != 0:
        for rej in work.glob("*.rej"):
            rej.unlink()
        for orig in work.glob("*.orig"):
            orig.unlink()
        raise RuntimeError((p.stdout + p.stderr).strip().splitlines()[-1])


def apply_aider_udiff(work, payload):
    from aider.coders.udiff_coder import hunk_to_before_after, do_replace, find_diffs
    edits = find_diffs("```diff\n" + payload.read_text() + "```\n")
    for fname, hunk in edits:
        fname = (fname or "file.py").removeprefix("b/")
        target = work / fname
        content = target.read_text() if target.exists() else ""
        new = do_replace(str(target), content, hunk)
        if new is None:
            raise RuntimeError(f"hunk failed to apply cleanly to {fname}")
        target.write_text(new)


def apply_editblock(work, payload):
    from aider.coders.editblock_coder import find_original_update_blocks, do_replace
    fence = ("```", "```")
    edits = list(find_original_update_blocks(payload.read_text(), fence,
                                             valid_fnames=None))
    for fname, original, updated in edits:
        target = work / fname
        content = target.read_text() if target.exists() else ""
        new = do_replace(str(target), content, original, updated, fence)
        if new is None:
            raise RuntimeError(f"SEARCH block not found in {fname}")
        target.write_text(new)


def apply_strreplace(work, payload):
    from openhands_aci.editor import OHEditor
    editor = OHEditor(workspace_root=str(work))
    calls = json.loads(payload.read_text())
    for call in calls:
        if call.get("create"):
            editor(command="create", path=str(work / call["path"]),
                   file_text=call["file_text"])
        else:
            editor(command="str_replace", path=str(work / "file.py"),
                   old_str=call["old_str"], new_str=call["new_str"])


def apply_codex_applypatch(work, payload):
    sys.path.insert(0, str(HERE / "vendor"))
    try:
        from apply_patch import process_patch, DiffError
    finally:
        sys.path.pop(0)

    def open_fn(path):
        return (work / path).read_text(encoding="utf-8")

    def write_fn(path, content):
        target = work / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    def remove_fn(path):
        (work / path).unlink(missing_ok=True)

    try:
        process_patch(payload.read_text(), open_fn, write_fn, remove_fn)
    except DiffError as e:
        raise RuntimeError(str(e)) from e


def apply_cline(work, payload):
    # 07-new-file creates util.py; everything else edits file.py (mirrors
    # the wholefile applier's convention).
    name = "util.py" if not (work / "file.py").exists() else "file.py"
    target = work / name
    # Node's fs reads/writes preserve line endings byte-for-byte; mirror that
    # (Python's read_text would silently normalize CRLF).
    original = target.read_bytes().decode("utf-8") if target.exists() else ""
    p = subprocess.run(
        ["bun", str(HERE / "vendor" / "cline_apply.ts")],
        input=json.dumps({"original": original, "diff": payload.read_text()}),
        capture_output=True, text=True)
    if p.returncode != 0 or not p.stdout.strip():
        try:
            msg = json.loads(p.stdout)["error"]
        except Exception:
            msg = (p.stderr or p.stdout).strip()[:200]
        raise RuntimeError(msg)
    target.write_bytes(json.loads(p.stdout)["content"].encode("utf-8"))


def apply_wholefile(work, payload):
    # Whole-file rewrite: the payload was generated from the STALE view.
    # 07-new-file names util.py; everything else targets file.py.
    name = "util.py" if not (work / "file.py").exists() else "file.py"
    (work / name).write_bytes(payload.read_bytes())


APPLIERS = [
    ("git-apply",        "payload.udiff",           apply_git),
    ("gnu-patch",        "payload.udiff",           apply_patch),
    ("aider-udiff",      "payload.udiff",           apply_aider_udiff),
    ("editblock",        "payload.editblock",       apply_editblock),
    ("strreplace",       "payload.strreplace.json", apply_strreplace),
    ("codex-applypatch", "payload.applypatch",      apply_codex_applypatch),
    ("cline-replace",    "payload.cline",           apply_cline),
    ("wholefile",        "payload.wholefile",       apply_wholefile),
]

# ---------------------------------------------------------------- harness

def run_one(scenario: Path, name: str, payload_name: str, fn):
    work = HERE / "_work"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=work, check=True)
    current = scenario / "file.py"
    if current.exists():
        shutil.copy(current, work / "file.py")
    payload = scenario / payload_name

    t0 = time.perf_counter()
    try:
        fn(work, payload)
        status = "applied"
        error = None
    except Exception as e:  # noqa: BLE001 - applier refusal is a result
        status = "REJECT"
        error = str(e)[:200]
    dt = time.perf_counter() - t0

    if status == "applied":
        ok = True
        for exp in scenario.glob("expected*"):
            out_name = exp.name.replace("expected_", "").replace(
                "expected.py", "file.py")
            got = work / out_name
            if not got.exists() or got.read_bytes() != exp.read_bytes():
                ok = False
        status = "PASS" if ok else "CORRUPT"
    shutil.rmtree(work)
    return {"status": status, "seconds": round(dt, 4), "error": error}


def main():
    scenarios = sorted(d for d in FIXTURES.iterdir()
                       if d.is_dir() and (d / "payload.udiff").exists())
    results = {}
    for scenario in scenarios:
        results[scenario.name] = {}
        for name, payload_name, fn in APPLIERS:
            if not (scenario / payload_name).exists():
                continue
            r = run_one(scenario, name, payload_name, fn)
            results[scenario.name][name] = r

    (HERE / "results.json").write_text(json.dumps(results, indent=2) + "\n")

    # Token cost of each payload format per scenario (cl100k_base).
    import tiktoken
    enc = tiktoken.get_encoding("cl100k_base")
    payload_files = {
        "udiff": "payload.udiff",
        "editblock": "payload.editblock",
        "strreplace": "payload.strreplace.json",
        "applypatch": "payload.applypatch",
        "cline": "payload.cline",
        "wholefile": "payload.wholefile",
    }
    tokens = {}
    for scenario in scenarios:
        tokens[scenario.name] = {}
        for fmt, fname in payload_files.items():
            f = scenario / fname
            if f.exists():
                tokens[scenario.name][fmt] = len(
                    enc.encode(f.read_bytes().decode("utf-8", "replace"),
                               disallowed_special=()))
    (HERE / "payload_tokens.json").write_text(
        json.dumps(tokens, indent=2) + "\n")

    names = [a[0] for a in APPLIERS]
    w = max(len(s) for s in results) + 2
    cw = max(len(n) for n in names) + 2
    print("scenario".ljust(w) + "".join(n.ljust(cw) for n in names))
    for scen, row in results.items():
        cells = []
        for n in names:
            r = row.get(n)
            cells.append((r["status"] if r else "-").ljust(cw))
        print(scen.ljust(w) + "".join(cells))
    print("\nresults.json written")


if __name__ == "__main__":
    sys.exit(main())
