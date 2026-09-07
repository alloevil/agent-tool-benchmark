#!/usr/bin/env python3
"""Intent-search benchmark: natural-language intent -> code location.

Compares three single-shot retrieval strategies over psf/requests v2.32.3
(src/requests/*.py, indexed subset only):

  zg-hybrid  zg query "<NL intent>"          (FTS + vector, fused)
  zg-fts     zg query --fts "<NL intent>"    (BM25 over the same index, same
                                              NL query -- measures BM25's
                                              robustness to intent phrasing)
  rg         bin/rg -n -w <keyword>          (the pre-committed single keyword
                                              an agent would guess; recorded in
                                              queries.json BEFORE any runs)

Metrics per (tool, query):
  file_hit@5 / file_hit@10   ground-truth file among the first 5/10 DISTINCT
                             files in the ranked output
  strict_hit@5 / strict_hit@10   same window, but additionally the returned
                             line/range must overlap the ground-truth
                             function's line range
  tokens                     tiktoken cl100k_base count of the tool's full
                             raw stdout (what an agent would ingest)
  latency_s                  median of 3 runs of the full CLI invocation

Also records zg index build time (cold: .zvec-grep is deleted and rebuilt)
and on-disk index size.

Run with the repo venv (has tiktoken):
  ../../.venv/bin/python run.py
"""

import ast
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORPUS = HERE / "corpus"
SRC = CORPUS / "src" / "requests"
RG = HERE.parent / "code-search" / "bin" / "rg"
INDEX_DIR = CORPUS / ".zvec-grep"
EMBEDDING = "local/potion-retrieval-32m"
REPS = 3
LIMIT = 10

ENV = dict(os.environ)
ENV["PATH"] = str(Path.home() / ".nvm/versions/node/v22.23.2/bin") + ":" + ENV["PATH"]

QUERIES = json.loads((HERE / "queries.json").read_text())["queries"]

import tiktoken  # noqa: E402  (repo .venv)

ENC = tiktoken.get_encoding("cl100k_base")


# --------------------------------------------------------------------------
# Sanity checks: every ground-truth entry must agree with the checkout.
# --------------------------------------------------------------------------

def function_ranges(pyfile: Path):
    """name -> list of (decorator-inclusive start, end) line ranges."""
    out = {}
    tree = ast.parse(pyfile.read_text())
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            start = min([node.lineno] + [d.lineno for d in node.decorator_list])
            out.setdefault(node.name, []).append((start, node.end_lineno))
    return out


def sanity_check():
    errors = []
    if not SRC.is_dir():
        sys.exit("corpus missing -- run ./fetch_corpus.sh first")
    sha = subprocess.run(
        ["git", "-C", str(CORPUS), "rev-parse", "HEAD"],
        capture_output=True, text=True,
    ).stdout.strip()
    if sha != "0e322af87745eff34caffe4df68456ebc20d9068":
        errors.append(f"corpus at unexpected commit {sha}")
    ranges_cache = {}
    for q in QUERIES:
        for gt in q["ground_truth"]:
            f = CORPUS / gt["file"]
            if not f.is_file():
                errors.append(f"{q['id']}: missing file {gt['file']}")
                continue
            if f not in ranges_cache:
                ranges_cache[f] = function_ranges(f)
            fn, lines = gt["function"], tuple(gt["lines"])
            if fn not in ranges_cache[f]:
                errors.append(f"{q['id']}: no function {fn} in {gt['file']}")
            elif lines not in ranges_cache[f][fn]:
                errors.append(
                    f"{q['id']}: {gt['file']}:{fn} range {lines} not in "
                    f"AST ranges {ranges_cache[f][fn]}"
                )
    if errors:
        print("SANITY CHECK FAILED:", file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        sys.exit(1)
    print(f"sanity check OK: {len(QUERIES)} queries, corpus at {sha[:12]}")


# --------------------------------------------------------------------------
# Index build (cold, timed)
# --------------------------------------------------------------------------

def build_index():
    if INDEX_DIR.exists():
        shutil.rmtree(INDEX_DIR)
    t0 = time.perf_counter()
    proc = subprocess.run(
        ["zg", "index", "--embedding", EMBEDDING, "-g", "src/requests/*.py"],
        cwd=CORPUS, env=ENV, capture_output=True, text=True,
    )
    dt = time.perf_counter() - t0
    if proc.returncode != 0:
        sys.exit(f"zg index failed:\n{proc.stderr}")
    size = sum(p.stat().st_size for p in INDEX_DIR.rglob("*") if p.is_file())
    print(f"zg index built in {dt:.1f}s, {size / 1e6:.1f} MB on disk")
    return {"build_time_s": round(dt, 1), "disk_bytes": size}


# --------------------------------------------------------------------------
# Adapters. Each returns (raw_stdout, hits) where hits is an ordered list of
# (relpath, start_line, end_line).
# --------------------------------------------------------------------------

ZG_HIT = re.compile(r"^#\d+ matchedBy=\S+ (.+?):(\d+)-(\d+)$", re.M)


def run_zg(nl_query, fts_only):
    cmd = ["zg", "query"]
    if fts_only:
        cmd += ["--fts", nl_query]
    else:
        cmd.append(nl_query)
    cmd += ["--limit", str(LIMIT), "--mode", "direct"]
    proc = subprocess.run(cmd, cwd=CORPUS, env=ENV, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.exit(f"zg query failed ({nl_query!r}):\n{proc.stderr}")
    hits = [(m[0], int(m[1]), int(m[2])) for m in ZG_HIT.findall(proc.stdout)]
    return proc.stdout, hits


def run_rg(keyword):
    proc = subprocess.run(
        [str(RG), "-n", "-w", keyword, "src/requests"],
        cwd=CORPUS, env=ENV, capture_output=True, text=True,
    )
    if proc.returncode not in (0, 1):  # 1 = no matches
        sys.exit(f"rg failed ({keyword!r}):\n{proc.stderr}")
    hits = []
    for line in proc.stdout.splitlines():
        parts = line.split(":", 2)
        if len(parts) == 3 and parts[1].isdigit():
            hits.append((parts[0], int(parts[1]), int(parts[1])))
    return proc.stdout, hits


# --------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------

def score(hits, ground_truth):
    gt_files = {gt["file"] for gt in ground_truth}
    gt_ranges = {}
    for gt in ground_truth:
        gt_ranges.setdefault(gt["file"], []).append(tuple(gt["lines"]))

    distinct = []  # distinct files in first-seen order
    file_at = {5: False, 10: False}
    strict_at = {5: False, 10: False}
    for f, a, b in hits:
        if f not in distinct:
            distinct.append(f)
        window = len(distinct)  # this hit's file is the `window`-th distinct file
        overlap = any(a <= e and b >= s for s, e in gt_ranges.get(f, []))
        for k in (5, 10):
            if window <= k:
                if f in gt_files:
                    file_at[k] = True
                if overlap:
                    strict_at[k] = True
    return {
        "file_hit@5": file_at[5], "file_hit@10": file_at[10],
        "strict_hit@5": strict_at[5], "strict_hit@10": strict_at[10],
        "n_hits": len(hits), "n_distinct_files": len(distinct),
    }


def timed(fn, *args):
    times, out = [], None
    for _ in range(REPS):
        t0 = time.perf_counter()
        out = fn(*args)
        times.append(time.perf_counter() - t0)
    return out, statistics.median(times)


# --------------------------------------------------------------------------

TOOLS = {
    "zg-hybrid": lambda q: run_zg(q["query"], fts_only=False),
    "zg-fts": lambda q: run_zg(q["query"], fts_only=True),
    "rg": lambda q: run_rg(q["rg_keyword"]),
}


def main():
    sanity_check()
    index_stats = build_index()

    per_query = []
    for q in QUERIES:
        row = {"id": q["id"], "tier": q["tier"], "query": q["query"],
               "rg_keyword": q["rg_keyword"], "tools": {}}
        for tool, fn in TOOLS.items():
            (raw, hits), lat = timed(fn, q)
            s = score(hits, q["ground_truth"])
            s["tokens"] = len(ENC.encode(raw))
            s["latency_s"] = round(lat, 3)
            row["tools"][tool] = s
            print(f"{q['id']:22s} {tool:10s} file@5={int(s['file_hit@5'])} "
                  f"strict@5={int(s['strict_hit@5'])} tokens={s['tokens']:5d} "
                  f"{s['latency_s']:.2f}s")
        per_query.append(row)

    # aggregates: overall and per tier
    def agg(rows, tool):
        n = len(rows)
        get = lambda m: sum(r["tools"][tool][m] for r in rows)
        return {
            "n": n,
            "file_hit@5": get("file_hit@5"), "file_hit@10": get("file_hit@10"),
            "strict_hit@5": get("strict_hit@5"), "strict_hit@10": get("strict_hit@10"),
            "median_tokens": statistics.median(r["tools"][tool]["tokens"] for r in rows),
            "total_tokens": get("tokens"),
            "median_latency_s": round(statistics.median(
                r["tools"][tool]["latency_s"] for r in rows), 3),
        }

    summary = {"overall": {}, "by_tier": {}}
    for tool in TOOLS:
        summary["overall"][tool] = agg(per_query, tool)
    for tier in ("named-direct", "vocab-gap", "conceptual"):
        rows = [r for r in per_query if r["tier"] == tier]
        summary["by_tier"][tier] = {tool: agg(rows, tool) for tool in TOOLS}

    results = {
        "corpus": {
            "repo": "psf/requests", "tag": "v2.32.3",
            "commit": "0e322af87745eff34caffe4df68456ebc20d9068",
            "scope": "src/requests/*.py",
        },
        "zg_index": index_stats,
        "config": {"zg_limit": LIMIT, "reps": REPS, "embedding": EMBEDDING,
                   "zg_mode": "direct", "tokenizer": "cl100k_base"},
        "summary": summary,
        "per_query": per_query,
    }
    (HERE / "results.json").write_text(json.dumps(results, indent=2) + "\n")

    print("\n=== summary (hits out of {} queries) ===".format(len(per_query)))
    hdr = f"{'tool':10s} {'file@5':>7s} {'file@10':>8s} {'strict@5':>9s} {'strict@10':>10s} {'med.tok':>8s} {'med.lat':>8s}"
    print(hdr)
    for tool in TOOLS:
        a = summary["overall"][tool]
        print(f"{tool:10s} {a['file_hit@5']:>7d} {a['file_hit@10']:>8d} "
              f"{a['strict_hit@5']:>9d} {a['strict_hit@10']:>10d} "
              f"{a['median_tokens']:>8.0f} {a['median_latency_s']:>7.2f}s")
    print("\nwrote results.json")


if __name__ == "__main__":
    main()
