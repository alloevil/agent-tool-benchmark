#!/usr/bin/env python3
"""PDF -> Markdown benchmark runner.

For every (tool, fixture) pair this script:
  1. converts the PDF in a **fresh subprocess** (so import/model-load cost is
     included), twice: run 1 = cold start (first call, would include any model
     download), run 2 = warm (OS caches + any downloaded models present);
  2. counts output bytes and cl100k_base tokens (tiktoken);
  3. scores the output against fixtures/expected/<name>.json with the purely
     mechanical string checks documented below.

Scoring is deliberately dumb string matching — no LLM, no fuzzy similarity:

  * heading_recall   — fraction of expected headings that appear on a line
                       starting with 1-6 '#' characters (markdown emphasis
                       stripped, whitespace collapsed, substring match on the
                       heading line). A tool that emits the text without a
                       '#' prefix scores 0 for that heading: the benchmark is
                       about producing *markdown structure*, not just text.
  * sentence_recall  — fraction of expected key sentences present as a
                       substring of the whitespace-collapsed output (markdown
                       decoration characters removed first, so **bold** or
                       pipe-table framing does not break the match).
  * cell_recall      — same substring test applied to every table cell value
                       (fixture 02 only).
  * code_recall      — same substring test applied to every source line of
                       the code block (fixture 04 only). Collapsing
                       whitespace means indentation fidelity is NOT scored,
                       only content survival.
  * reading_order    — fixture 03 only. expected JSON lists ordered pairs
                       [A, B]; a pair passes iff both sentences are found and
                       A's first occurrence index < B's. Column-wise reading
                       (all left-column text before right-column) passes all
                       pairs; naive top-to-bottom-across-both-columns fails
                       the cross-column pairs.
  * cjk_intact       — fixture 05 only. Each Chinese sentence must appear
                       verbatim, character for character, after removing ALL
                       whitespace from the output (CJK text has no spaces, so
                       line wrapping inside a sentence is forgiven; any
                       dropped/mojibake character fails the sentence).

Usage:
    ../../.venv/bin/python run.py            # run matrix, write results.json
    <python> run.py --not-run 'TOOL=reason'  # force-record a column as not_run
    <python> run.py --convert TOOL IN OUT    # internal single-conversion mode

docling / marker columns: run.py looks for dedicated interpreters via the
DOCLING_PYTHON / MARKER_PYTHON env vars (they need their own venv: torch).
If the import probe fails the column is recorded as status="not_run" with
the captured error instead of numbers.
"""

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures"
EXPECTED = FIXTURES / "expected"

FIXTURE_NAMES = ["01-simple", "02-table", "03-two-column",
                 "04-code-and-list", "05-cjk"]

# ---------------------------------------------------------------- converters
# Each converter runs inside `run.py --convert` in a fresh subprocess.

def convert_pdftotext(pdf: str) -> str:
    # Baseline: poppler's pdftotext in default (layout-analysing) mode.
    # Emits plain text, not markdown — headings can never carry '#'.
    out = subprocess.run(["/usr/bin/pdftotext", pdf, "-"],
                         capture_output=True, check=True)
    return out.stdout.decode("utf-8")


def convert_pymupdf4llm(pdf: str) -> str:
    import pymupdf4llm
    return pymupdf4llm.to_markdown(pdf)


def convert_markitdown(pdf: str) -> str:
    from markitdown import MarkItDown
    return MarkItDown().convert(pdf).text_content


def convert_docling(pdf: str) -> str:
    from docling.document_converter import DocumentConverter
    return DocumentConverter().convert(pdf).document.export_to_markdown()


def convert_marker(pdf: str) -> str:
    from marker.converters.pdf import PdfConverter
    from marker.models import create_model_dict
    from marker.output import text_from_rendered
    converter = PdfConverter(artifact_dict=create_model_dict())
    text, _, _ = text_from_rendered(converter(pdf))
    return text


CONVERTERS = {
    "pdftotext": convert_pdftotext,
    "pymupdf4llm": convert_pymupdf4llm,
    "markitdown": convert_markitdown,
    "docling": convert_docling,
    "marker": convert_marker,
}

# Interpreter used for each tool's subprocess. docling/marker need their own
# torch-bearing venv, supplied via env var; everything else runs on the
# interpreter that launched run.py.
TOOL_PYTHON = {
    "docling": os.environ.get("DOCLING_PYTHON", sys.executable),
    "marker": os.environ.get("MARKER_PYTHON", sys.executable),
}


def probe_tool(tool: str) -> str | None:
    """Return None if the tool is importable in its interpreter, else the error."""
    if tool == "pdftotext":
        return None if Path("/usr/bin/pdftotext").exists() else "/usr/bin/pdftotext missing"
    py = TOOL_PYTHON.get(tool, sys.executable)
    mod = {"pymupdf4llm": "pymupdf4llm", "markitdown": "markitdown",
           "docling": "docling", "marker": "marker"}[tool]
    r = subprocess.run([py, "-c", f"import {mod}"], capture_output=True, text=True)
    if r.returncode == 0:
        return None
    return (r.stderr.strip().splitlines() or ["import failed"])[-1]


# ------------------------------------------------------------------ scoring

def collapse(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def haystacks(md: str):
    """(plain, decoration-stripped, no-whitespace) haystacks."""
    plain = collapse(md)
    stripped = collapse(re.sub(r"[*_`>#|\\]", " ", md))
    nows = re.sub(r"\s+", "", md)
    return plain, stripped, nows


def present(needle: str, plain: str, stripped: str) -> bool:
    n = collapse(needle)
    ns = collapse(re.sub(r"[*_`>#|\\]", " ", needle))
    return n in plain or ns in stripped


def heading_lines(md: str) -> list[str]:
    out = []
    for line in md.splitlines():
        m = re.match(r"^\s{0,3}(#{1,6})\s+(.*)$", line)
        if m:
            text = re.sub(r"[*_`#]", "", m.group(2))
            out.append(collapse(text))
    return out


def score(md: str, exp: dict) -> dict:
    plain, stripped, nows = haystacks(md)
    s: dict = {}

    heads = heading_lines(md)
    want = exp.get("headings", [])
    hit = sum(1 for h in want if any(collapse(h) in line for line in heads))
    s["heading_recall"] = round(hit / len(want), 3) if want else None

    sents = exp.get("key_sentences", [])
    if sents:
        hit = sum(1 for k in sents if present(k, plain, stripped))
        s["sentence_recall"] = round(hit / len(sents), 3)

    cells = exp.get("cells")
    if cells:
        hit = sum(1 for c in cells if present(c, plain, stripped))
        s["cell_recall"] = round(hit / len(cells), 3)

    code = exp.get("code_lines")
    if code:
        hit = sum(1 for c in code if collapse(c) in plain or collapse(c) in stripped)
        s["code_recall"] = round(hit / len(code), 3)

    pairs = exp.get("order_pairs")
    if pairs:
        ok = 0
        for a, b in pairs:
            # first-occurrence indexes in the decoration-stripped haystack
            ia = stripped.find(collapse(re.sub(r"[*_`>#|\\]", " ", a)))
            ib = stripped.find(collapse(re.sub(r"[*_`>#|\\]", " ", b)))
            if ia >= 0 and ib >= 0 and ia < ib:
                ok += 1
        s["order_pairs_ok"] = f"{ok}/{len(pairs)}"
        s["reading_order_correct"] = ok == len(pairs)

    cjk = exp.get("cjk_sentences")
    if cjk:
        hit = sum(1 for c in cjk if re.sub(r"\s+", "", c) in nows)
        s["cjk_intact"] = round(hit / len(cjk), 3)

    return s


# ------------------------------------------------------------------- runner

def timed_convert(tool: str, pdf: Path, out: Path) -> float:
    py = TOOL_PYTHON.get(tool, sys.executable)
    t0 = time.perf_counter()
    r = subprocess.run(
        [py, str(HERE / "run.py"), "--convert", tool, str(pdf), str(out)],
        capture_output=True, text=True, timeout=1800,
    )
    dt = time.perf_counter() - t0
    if r.returncode != 0:
        raise RuntimeError(f"{tool} on {pdf.name} failed:\n{r.stderr[-2000:]}")
    return dt


def main(forced_not_run: dict[str, str] | None = None):
    import tiktoken
    enc = tiktoken.get_encoding("cl100k_base")
    forced_not_run = forced_not_run or {}

    results: dict = {"tools": {}}
    for tool in CONVERTERS:
        if tool in forced_not_run:
            results["tools"][tool] = {"status": "not_run",
                                      "reason": forced_not_run[tool]}
            print(f"[skip] {tool}: {forced_not_run[tool]}")
            continue
        err = probe_tool(tool)
        if err:
            results["tools"][tool] = {"status": "not_run", "reason": err}
            print(f"[skip] {tool}: {err}")
            continue

        entry: dict = {"status": "ok", "fixtures": {}}
        for name in FIXTURE_NAMES:
            pdf = FIXTURES / f"{name}.pdf"
            exp = json.loads((EXPECTED / f"{name}.json").read_text("utf-8"))
            out = HERE / "outputs" / tool / f"{name}.md"
            out.parent.mkdir(parents=True, exist_ok=True)

            cold = timed_convert(tool, pdf, out)
            first = out.read_bytes()
            warm = timed_convert(tool, pdf, out)
            md = out.read_text("utf-8")
            rec = {
                "cold_s": round(cold, 3),
                "warm_s": round(warm, 3),
                "output_bytes": len(md.encode("utf-8")),
                "output_tokens": len(enc.encode(md)),
                "deterministic": first == md.encode("utf-8"),
            }
            rec.update(score(md, exp))
            entry["fixtures"][name] = rec
            print(f"[done] {tool:12s} {name:18s} warm={warm:6.2f}s "
                  f"tok={rec['output_tokens']:5d} {json.dumps(score(md, exp), ensure_ascii=False)}")
        results["tools"][tool] = entry

    (HERE / "results.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False) + "\n", "utf-8")
    print("\nwrote results.json")

    # compact summary table
    ran = [t for t, v in results["tools"].items() if v.get("status") == "ok"]
    print(f"\n{'fixture':18s} | " + " | ".join(f"{t:>12s}" for t in ran))
    for name in FIXTURE_NAMES:
        row = []
        for t in ran:
            r = results["tools"][t]["fixtures"][name]
            keys = [k for k in ("heading_recall", "cell_recall", "code_recall",
                                "cjk_intact") if r.get(k) is not None]
            main_metric = r[keys[0]] if keys else ""
            ro = "" if "reading_order_correct" not in r else (
                " RO+" if r["reading_order_correct"] else " RO-")
            row.append(f"{main_metric}{ro} {r['warm_s']:.2f}s")
        print(f"{name:18s} | " + " | ".join(f"{c:>12s}" for c in row))


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "--convert":
        tool, pdf, out = sys.argv[2], sys.argv[3], sys.argv[4]
        md = CONVERTERS[tool](pdf)
        Path(out).write_text(md, encoding="utf-8")
    else:
        forced = {}
        args = sys.argv[1:]
        while args:
            if args[0] == "--not-run" and len(args) >= 2:
                tool, _, reason = args[1].partition("=")
                forced[tool] = reason or "not run"
                args = args[2:]
            else:
                raise SystemExit(f"unknown argument: {args[0]}")
        main(forced)
