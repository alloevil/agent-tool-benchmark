#!/usr/bin/env python3
"""Code-search recall benchmark: find ALL call sites of a symbol.

Four "find references" adapters run against the synthetic corpus/ project
and are scored per symbol against ground_truth.json:

  ripgrep      word-boundary text search (fixed string, -w)
  ctags        universal-ctags tags file queried with readtags
  tree-sitter  AST parse; identifiers in call position matching the name
  jedi         Script.get_references at the definition (LSP semantics;
               jedi is the engine behind jedi-language-server)

Scoring (per symbol):
  true_sites     lines a reference finder MUST return (calls, alias
                 constructor calls, dict registration, getattr string)
  neutral_sites  definition / import / re-export lines: returning them is
                 neither rewarded nor punished (excluded from both recall
                 numerator/denominator and precision denominator)
  trap_sites     textual look-alikes that are NOT uses (comments,
                 docstrings, strings, same-named methods on other classes)

  recall    = |result ∩ true| / |true|
  precision = |result ∩ true| / |result \\ neutral|

A startup sanity check verifies every ground-truth (file, line) actually
contains the recorded token, and that ground truth is complete: every
word-boundary occurrence of a symbol's name in the corpus is classified.

Usage: ../../.venv/bin/python run.py     (writes results.json)
"""

import json
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORPUS = HERE / "corpus"
BIN = HERE / "bin"
RG = BIN / "rg"
CTAGS = BIN / "ctags"
READTAGS = BIN / "readtags"
TAGS_FILE = HERE / "tags"
REPS = 3

GT = json.loads((HERE / "ground_truth.json").read_text())["symbols"]

PY_FILES = sorted(p for p in CORPUS.rglob("*.py"))
SOURCES = {str(p.relative_to(CORPUS)): p.read_text().splitlines() for p in PY_FILES}


# --------------------------------------------------------------------------
# Sanity checks: ground truth must agree with the corpus, byte for byte.
# --------------------------------------------------------------------------

def sanity_check():
    errors = []
    for sym in GT:
        classified = set()
        for cat in ("true_sites", "neutral_sites", "trap_sites"):
            for site in sym[cat]:
                key = (site["file"], site["line"])
                classified.add(key)
                lines = SOURCES.get(site["file"])
                if lines is None or site["line"] > len(lines):
                    errors.append(f"{sym['name']}: {key} out of range")
                    continue
                if site["token"] not in lines[site["line"] - 1]:
                    errors.append(
                        f"{sym['name']}: token {site['token']!r} not on "
                        f"{site['file']}:{site['line']}: "
                        f"{lines[site['line'] - 1]!r}"
                    )
        d = sym["definition"]
        if (d["file"], d["line"]) not in classified:
            errors.append(f"{sym['name']}: definition not classified")
        # Completeness: every word-boundary occurrence of the name must be
        # classified, otherwise precision would punish tools for lines the
        # ground truth forgot.
        pat = re.compile(r"(?<![\w])" + re.escape(sym["name"]) + r"(?![\w])")
        for relpath, lines in SOURCES.items():
            for i, line in enumerate(lines, 1):
                if pat.search(line) and (relpath, i) not in classified:
                    errors.append(
                        f"{sym['name']}: unclassified occurrence at "
                        f"{relpath}:{i}: {line!r}"
                    )
    if errors:
        for e in errors:
            print("SANITY FAIL:", e, file=sys.stderr)
        sys.exit(1)


# --------------------------------------------------------------------------
# Adapters. Each returns a set of (relpath, line) candidate reference sites.
# --------------------------------------------------------------------------

def rg_find(symbol):
    proc = subprocess.run(
        [str(RG), "-n", "-w", "-F", symbol["name"], "--no-heading", "."],
        cwd=CORPUS, capture_output=True, text=True,
    )
    out = set()
    for line in proc.stdout.splitlines():
        path, lineno, _ = line.split(":", 2)
        out.add((path.lstrip("./"), int(lineno)))
    return out


def ctags_build_index():
    t0 = time.perf_counter()
    subprocess.run(
        [str(CTAGS), "-R", "--extras=+r", "--fields=+rn", "--excmd=number",
         "-o", str(TAGS_FILE), "corpus"],
        cwd=HERE, check=True, capture_output=True,
    )
    return time.perf_counter() - t0


def ctags_find(symbol):
    proc = subprocess.run(
        [str(READTAGS), "-t", str(TAGS_FILE), "-en", "-", symbol["name"]],
        capture_output=True, text=True,
    )
    out = set()
    for line in proc.stdout.splitlines():
        fields = line.split("\t")
        path = fields[1]
        m = re.search(r"line:(\d+)", line)
        if m and path.startswith("corpus/"):
            out.add((path[len("corpus/"):], int(m.group(1))))
    return out


class TreeSitterIndex:
    def __init__(self):
        import tree_sitter_python as tspython
        from tree_sitter import Language, Parser

        t0 = time.perf_counter()
        self.parser = Parser(Language(tspython.language()))
        self.trees = {
            rel: self.parser.parse(
                "\n".join(lines).encode() + b"\n"
            )
            for rel, lines in SOURCES.items()
        }
        self.build_time = time.perf_counter() - t0

    def find(self, symbol):
        """Identifiers in call position whose text equals the name:
        plain calls `name(...)` and method calls `obj.name(...)`."""
        name = symbol["name"].encode()
        out = set()

        def walk(node, rel):
            if node.type == "call":
                fn = node.child_by_field_name("function")
                target = None
                if fn.type == "identifier":
                    target = fn
                elif fn.type == "attribute":
                    attr = fn.child_by_field_name("attribute")
                    if attr is not None:
                        target = attr
                if target is not None and target.text == name:
                    out.add((rel, target.start_point.row + 1))
            for child in node.children:
                walk(child, rel)

        for rel, tree in self.trees.items():
            walk(tree.root_node, rel)
        return out


class JediIndex:
    def __init__(self):
        import jedi

        self.jedi = jedi
        self.project = jedi.Project(path=str(CORPUS))

    def find(self, symbol):
        d = symbol["definition"]
        path = CORPUS / d["file"]
        line_text = SOURCES[d["file"]][d["line"] - 1]
        col = line_text.index(symbol["name"])
        script = self.jedi.Script(path=str(path), project=self.project)
        refs = script.get_references(d["line"], col, include_builtins=False)
        out = set()
        for ref in refs:
            if ref.module_path is None:
                continue
            try:
                rel = str(Path(ref.module_path).relative_to(CORPUS))
            except ValueError:
                continue
            out.add((rel, ref.line))
        return out


# --------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------

def score(symbol, result):
    true = {(s["file"], s["line"]) for s in symbol["true_sites"]}
    neutral = {(s["file"], s["line"]) for s in symbol["neutral_sites"]}
    traps = {(s["file"], s["line"]) for s in symbol["trap_sites"]}

    hits = result & true
    scored = result - neutral          # neutral results are ignored
    false_pos = scored - true          # traps or unclassified
    recall = len(hits) / len(true) if true else None
    precision = len(hits) / len(scored) if scored else None
    return {
        "recall": round(recall, 3) if recall is not None else None,
        "precision": round(precision, 3) if precision is not None else None,
        "true_total": len(true),
        "hits": len(hits),
        "missed": sorted(f"{f}:{n}" for f, n in true - hits),
        "false_positives": sorted(f"{f}:{n}" for f, n in false_pos),
        "traps_reported": len(false_pos & traps),
        "unclassified_reported": len(false_pos - traps),
    }


def timed(fn, *args):
    times = []
    result = None
    for _ in range(REPS):
        t0 = time.perf_counter()
        result = fn(*args)
        times.append(time.perf_counter() - t0)
    return result, statistics.median(times)


def micro(rows):
    """Micro-average across symbols: pool all hits/targets/results."""
    hits = sum(r["hits"] for r in rows.values())
    true = sum(r["true_total"] for r in rows.values())
    scored = sum(
        r["hits"] + len(r["false_positives"]) for r in rows.values()
    )
    return {
        "recall": round(hits / true, 3),
        "precision": round(hits / scored, 3) if scored else None,
    }


def main():
    sanity_check()
    print(f"sanity check OK: {sum(len(v) for v in SOURCES.values())} corpus "
          f"lines, {len(GT)} symbols")

    cold_start = {}
    tools = {}

    if RG.exists():
        tools["ripgrep"] = rg_find
        cold_start["ripgrep"] = {"note": "no index; grep is always cold", "seconds": 0.0}
    if CTAGS.exists() and READTAGS.exists():
        cold_start["ctags"] = {
            "note": "ctags -R index build",
            "seconds": round(ctags_build_index(), 4),
        }
        tools["ctags"] = ctags_find

    ts = TreeSitterIndex()
    cold_start["tree-sitter"] = {
        "note": "parse all corpus files to ASTs",
        "seconds": round(ts.build_time, 4),
    }
    tools["tree-sitter"] = ts.find

    ji = JediIndex()
    # Jedi cold start: first get_references in a fresh process (module
    # import + initial inference), measured on the first symbol.
    t0 = time.perf_counter()
    ji.find(GT[0])
    cold_start["jedi"] = {
        "note": "first get_references call (in-process caches empty)",
        "seconds": round(time.perf_counter() - t0, 4),
    }
    tools["jedi"] = ji.find

    results = {}
    for tool, fn in tools.items():
        rows = {}
        for sym in GT:
            found, seconds = timed(fn, sym)
            row = score(sym, found)
            row["query_ms"] = round(seconds * 1000, 2)
            rows[sym["name"]] = row
        results[tool] = {"per_symbol": rows, "micro_avg": micro(rows)}

    versions = {
        "ripgrep": subprocess.run([str(RG), "--version"], capture_output=True,
                                  text=True).stdout.splitlines()[0] if RG.exists() else "not run",
        "ctags": subprocess.run([str(CTAGS), "--version"], capture_output=True,
                                text=True).stdout.splitlines()[0] if CTAGS.exists() else "not run",
        "python": sys.version.split()[0],
    }
    from importlib.metadata import version as pkg_version
    versions["jedi"] = pkg_version("jedi")
    versions["tree-sitter"] = pkg_version("tree-sitter")
    versions["tree-sitter-python"] = pkg_version("tree-sitter-python")

    payload = {
        "versions": versions,
        "corpus": {
            "files": len(SOURCES),
            "lines": sum(len(v) for v in SOURCES.values()),
        },
        "cold_start": cold_start,
        "results": results,
    }
    (HERE / "results.json").write_text(json.dumps(payload, indent=2) + "\n")

    # Console summary table
    print(f"\n{'symbol':<14}", end="")
    for tool in results:
        print(f"{tool:>24}", end="")
    print("\n" + " " * 14 + "".join(f"{'R / P':>24}" for _ in results))
    for sym in GT:
        print(f"{sym['name']:<14}", end="")
        for tool in results:
            row = results[tool]["per_symbol"][sym["name"]]
            r = "-" if row["recall"] is None else f"{row['recall']:.2f}"
            p = "-" if row["precision"] is None else f"{row['precision']:.2f}"
            print(f"{r + ' / ' + p:>24}", end="")
        print()
    print(f"{'micro-avg':<14}", end="")
    for tool in results:
        m = results[tool]["micro_avg"]
        p = "-" if m["precision"] is None else f"{m['precision']:.2f}"
        print(f"{f'{m['recall']:.2f} / {p}':>24}", end="")
    print("\nwrote results.json")


if __name__ == "__main__":
    main()
