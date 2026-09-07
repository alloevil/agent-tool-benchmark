# Edit-apply formats: udiff vs SEARCH/REPLACE vs str_replace vs apply_patch vs whole-file

Same-machine, same-fixture benchmark of the **edit application layer** used by
coding agents, run on 2026-08-19.

**TL;DR** — On clean files everything works. The differences are structural
failure modes: whole-file rewrite **silently reverts concurrent changes**
(3 CORRUPT), aider's and Cline's SEARCH/REPLACE **edit the wrong occurrence**
when the target text appears twice, and **nobody handles CRLF or tab-retabbed
files well** — the only safe behaviors there were git apply / GNU patch
refusing outright. Cline's fallback matching produced **zero rejections and
the most corruptions of any non-trivial applier** (tied with whole-file at 4).
`str_replace` (Anthropic text-editor semantics, openhands-aci implementation)
was the only format that *refused* the ambiguous edit instead of guessing, and
OpenAI's `apply_patch` joined git apply in refusing overlapping hunks rather
than misplacing them.

## What this measures

Coding agents emit edits in one of a few wire formats; a deterministic applier
then patches the file. This benchmark isolates **the applier**, not the model:
every payload is generated mechanically from the same intended change, and the
question is what each applier does when the on-disk file has drifted from the
agent's stale view of it. No LLM is involved; token costs are counted with
`tiktoken` (cl100k_base).

## Environment

| Item | Value |
| --- | --- |
| Date | 2026-08-19 |
| Machine | Intel i7-10700, Linux 6.8.0-136-generic x86_64 |
| git apply | git 2.43.0 |
| GNU patch | 2.7.6 (`patch -u -F2 -p1`) |
| aider (udiff + editblock appliers) | aider-chat 0.84.0 |
| str_replace | openhands-aci 0.3.3 `OHEditor` (Anthropic `text_editor` semantics) |
| codex-applypatch | OpenAI `apply_patch.py` reference impl (V4A format), vendored from openai/openai-cookbook `gpt4-1_prompting_guide.ipynb` @ commit `2a798f0c` (MIT) → `vendor/apply_patch.py` |
| cline-replace | Cline `constructNewFileContent` (replace_in_file applier), vendored from cline/cline `src/core/assistant-message/diff.ts` @ tag v3.39.2, commit `37152329` (Apache-2.0) → `vendor/cline_diff.ts`, run under bun 1.3.14 via `vendor/cline_apply.ts` |
| whole-file | plain overwrite with the payload |

## Task design

Base fixture: a 50-line Python calculator (scenarios 09 and 11 use their own
generated files). The canonical intended change adds a `ZeroDivisionError`
guard to `divide()`. Each scenario perturbs the on-disk file relative to the
agent's stale view, or stresses a structural property of the payload:

| # | Scenario | What it probes |
| --- | --- | --- |
| 01 | clean | Baseline, stale == disk |
| 02 | line-shift | 8 lines prepended since the stale view (line numbers moved, context intact) |
| 03 | whitespace | Disk file re-indented with tabs; payload uses spaces |
| 04 | ambiguous | Target text appears **twice**; the intended edit is the 2nd occurrence |
| 05 | context-drift | A line *near* the edit (diff leading context) changed |
| 06 | multi-hunk | 4 independent changes in one payload |
| 07 | new-file | Create a file that doesn't exist |
| 08 | crlf | Disk file uses CRLF; payload uses LF |
| 09 | unicode | File and edit context are full of emoji + CJK multibyte characters |
| 10 | eof-newline | File has **no trailing newline**; the edit targets the last lines; expected output also has none |
| 11 | large-file | ~5000-line generated module, edit near the tail (also checks latency stays <100 ms) |
| 12 | overlapping-hunks | Two edits close enough that their 3-line hunk contexts overlap (one hunk per edit, as a model emits them) |
| 13 | indent-only | Wrap a function body in an `if` block — the edit is one new line plus re-indentation of existing lines |

Outcomes: **PASS** (byte-identical to expected), **REJECT** (applier refused,
file untouched — safe), **CORRUPT** (applier reported success but the file is
wrong — the dangerous one).

## Results

| Scenario | git-apply | gnu-patch | aider-udiff | editblock | str_replace | codex-applypatch | cline-replace | whole-file |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 01 clean | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| 02 line-shift | PASS | PASS | PASS | PASS | PASS | PASS | PASS | **CORRUPT** |
| 03 whitespace | REJECT | REJECT | REJECT | REJECT | REJECT | **CORRUPT** | **CORRUPT** | **CORRUPT** |
| 04 ambiguous | PASS | PASS | PASS | **CORRUPT** | REJECT | PASS | **CORRUPT** | PASS |
| 05 context-drift | PASS | PASS | PASS | PASS | PASS | PASS | PASS | **CORRUPT** |
| 06 multi-hunk | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| 07 new-file | PASS | PASS | PASS | PASS | PASS | **CORRUPT** | PASS | PASS |
| 08 crlf | REJECT | REJECT | **CORRUPT** | **CORRUPT** | **CORRUPT** | **CORRUPT** | **CORRUPT** | **CORRUPT** |
| 09 unicode | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| 10 eof-newline | PASS | PASS | **CORRUPT** | **CORRUPT** | PASS | PASS | **CORRUPT** | PASS |
| 11 large-file | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| 12 overlapping-hunks | REJECT | PASS | PASS | PASS | PASS | REJECT | PASS | PASS |
| 13 indent-only | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS |
| **PASS / REJECT / CORRUPT** | **10 / 3 / 0** | **11 / 2 / 0** | 10 / 1 / 2 | 9 / 1 / 3 | 10 / 2 / 1 | 9 / 1 / 3 | 9 / 0 / 4 | 9 / 0 / 4 |

Payload token cost (cl100k_base, sum over all 13 scenarios): cline **914**,
applypatch **1027**, editblock **1033**, udiff **1110**, str_replace **1229**,
whole-file **27756** — dominated by scenario 11, where rewriting the
5000-line file costs 25 099 tokens vs 61–76 for every other format. Over the
original 8 small-file scenarios the totals are: cline 545, applypatch 595,
editblock 622, udiff 637, str_replace 710, whole-file 1768. Per-scenario
numbers are in `payload_tokens.json`.

Latency: all appliers stay far under 100 ms even on the 5000-line file
(slowest cell in scenario 11: cline-replace at 15.1 ms, which includes a bun
subprocess launch; the pure-Python appliers are ≤12 ms). The only >100 ms
cells anywhere in `results.json` are the first aider/openhands import in
scenario 01 (one-time module load, 0.37–0.51 s).

## Key findings

1. **Whole-file rewrite still cannot fail — and still loses concurrent
   edits.** Zero REJECTs, 4 CORRUPTs; scenarios 02 and 05 silently reverted
   the concurrent change. The new scenarios add the cost dimension: on the
   5000-line file the whole-file payload is 25 099 tokens vs ≤76 for every
   diff-shaped format — the 2.8× gap measured on the 50-line file becomes
   ~370× at 5000 lines.
2. **Cline's fallback ladder trades rejections for corruptions.** Its applier
   tries exact match, then line-trimmed match, then block-anchor match, then
   a full-file scan. Result: the only non-trivial applier with **zero**
   REJECTs, and 4 CORRUPTs. In 03-whitespace the line-trimmed fallback
   "found" the tab-indented target and spliced in space-indented replacement
   lines, producing a mixed-indentation file (a syntax hazard in Python); in
   04-ambiguous the full-file scan edited the **first** occurrence (the wrong
   one — `add()` was modified instead of `subtract()`, same corruption as
   aider's editblock).
3. **OpenAI's apply_patch is context-bearing like udiff, but its whitespace
   fuzz reintroduces the guessing.** It PASSes 04-ambiguous for the same
   structural reason udiff does (the `@@`/context lines pin the site), and —
   like git apply — it REJECTs overlapping hunks
   (`Invalid context` — its context cursor only scans forward, so hunk 2's
   overlapping pre-context is unfindable — a safe refusal). But its third-tier
   context match compares whitespace-**stripped** lines, so in 03-whitespace
   it "found" the retabbed context and wrote space-indented lines into the
   tab-indented file — the same mixed-indent corruption as Cline. It also
   CORRUPTs 07-new-file by a single byte: `*** Add File` joins `+` lines with
   `\n` and drops the trailing newline.
4. **Missing trailing newlines are a real corruption class.** In
   10-eof-newline, aider-udiff, editblock, and cline-replace all appended a
   trailing newline that neither the original file nor the expected output
   has (verified: each output is exactly `expected + "\n"`). git apply and
   GNU patch handle it via the `\ No newline at end of file` marker;
   str_replace and apply_patch preserve the missing newline exactly. One
   byte, but byte-exact appliers exist, so it is measurable — and it flips
   editblock's scorecard on what looks like a trivial edit.
5. **Overlapping hunk contexts split the strict from the fuzzy.** git apply
   refuses (hunk 2's context no longer matches after hunk 1 shifted the
   file); GNU patch absorbs it with fuzz/offset; aider-udiff and all
   search-based formats pass because their targets are disjoint even though
   the *contexts* overlap. apply_patch refuses — its sequential
   context-cursor cannot re-find hunk 2's pre-context, which is the safe
   outcome.
6. **Unicode, large files, and indent-only edits are non-events.** All eight
   appliers PASS 09, 11, and 13. Multibyte handling is correct everywhere,
   5000 lines cost milliseconds, and even the whitespace-fuzzy matchers apply
   the indent-only edit correctly — their normalization is applied to
   *finding* the target, not to writing the replacement.
7. **CRLF remains a swamp.** Both new appliers join the corruption column:
   apply_patch and cline-replace each produced mixed LF/CRLF files (Cline's
   output has 4 lone-LF lines in an otherwise-CRLF file). git apply and GNU
   patch still refuse — the only safe behavior observed.
8. **The old tools still hold up.** git apply and GNU patch remain the only
   appliers with zero corruptions across all 13 scenarios; every failure was
   a refusal. GNU patch's fuzz even earns it the best PASS count (11) without
   a single CORRUPT.

## Verdict

- **Safety-critical / multi-writer workspaces:** udiff applied with
  `git apply` — context-bearing and refuses rather than guesses. GNU patch
  adds useful fuzz (passes overlapping hunks) at no observed corruption cost.
- **Model ergonomics + safety:** `str_replace` with occurrence counting
  (Anthropic semantics) is still the best-behaved search-based format: 1
  CORRUPT (CRLF only) and it refuses ambiguity.
- **OpenAI apply_patch (V4A):** structurally sound — context pins ambiguous
  sites, overlaps are refused — but the whitespace-stripping fuzz tier and
  the Add-File trailing-newline bug give it 3 CORRUPTs. Disable the
  strip-level fuzz and fix the newline join and it would rival git apply.
- **SEARCH/REPLACE (aider editblock, Cline replace_in_file):** fine on clean
  files; first-match/fallback semantics make repeated code a
  silent-corruption hazard for both. Cline's extra fallbacks are strictly
  more dangerous than aider's on drifted files (0 rejects, 4 corruptions);
  they exist to absorb *model* sloppiness, which this benchmark doesn't
  reward.
- **Whole-file rewrite:** token cost scales with file size (25k tokens for a
  5k-line file) and it is the only format that loses concurrent edits; use
  only for file creation or single-writer scratch work.

Note this deliberately excludes the *model-side* half of the argument (which
format models emit most accurately — aider's own leaderboards cover that).
An applier that rejects malformed-but-well-intended edits costs a retry
round-trip; an applier that guesses costs a corrupted file.

## Reproduce

```bash
python3 -m venv .venv && .venv/bin/pip install aider-chat openhands-aci tiktoken
# bun ≥1.x on PATH (runs the vendored Cline TypeScript applier)
cd editing/edit-apply-formats
python3 fixtures/generate.py     # regenerate all fixtures + payloads (idempotent)
../../.venv/bin/python run.py    # run the matrix, writes results.json + payload_tokens.json
```

`fixtures/generate.py` is the single source of truth: every payload is derived
mechanically from (stale view, intended change), so adding a scenario or an
applier is a few lines. `vendor/` contains the two vendored appliers verbatim
with source URLs, commits, and licenses in their headers.

## Limitations

- Python-centric fixtures; scenario 09 covers multibyte text but non-UTF-8
  encodings are untested.
- One applier per implementation: aider represents SEARCH/REPLACE and
  flexible udiff, openhands-aci represents `str_replace`, the vendored
  cookbook `apply_patch.py` represents Codex V4A (the Rust implementation in
  openai/codex may differ), and Cline v3.39.2's `constructNewFileContent`
  (v1 strategy, as its tool calls it) represents Cline — the post-v4 SDK
  rewrite may differ. Morph/Relace fast-apply models require a model call and
  were out of scope for a deterministic benchmark.
- CORRUPT is judged byte-exact. Line-ending normalization (scenario 08) and
  the added trailing newline (scenario 10) are arguably benign in some
  toolchains; the ambiguous-edit corruption (scenario 04) and the
  mixed-indentation corruption (scenario 03, codex-applypatch/cline-replace)
  are not.
- Scenario 12's overlapping hunks are built by hand (one hunk per edit, 3
  context lines, same stale view) because `diff -u` merges overlapping
  hunks; this mirrors how a model emits independent edits but is not the
  output of any diff tool.
- cline-replace timings include a bun subprocess launch (~13 ms); in-process
  numbers would be lower.
- Timings are negligible for all appliers and reported only in `results.json`.
