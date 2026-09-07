#!/usr/bin/env python3
"""Generate all fixtures for the edit-apply-formats benchmark.

Model: an agent read `stale.py` (its view of the file), decided on an intended
change, and emitted that change in several edit formats. Meanwhile the file on
disk (`file.py`) may have drifted from the stale view. `expected.py` is the
ground truth: the current on-disk file with the intended change applied.

Every payload is derived mechanically from (stale, changed_stale):
  - payload.udiff        `diff -u stale changed_stale` with a/file.py b/file.py labels
  - payload.editblock    aider SEARCH/REPLACE block(s), minimal target region
  - payload.strreplace.json  list of {old_str, new_str} calls (str_replace_editor style)
  - payload.wholefile    the full changed_stale content (whole-file rewrite)
  - payload.applypatch   OpenAI apply_patch V4A ("*** Begin Patch", context lines,
                         no line numbers), derived from difflib opcodes over
                         (stale, changed_stale) with 3 context lines per hunk
  - payload.cline        Cline replace_in_file SEARCH/REPLACE blocks
                         ("------- SEARCH / ======= / +++++++ REPLACE"),
                         same minimal regions as payload.editblock

Rerun: python3 generate.py  (writes scenario dirs next to this script)
"""

import difflib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

# --------------------------------------------------------------------------
# Base file (the stale view for most scenarios)
# --------------------------------------------------------------------------

BASE = '''\
"""Small calculator used by the edit-format benchmark."""

VERSION = "1.0.0"


def add(a, b):
    if not isinstance(a, (int, float)):
        raise TypeError("a must be a number")
    return a + b


def subtract(a, b):
    if not isinstance(a, (int, float)):
        raise TypeError("a must be a number")
    return a - b


def multiply(a, b):
    return a * b


def divide(a, b):
    # TODO: handle divide by zero
    return a / b


def apply_op(op, a, b):
    ops = {
        "add": add,
        "sub": subtract,
        "mul": multiply,
        "div": divide,
    }
    if op not in ops:
        raise KeyError(f"unknown op: {op}")
    return ops[op](a, b)


def main():
    import sys

    op, a, b = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
    print(apply_op(op, a, b))


if __name__ == "__main__":
    main()
'''

# --------------------------------------------------------------------------
# Intended changes, expressed as (search, replace) pairs on the stale view.
# These are the minimal regions a competent model would target.
# --------------------------------------------------------------------------

DIVIDE_OLD = '''\
def divide(a, b):
    # TODO: handle divide by zero
    return a / b
'''
DIVIDE_NEW = '''\
def divide(a, b):
    if b == 0:
        raise ZeroDivisionError("division by zero is not allowed")
    return a / b
'''

VERSION_OLD = 'VERSION = "1.0.0"\n'
VERSION_NEW = 'VERSION = "1.1.0"\n'

POW_OLD = '''\
def multiply(a, b):
    return a * b
'''
POW_NEW = '''\
def multiply(a, b):
    return a * b


def power(a, b):
    return a ** b
'''

OPS_OLD = '''\
        "div": divide,
'''
OPS_NEW = '''\
        "div": divide,
        "pow": power,
'''

# The duplicated validation stanza (appears in add() and subtract()).
VALIDATE_OLD = '''\
    if not isinstance(a, (int, float)):
        raise TypeError("a must be a number")
'''
VALIDATE_NEW = '''\
    if not isinstance(a, (int, float)):
        raise TypeError("a must be numeric")
'''

UTIL_CONTENT = '''\
"""Helpers for the calculator."""


def clamp(x, lo, hi):
    return max(lo, min(hi, x))
'''

# ---- 09-unicode: multibyte file (emoji + CJK) --------------------------------

UNI_BASE = '''\
"""计算器 🧮 helpers with 多字节 characters."""

GREETING = "你好,世界 👋"


def describe(op):
    # 返回操作的中文描述 📝
    names = {
        "add": "加法 ➕",
        "sub": "减法 ➖",
    }
    return names.get(op, "未知 ❓")


def format_result(value):
    # TODO: 处理无穷大 ∞
    return f"结果 → {value} ✅"


def banner():
    return "═" * 20 + " 计算完成 🎉 " + "═" * 20
'''

UNI_OLD = '''\
def format_result(value):
    # TODO: 处理无穷大 ∞
    return f"结果 → {value} ✅"
'''
UNI_NEW = '''\
def format_result(value):
    if value == float("inf"):
        return "结果 → ∞ ♾️"
    return f"结果 → {value} ✅"
'''

# ---- 10-eof-newline: file has no trailing newline ----------------------------

TAIL_OLD = 'if __name__ == "__main__":\n    main()'
TAIL_NEW = 'if __name__ == "__main__":\n    raise SystemExit(main())'

# ---- 12-overlapping-hunks: two edits whose diff contexts overlap -------------

MULT_OLD = '''\
def multiply(a, b):
    return a * b
'''
MULT_NEW = '''\
def multiply(a, b):
    product = a * b
    return product
'''

# ---- 13-indent-only: wrap main()'s statements in an if block -----------------

WRAP_OLD = '''\
def main():
    import sys

    op, a, b = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
    print(apply_op(op, a, b))
'''
WRAP_NEW = '''\
def main():
    import sys

    if len(sys.argv) == 4:
        op, a, b = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
        print(apply_op(op, a, b))
'''


def make_big():
    """~5000-line generated module with a divide() near the tail (96%)."""
    parts = ['"""Large generated module (benchmark fixture)."""\n']
    for i in range(552):
        parts.append(
            f'\n\ndef fn_{i:04d}(x):\n'
            f'    """Generated function {i}."""\n'
            f'    y = x + {i}\n'
            f'    y *= 2\n'
            f'    if y > {i * 3}:\n'
            f'        y -= 1\n'
            f'    return y\n'
        )
        if i == 530:
            parts.append("\n\n" + DIVIDE_OLD)
    return "".join(parts)


def apply_pairs(text, pairs, occurrence=None):
    """Apply (old, new) pairs to text. occurrence=N replaces the Nth match
    (1-based) of a single pair; default requires exactly one occurrence."""
    for old, new in pairs:
        count = text.count(old)
        if occurrence is None:
            assert count == 1, f"expected unique match, found {count}: {old!r}"
            text = text.replace(old, new)
        else:
            assert count >= occurrence
            parts = text.split(old)
            text = old.join(parts[:occurrence]) + new + old.join(parts[occurrence:])
    return text


def editblock(fname, pairs):
    out = []
    for old, new in pairs:
        o = old if old.endswith("\n") else old + "\n"
        n = new if new.endswith("\n") else new + "\n"
        out.append(
            f"{fname}\n```python\n<<<<<<< SEARCH\n{o}=======\n{n}"
            f">>>>>>> REPLACE\n```\n"
        )
    return "\n".join(out)


def cline_blocks(pairs):
    """Cline replace_in_file SEARCH/REPLACE blocks (------- SEARCH / ======= /
    +++++++ REPLACE), same minimal regions as the aider editblock payload."""
    out = []
    for old, new in pairs:
        o = old if old.endswith("\n") else old + "\n"
        n = new if new.endswith("\n") else new + "\n"
        out.append(f"------- SEARCH\n{o}=======\n{n}+++++++ REPLACE\n")
    return "".join(out)


def _logical_lines(text):
    """Split into logical lines; a trailing newline does not create an empty
    trailing line (mirrors how patch formats treat line-based content)."""
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def v4a(stale, changed, fname="file.py", n=3):
    """OpenAI apply_patch V4A update patch: hunks located by context lines
    (no line numbers), derived mechanically via difflib grouped opcodes."""
    a, b = _logical_lines(stale), _logical_lines(changed)
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    out = ["*** Begin Patch", f"*** Update File: {fname}"]
    for group in sm.get_grouped_opcodes(n):
        out.append("@@")
        for tag, i1, i2, j1, j2 in group:
            if tag == "equal":
                out.extend(" " + line for line in a[i1:i2])
            else:
                out.extend("-" + line for line in a[i1:i2])
                out.extend("+" + line for line in b[j1:j2])
    out.append("*** End Patch")
    return "\n".join(out) + "\n"


def v4a_add(fname, content):
    out = ["*** Begin Patch", f"*** Add File: {fname}"]
    out.extend("+" + line for line in _logical_lines(content))
    out.append("*** End Patch")
    return "\n".join(out) + "\n"


def _locate_unique(lines, old_lines):
    hits = [i for i in range(len(lines) - len(old_lines) + 1)
            if lines[i:i + len(old_lines)] == old_lines]
    assert len(hits) == 1, f"expected unique region, found {len(hits)}"
    return hits[0]


def per_pair_hunks(stale, pairs, ctx=3):
    """One hunk per (old, new) pair, each independently derived from the SAME
    stale view with `ctx` context lines — the way a model emits independent
    edits. Adjacent pairs produce hunks whose context regions overlap (a real
    diff tool would merge them; scenario 12 deliberately does not)."""
    lines = _logical_lines(stale)
    hunks = []
    for old, new in pairs:
        old_l, new_l = _logical_lines(old), _logical_lines(new)
        start = _locate_unique(lines, old_l)
        pre = lines[max(0, start - ctx):start]
        post = lines[start + len(old_l):start + len(old_l) + ctx]
        hunks.append((max(0, start - ctx), pre, old_l, new_l, post))
    return hunks


def udiff_overlapping(stale, pairs, ctx=3):
    delta = 0
    out = ["--- a/file.py", "+++ b/file.py"]
    for a_start0, pre, old_l, new_l, post in per_pair_hunks(stale, pairs, ctx):
        a_cnt = len(pre) + len(old_l) + len(post)
        b_cnt = len(pre) + len(new_l) + len(post)
        out.append(f"@@ -{a_start0 + 1},{a_cnt} +{a_start0 + 1 + delta},{b_cnt} @@")
        out.extend(" " + line for line in pre)
        out.extend("-" + line for line in old_l)
        out.extend("+" + line for line in new_l)
        out.extend(" " + line for line in post)
        delta += len(new_l) - len(old_l)
    return "\n".join(out) + "\n"


def v4a_overlapping(stale, pairs, ctx=3):
    out = ["*** Begin Patch", "*** Update File: file.py"]
    for _, pre, old_l, new_l, post in per_pair_hunks(stale, pairs, ctx):
        out.append("@@")
        out.extend(" " + line for line in pre)
        out.extend("-" + line for line in old_l)
        out.extend("+" + line for line in new_l)
        out.extend(" " + line for line in post)
    out.append("*** End Patch")
    return "\n".join(out) + "\n"


def udiff(stale, changed, workdir):
    a, b = workdir / "_a.py", workdir / "_b.py"
    a.write_text(stale)
    b.write_text(changed)
    proc = subprocess.run(
        ["diff", "-u", "--label", "a/file.py", "--label", "b/file.py",
         str(a), str(b)],
        capture_output=True, text=True,
    )
    a.unlink(); b.unlink()
    assert proc.returncode == 1, proc.stderr
    return proc.stdout


def write_scenario(name, *, stale, current, expected, pairs,
                   occurrence=None, current_name="file.py",
                   expected_name=None):
    d = HERE / name
    d.mkdir(parents=True, exist_ok=True)
    changed_stale = apply_pairs(stale, pairs, occurrence)
    (d / "stale.py").write_text(stale)
    if current is not None:
        (d / current_name).write_bytes(
            current.encode() if isinstance(current, str) else current)
    (d / (expected_name or "expected.py")).write_bytes(
        expected.encode() if isinstance(expected, str) else expected)
    (d / "payload.udiff").write_text(udiff(stale, changed_stale, d))
    (d / "payload.editblock").write_text(editblock("file.py", pairs))
    (d / "payload.strreplace.json").write_text(json.dumps(
        [{"old_str": o.rstrip("\n"), "new_str": n.rstrip("\n")}
         for o, n in pairs], indent=2) + "\n")
    (d / "payload.wholefile").write_text(changed_stale)
    (d / "payload.applypatch").write_text(v4a(stale, changed_stale))
    (d / "payload.cline").write_text(cline_blocks(pairs))
    print(f"wrote {name}")


def main():
    # 01-clean: stale == current. Baseline; everything should pass.
    write_scenario(
        "01-clean",
        stale=BASE, current=BASE,
        expected=apply_pairs(BASE, [(DIVIDE_OLD, DIVIDE_NEW)]),
        pairs=[(DIVIDE_OLD, DIVIDE_NEW)],
    )

    # 02-line-shift: 8 lines were prepended (after the docstring) since the
    # stale view. Context is intact, only line numbers moved.
    header = (
        "\nimport logging\n\nlogger = logging.getLogger(__name__)\n"
        "logger.debug(\"calculator loaded\")\n\n\n# telemetry hook added by another change\n"
    )
    shifted = BASE.replace('benchmark."""\n', 'benchmark."""\n' + header, 1)
    write_scenario(
        "02-line-shift",
        stale=BASE, current=shifted,
        expected=apply_pairs(shifted, [(DIVIDE_OLD, DIVIDE_NEW)]),
        pairs=[(DIVIDE_OLD, DIVIDE_NEW)],
    )

    # 03-whitespace: the on-disk file is tab-indented; the agent's stale view
    # (and therefore every payload) is space-indented.
    tabbed = "\n".join(
        line.replace("    ", "\t") if line.startswith("    ") else line
        for line in BASE.split("\n"))
    tabbed_expected = "\n".join(
        line.replace("    ", "\t") if line.startswith("    ") else line
        for line in apply_pairs(BASE, [(DIVIDE_OLD, DIVIDE_NEW)]).split("\n"))
    write_scenario(
        "03-whitespace",
        stale=BASE, current=tabbed, expected=tabbed_expected,
        pairs=[(DIVIDE_OLD, DIVIDE_NEW)],
    )

    # 04-ambiguous: the target stanza appears twice (add and subtract); the
    # intended edit is the SECOND occurrence (inside subtract). The minimal
    # payload matches both. Safe behavior is to refuse; editing the first
    # occurrence corrupts add().
    expected_04 = apply_pairs(BASE, [(VALIDATE_OLD, VALIDATE_NEW)], occurrence=2)
    d = HERE / "04-ambiguous"
    d.mkdir(parents=True, exist_ok=True)
    (d / "stale.py").write_text(BASE)
    (d / "file.py").write_text(BASE)
    (d / "expected.py").write_text(expected_04)
    # udiff generated from the real intended change: hunk context contains
    # `def subtract`, so the diff itself is NOT ambiguous. This is the
    # structural difference under test.
    (d / "payload.udiff").write_text(
        udiff(BASE, expected_04, d))
    (d / "payload.editblock").write_text(
        editblock("file.py", [(VALIDATE_OLD, VALIDATE_NEW)]))
    (d / "payload.strreplace.json").write_text(json.dumps(
        [{"old_str": VALIDATE_OLD.rstrip("\n"),
          "new_str": VALIDATE_NEW.rstrip("\n")}], indent=2) + "\n")
    (d / "payload.wholefile").write_text(expected_04)
    # applypatch generated from the real intended change, like udiff: its
    # hunk context disambiguates the target.
    (d / "payload.applypatch").write_text(v4a(BASE, expected_04))
    (d / "payload.cline").write_text(
        cline_blocks([(VALIDATE_OLD, VALIDATE_NEW)]))
    print("wrote 04-ambiguous")

    # 05-context-drift: a line NEAR the edit region (leading diff context)
    # changed since the stale view; the target region itself is untouched.
    drifted = BASE.replace("    return a * b\n",
                           "    return a * b  # fast path\n", 1)
    write_scenario(
        "05-context-drift",
        stale=BASE, current=drifted,
        expected=apply_pairs(drifted, [(DIVIDE_OLD, DIVIDE_NEW)]),
        pairs=[(DIVIDE_OLD, DIVIDE_NEW)],
    )

    # 06-multi-hunk: three independent changes in one payload; stale == current.
    pairs_06 = [
        (VERSION_OLD, VERSION_NEW),
        (POW_OLD, POW_NEW),
        (DIVIDE_OLD, DIVIDE_NEW),
        (OPS_OLD, OPS_NEW),
    ]
    write_scenario(
        "06-multi-hunk",
        stale=BASE, current=BASE,
        expected=apply_pairs(BASE, pairs_06),
        pairs=pairs_06,
    )

    # 07-new-file: create util.py. udiff uses /dev/null; editblock uses an
    # empty SEARCH; str_replace uses its `create` command; wholefile writes it.
    d = HERE / "07-new-file"
    d.mkdir(parents=True, exist_ok=True)
    (d / "expected_util.py").write_text(UTIL_CONTENT)
    b = d / "_b.py"
    b.write_text(UTIL_CONTENT)
    proc = subprocess.run(
        ["diff", "-u", "--label", "/dev/null", "--label", "b/util.py",
         "/dev/null", str(b)], capture_output=True, text=True)
    b.unlink()
    (d / "payload.udiff").write_text(proc.stdout)
    (d / "payload.editblock").write_text(
        f"util.py\n```python\n<<<<<<< SEARCH\n=======\n{UTIL_CONTENT}"
        f">>>>>>> REPLACE\n```\n")
    (d / "payload.strreplace.json").write_text(json.dumps(
        [{"create": True, "path": "util.py", "file_text": UTIL_CONTENT}],
        indent=2) + "\n")
    (d / "payload.wholefile").write_text(UTIL_CONTENT)
    (d / "payload.applypatch").write_text(v4a_add("util.py", UTIL_CONTENT))
    # Cline creates files via an empty SEARCH block against empty content.
    (d / "payload.cline").write_text(
        f"------- SEARCH\n=======\n{UTIL_CONTENT}+++++++ REPLACE\n")
    print("wrote 07-new-file")

    # 08-crlf: the on-disk file has CRLF line endings; the stale view and all
    # payloads are LF. Expected output keeps CRLF.
    crlf = BASE.replace("\n", "\r\n").encode()
    crlf_expected = apply_pairs(BASE, [(DIVIDE_OLD, DIVIDE_NEW)]) \
        .replace("\n", "\r\n").encode()
    write_scenario(
        "08-crlf",
        stale=BASE, current=crlf, expected=crlf_expected,
        pairs=[(DIVIDE_OLD, DIVIDE_NEW)],
    )

    # 09-unicode: file and edit context are full of emoji + CJK multibyte
    # characters; stale == current. Probes byte/char index handling.
    write_scenario(
        "09-unicode",
        stale=UNI_BASE, current=UNI_BASE,
        expected=apply_pairs(UNI_BASE, [(UNI_OLD, UNI_NEW)]),
        pairs=[(UNI_OLD, UNI_NEW)],
    )

    # 10-eof-newline: the file has NO trailing newline and the edit targets
    # the last lines. Expected output also has no trailing newline.
    stale_10 = BASE[:-1]  # strip the final "\n"
    assert not stale_10.endswith("\n")
    write_scenario(
        "10-eof-newline",
        stale=stale_10, current=stale_10,
        expected=apply_pairs(stale_10, [(TAIL_OLD, TAIL_NEW)]),
        pairs=[(TAIL_OLD, TAIL_NEW)],
    )

    # 11-large-file: ~5000-line generated module; the edit is near the tail.
    # Probes latency (run.py records wall time) and payload size scaling.
    big = make_big()
    n_lines = big.count("\n")
    assert 4500 <= n_lines <= 5500, n_lines
    write_scenario(
        "11-large-file",
        stale=big, current=big,
        expected=apply_pairs(big, [(DIVIDE_OLD, DIVIDE_NEW)]),
        pairs=[(DIVIDE_OLD, DIVIDE_NEW)],
    )

    # 12-overlapping-hunks: two edits (multiply and divide) sit 2 blank lines
    # apart, so with 3 context lines each hunk's context region overlaps the
    # other hunk. A model emitting per-edit hunks produces exactly this; a
    # diff tool would merge them (like `diff -u` does — which is why this
    # scenario builds its context-carrying payloads by hand, one hunk per
    # edit, same stale view). SEARCH-based payloads are structurally
    # unaffected: their target regions are disjoint.
    pairs_12 = [(MULT_OLD, MULT_NEW), (DIVIDE_OLD, DIVIDE_NEW)]
    expected_12 = apply_pairs(BASE, pairs_12)
    d = HERE / "12-overlapping-hunks"
    d.mkdir(parents=True, exist_ok=True)
    (d / "stale.py").write_text(BASE)
    (d / "file.py").write_text(BASE)
    (d / "expected.py").write_text(expected_12)
    (d / "payload.udiff").write_text(udiff_overlapping(BASE, pairs_12))
    (d / "payload.applypatch").write_text(v4a_overlapping(BASE, pairs_12))
    (d / "payload.editblock").write_text(editblock("file.py", pairs_12))
    (d / "payload.cline").write_text(cline_blocks(pairs_12))
    (d / "payload.strreplace.json").write_text(json.dumps(
        [{"old_str": o.rstrip("\n"), "new_str": n.rstrip("\n")}
         for o, n in pairs_12], indent=2) + "\n")
    (d / "payload.wholefile").write_text(expected_12)
    print("wrote 12-overlapping-hunks")

    # 13-indent-only: wrap main()'s statements in an `if` block — the only
    # differences are one new line and the indentation of existing lines.
    # Probes whitespace-fuzzy matchers whose normalization discards exactly
    # the information that constitutes this edit.
    write_scenario(
        "13-indent-only",
        stale=BASE, current=BASE,
        expected=apply_pairs(BASE, [(WRAP_OLD, WRAP_NEW)]),
        pairs=[(WRAP_OLD, WRAP_NEW)],
    )


if __name__ == "__main__":
    sys.exit(main())
