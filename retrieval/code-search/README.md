# Code search: how well do retrieval tools find *all* call sites?

Same-machine, same-corpus benchmark of four "find references" strategies —
ripgrep, universal-ctags, tree-sitter, and jedi (LSP semantics) — scored for
recall and precision against a hand-verified ground truth, run on 2026-08-19.

**TL;DR** — Nobody wins outright. ripgrep finds *almost* everything (0.95
recall) but half of what it returns is noise (0.51 precision: docstrings,
comments, same-named methods). jedi is the only tool with perfect precision
(1.00) and the only one that separates `Cache.flush` from `Logger.flush`, but
it goes blind at `getattr` dispatch and **alias renames defeat every tool** —
not one of the four found the `Store(limit=2)` constructor call hiding behind
`import Cache as Store`. ctags is structurally unable to answer the question:
tags files index *definitions*, so its reference recall is 0.00 across the
board.

## What this measures

An agent asked to "rename this function" or "check every caller before
changing this signature" needs the *complete* set of call sites — a missed
site is a bug shipped, a false site is wasted context. This benchmark asks
each tool the same question — *find all references of symbol X* — against a
small synthetic Python project engineered to contain the retrieval traps that
occur in real codebases, and scores the answers against a line-exact ground
truth.

No LLM is involved; each adapter is a deterministic query in `run.py`.

## Environment

| Item | Value |
| --- | --- |
| Date | 2026-08-19 |
| Machine | Intel i7-10700, Linux 6.8.0-136-generic x86_64 |
| ripgrep | 14.1.1 (musl static binary from GitHub releases) |
| universal-ctags | 6.2.0(b0615e0) + readtags (static nightly `uctags-2026.08.18-linux-x86_64`) |
| tree-sitter | 0.24.0 + tree-sitter-python 0.23.6 (pip) |
| jedi | 0.20.0 (pip) — the inference engine behind jedi-language-server; used here via `Script.get_references`, which is what the LSP `textDocument/references` request calls |
| Python | 3.12.8 |

## Task design

### Corpus

`corpus/` is a self-contained 11-file, 266-line Python project, committed to
the repo (nothing is cloned). It runs (`python app.py`) and its checks pass
(`python test_miniproj.py`), so the ground truth is grounded in code that
actually executes. It deliberately contains:

| Trap | Where |
| --- | --- |
| Same-named method on two unrelated classes | `Cache.flush()` vs `Logger.flush()` |
| Double re-export | `handler` defined in `handlers/impl.py`, forwarded by `handlers/__init__.py` **and** `miniproj/__init__.py`, called via the top-level import |
| Dynamic dispatch | `ROUTES = {"ping": handle_ping, ...}` dict table; `getattr(module, "handle_ping")` |
| Pseudo-references in strings | `handler`, `flush`, `normalize` all appear in docstrings/comments; `"flush complete"` in a log string |
| Decorator wrapping | `normalize` is wrapped by `@traced` |
| Alias imports | `import miniproj.textutil as tu` → `tu.normalize()`; `from miniproj.cache import Cache as Store` → `Store(limit=2)` |

### Ground truth

`ground_truth.json` classifies **every** word-boundary occurrence of each
target symbol in the corpus (7 symbols, hand-verified per line):

- **true_sites** — lines a reference finder MUST return: calls, constructor
  calls (including through aliases), dict-table registrations, and the
  `getattr` string (anything you'd have to edit when renaming the symbol);
- **neutral_sites** — definition/import/re-export lines: returning them is
  neither rewarded nor punished (excluded from both recall and precision);
- **trap_sites** — textual look-alikes that are *not* uses.

`run.py` refuses to start unless (a) the recorded token is literally present
at every ground-truth `(file, line)` and (b) no word-boundary occurrence of
any symbol is left unclassified — so ground truth and corpus cannot drift.

### Adapters

| Tool | Query |
| --- | --- |
| ripgrep | `rg -n -w -F <name>` (word-boundary fixed-string, the standard agent move) |
| ctags | `ctags -R --extras=+r --fields=+rn` index, then `readtags -en <name>` |
| tree-sitter | parse all files; report identifiers in call position (`name(...)` or `obj.name(...)`) whose text equals the name |
| jedi | `Script.get_references(line, col)` at the definition site |

Scoring: recall = true sites found / true sites; precision = true sites
found / (results − neutral). Query times are the median of 3 runs.

## Results

Per-symbol **recall / precision** (from `results.json`):

| Symbol (trap) | ripgrep | ctags | tree-sitter | jedi |
| --- | --- | --- | --- | --- |
| `handler` (double re-export, docstring fakes) | 1.00 / 0.50 | 0.00 / – | 1.00 / 1.00 | 1.00 / 1.00 |
| `flush` (two unrelated classes) | 1.00 / 0.31 | 0.00 / 0.00 | 1.00 / 0.50 | 1.00 / 1.00 |
| `Cache` (aliased as `Store`) | 0.67 / 0.50 | 0.00 / – | 0.67 / 1.00 | 0.67 / 1.00 |
| `normalize` (decorated, module alias) | 1.00 / 0.60 | 0.00 / – | 1.00 / 1.00 | 1.00 / 1.00 |
| `handle_ping` (dict table + getattr only) | 1.00 / 1.00 | 0.00 / – | 0.00 / – | 0.50 / 1.00 |
| `route` (control: no traps) | 1.00 / 1.00 | 0.00 / – | 1.00 / 1.00 | 1.00 / 1.00 |
| `Logger` (docstring fakes) | 1.00 / 0.60 | 0.00 / – | 1.00 / 1.00 | 1.00 / 1.00 |
| **micro-average** | **0.95 / 0.51** | **0.00 / 0.00** | **0.86 / 0.82** | **0.91 / 1.00** |

("–" = tool returned nothing scoreable for that symbol, precision undefined.)

Cold start / index build: ctags `-R` build 12.5 ms, tree-sitter full-corpus
parse 1.2 ms, jedi first `get_references` in a fresh process 198 ms; ripgrep
has no index. Warm per-query medians: ctags-readtags 0.6–1.3 ms,
tree-sitter 0.7–1.6 ms, jedi 2.2–9.4 ms, ripgrep 6.5–10.0 ms. On a 266-line
corpus none of this matters; the recall/precision structure is the story.

## Key findings

1. **ripgrep: near-total recall, coin-flip precision.** It found every call
   site except the alias (`Store(...)`) — including both dynamic-dispatch
   sites, since dict registrations and `getattr` strings still contain the
   literal name (text search's accidental superpower). But on `flush` its
   precision was 0.31: 9 of 13 scoreable results were docstrings, comments,
   a log string, and the *other* class's `flush`. An agent consuming raw rg
   output edits `Logger.flush` when it meant `Cache.flush`.
2. **ctags answers a different question.** Recall 0.00 on all 7 symbols:
   tags index *definitions* (plus import references with `--extras=+r`),
   never call sites. Worse than useless for this task on same-named methods —
   its only scoreable result for `flush` was the *wrong* class's definition
   (precision 0.00). Use it for "jump to definition", never for "who calls
   this".
3. **jedi is the precision king and the only type-aware tool.** Perfect 1.00
   precision overall — the only tool that returned `Cache.flush` call sites
   without a single `Logger.flush` contamination, and it followed the double
   re-export and the `tu.` module alias flawlessly. Its blind spot is
   computed names: it found `handle_ping` in the dict table but not via
   `getattr(module, "handle_ping")` (recall 0.50) — the reference exists only
   inside a string, which is exactly what static inference cannot see.
4. **Alias renames defeat everyone.** `from miniproj.cache import Cache as
   Store; ... Store(limit=2)` — 0/4 tools connected `Store(...)` back to
   `Cache`. Text tools search the wrong string; tree-sitter matches names
   syntactically; even jedi's `get_references` stops at the aliased import
   line (neutral) and does not chase the new binding. The only recall miss
   jedi has that ripgrep also has — and the single site that would break a
   "rename Cache" refactor with every tool in this table.
5. **tree-sitter is a cheap precision upgrade over grep, with a structural
   ceiling.** Restricting matches to call position erased *all* string/
   comment noise (`handler` precision 0.50 → 1.00 vs rg) at ~rg-level speed.
   But it is name-matching, not type inference: it merged the two `flush`
   methods (0.50 precision), and anything not syntactically a call — dict
   registration, getattr — is invisible (recall 0.00 on `handle_ping`, the
   one symbol where grep beat everything).

## Verdict

- **"Did I find every caller?" (pre-refactor sweep):** ripgrep `-w` — highest
  recall, and the only tool that sees into strings and dispatch tables.
  Treat its output as candidates to verify, not answers.
- **"Which of these is a real reference?":** jedi / an LSP — zero false
  positives here, resolves receivers and re-exports. Budget for its blind
  spot: computed `getattr` names.
- **Best default for an agent:** semantic first, text second — take jedi's
  answer, then run one `rg -w` pass and inspect only the *extra* lines for
  string-borne dispatch. On this corpus that union recovers everything except
  the alias site (20/21 true sites), and each tool covers exactly the other's
  failure mode.
- **ctags:** definitions only. Do not use as a reference finder.
- **Alias imports (`as`)** are a residual risk for every strategy; nothing
  short of executing the code (or an alias-chasing index) catches
  `Store(limit=2)`.

## Reproduce

```bash
cd retrieval/code-search
./fetch_tools.sh          # downloads pinned rg + ctags/readtags into bin/ (~10 MB, gitignored)
../../.venv/bin/pip install -i https://pypi.tuna.tsinghua.edu.cn/simple \
    jedi 'tree-sitter>=0.24,<0.25' 'tree-sitter-python==0.23.6'
../../.venv/bin/python run.py    # sanity-checks ground truth, runs matrix, writes results.json
```

The corpus itself is executable: `cd corpus && python3 app.py &&
python3 test_miniproj.py`.

## Limitations

- **Synthetic 266-line corpus.** Traps are dense by design; real-world
  precision for text tools is higher on average and recall pressure comes
  from scale instead. Timings on a corpus this small say nothing about
  large-repo behavior (where ctags/tree-sitter indexes pay off and jedi's
  latency grows).
- **Single language (Python).** Dynamic dispatch and alias semantics differ
  per language; tree-sitter and ctags results would change with typed
  languages, and jedi is Python-only.
- **jedi stands in for "LSP references"** because it is the engine inside
  jedi-language-server, but it is one implementation — pyright/pylsp may
  score differently (pyright in particular ships alias-aware rename).
- **ctags was queried via `readtags` over a `--extras=+r` tags file** — its
  best built-in approximation of references. Third-party overlays (e.g.
  GNU GLOBAL/cscope-style reference databases) are a different tool family
  and were out of scope.
- Scoring counts a site as found on `(file, line)` match; column positions
  are not checked (no symbol occurs twice on one line in this corpus, in
  different roles).
