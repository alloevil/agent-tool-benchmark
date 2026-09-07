# Intent search: does natural-language retrieval beat grep for "where is X handled?"

Same-machine benchmark of Alibaba's **zvec-grep (`zg`)** — an indexed
hybrid (BM25 + vector) code retrieval CLI marketed at coding agents — against
a plain ripgrep keyword baseline, on a real codebase (psf/requests v2.32.3),
run on 2026-09-07.

zg's headline claim is that intent-based retrieval cuts agent tool calls by
40–58%. This benchmark does **not** measure agent loops (no LLM is involved);
it measures the foundation that claim rests on: given a single
natural-language intent ("where are HTTP redirects followed and resolved"),
does one `zg query` land on the right code more often — and at what token
cost — than one educated `rg` guess?

**TL;DR** — On 12 intent queries, zg hybrid answered 11/12 with the correct
function in the top 5, zg's BM25-only mode (`--fts`) hit the right *file*
12/12, and ripgrep with a pre-committed keyword guess managed 6/12. The
split is entirely predictable: when the intent word literally appears in the
code (`redirect`, `timeout`), rg ties zg at 4/4 while being ~350× faster;
the moment vocabulary diverges from naming (`pooling`, `credentials`,
`leak`, `resend`), rg goes 0/4 — the keywords match nothing or only a stray
comment — while both zg modes stay at 3–4/4. The token claim, however,
inverts: **zg's output costs 2.3× more tokens than rg's overall** (4,378 vs
1,890 cl100k tokens for all 12 queries), because zg always returns a
fixed-size ranked list while rg's failures are nearly free (0–22 tokens).
zg saves tokens only in the scenario where rg *succeeds noisily* (`timeout`:
655 rg tokens vs 362). And a surprise: on this corpus the pure-BM25 `--fts`
mode found the right file more reliably than the hybrid mode that adds
vectors — the one hybrid miss (`url-credentials`) is a case where vector
similarity actively drowned the lexically-correct answer.

## What this measures

An agent that needs to modify unfamiliar code first has to *find* it. With
grep, it must guess what the author named things; if the guess misses, that's
a wasted round-trip (and the 40–58% fewer-tool-calls pitch is precisely about
eliminating those). This benchmark asks each tool the same 12 questions in a
single shot and scores whether the ground-truth location is in the result —
no reformulation, no second attempt, which is exactly the margin zg claims.

Three adapters, all deterministic CLI invocations in `run.py`:

| Tool | Query |
| --- | --- |
| zg-hybrid | `zg query "<NL intent>" --limit 10 --mode direct` (BM25 + vector, fused) |
| zg-fts | `zg query --fts "<NL intent>" --limit 10 --mode direct` (BM25 only, **same NL sentence** — tests BM25's robustness to intent phrasing, not keyword crafting) |
| rg | `rg -n -w <keyword>` with a **pre-committed** keyword per query, recorded in `queries.json` before any tool was run — the single word an agent unfamiliar with the code's naming would plausibly grep first (e.g. "connection reuse pooling" → `pooling`) |

## Environment

| Item | Value |
| --- | --- |
| Date | 2026-09-07 |
| Machine | Intel i7-10700, Linux 6.8.0-138-generic x86_64 |
| zvec-grep | 0.2.1, embedding `local/potion-retrieval-32m` (local CPU inference), direct mode |
| ripgrep | 14.1.1 (shared static binary in `../code-search/bin/`) |
| Corpus | psf/requests tag v2.32.3, commit `0e322af8`, indexed scope `src/requests/*.py` (18 files, ~5.6k lines of real library code) |
| Tokenizer | tiktoken 0.9.0, `cl100k_base`, counted over each tool's full raw stdout |
| Python | 3.12.8 |

zg index: **6.9 s cold build, 5.8 MB on disk** (the source it indexes is
~230 KB — a 25× storage overhead at this scale).

## Task design

### Queries and ground truth

`queries.json` holds 12 English intent queries in three difficulty tiers,
4 each:

- **named-direct** — the intent word is literally in the code
  (`redirect`, `digest`, `timeout`, `no_proxy`). Grep's home turf.
- **vocab-gap** — the natural way to phrase the intent uses words absent
  from the implementation: "connection reuse pooling" → `HTTPAdapter.
  init_poolmanager`; "login credentials in URL" → `get_auth_from_url`;
  "resent after redirect" → `rewind_body`; "leaking the Authorization
  header" → `should_strip_auth`.
- **conceptual** — the question is about behavior, not a nameable thing:
  "how does it decide response body encoding" → `Response.text` /
  `apparent_encoding`; "counts as truthy" → `Response.__bool__`.

Every ground-truth entry is a `(file, function, start–end lines)` triple.
`run.py` refuses to start unless (a) the corpus is at the pinned commit,
(b) every ground-truth file exists, and (c) every recorded line range
exactly matches the function's AST range (decorators included) in the
checkout — so ground truth and corpus cannot drift.

### Scoring

- **file_hit@k** — a ground-truth file appears within the first k *distinct
  files* of the ranked output (distinct-file counting keeps rg's many-lines-
  per-file output comparable to zg's ranked chunks).
- **strict_hit@k** — same window, but the returned line/range must overlap a
  ground-truth function's line range. Both reported; strict is the honest
  one ("the agent can start reading the right function"), file-level is the
  generous one ("the agent is in the right file").
- **tokens** — cl100k count of the tool's complete stdout, i.e. what an
  agent would actually ingest.
- **latency** — median of 3 full CLI invocations.

## Results

Overall (hits out of 12; from `results.json`):

| Tool | file@5 | file@10 | strict@5 | strict@10 | median tokens | total tokens | median latency |
| --- | --- | --- | --- | --- | --- | --- | --- |
| zg-hybrid | 11 | 11 | 11 | 11 | 362 | 4,378 | 1.76 s |
| zg-fts | **12** | **12** | 10 | 10 | 340 | 4,160 | 1.46 s |
| rg | 6 | 6 | 6 | 6 | 46 | **1,890** | **0.005 s** |

By tier (file@5 / strict@5, out of 4):

| Tier | zg-hybrid | zg-fts | rg |
| --- | --- | --- | --- |
| named-direct | 4 / 4 | 4 / 4 | 4 / 4 |
| vocab-gap | 3 / 3 | 4 / 3 | **0 / 0** |
| conceptual | 4 / 4 | 4 / 3 | 2 / 2 |

Per query (file@5/strict@5, tokens):

| Query | Tier | rg keyword | zg-hybrid | zg-fts | rg |
| --- | --- | --- | --- | --- | --- |
| redirects | named | `redirect` | 1/1, 361 | 1/1, 331 | 1/1, 332 |
| digest-auth | named | `digest` | 1/1, 339 | 1/1, 335 | 1/1, 115 |
| timeout | named | `timeout` | 1/1, 362 | 1/1, 344 | 1/1, 655 |
| no-proxy | named | `no_proxy` | 1/1, 360 | 1/1, 336 | 1/1, 445 |
| connection-pooling | gap | `pooling` | 1/1, 382 | 1/1, 353 | 0/0, 22 |
| url-credentials | gap | `credentials` | **0/0**, 393 | 1/**0**, 372 | 0/0, 22 |
| body-rewind | gap | `resend` | 1/1, 366 | 1/1, 327 | 0/0, 17 |
| auth-leak | gap | `leak` | 1/1, 381 | 1/1, 363 | 0/0, 21 |
| text-encoding | concept | `charset` | 1/1, 363 | 1/1, 335 | 1/1, 192 |
| content-length | concept | `size` | 1/1, 387 | 1/**0**, 354 | 1/1, 69 |
| response-truthiness | concept | `truthy` | 1/1, 359 | 1/1, 385 | **0/0, 0** |
| pagination-links | concept | `pagination` | 1/1, 325 | 1/1, 325 | **0/0, 0** |

## Key findings

1. **The vocabulary gap is real, binary, and exactly where zg earns its
   keep.** All four vocab-gap queries are total rg failures — `pooling`,
   `credentials`, and `leak` each match exactly one docstring/comment line
   (never the implementation), `truthy` and `pagination` match nothing at
   all. Both zg modes answered 3–4 of 4 with the correct function ranked in
   the top 5. If an agent's first grep guess misses like this, the recovery
   round-trips are precisely the tool calls zg claims to eliminate — on this
   axis the claim is directionally supported.
2. **Where naming cooperates, grep concedes nothing.** named-direct:
   4/4 strict for all three tools. rg was 350× faster (5 ms vs 1.5–1.8 s)
   and needed no 6.9 s index or 5.8 MB of state. `redirect` in requests
   lands you in `sessions.py` inside a millisecond; no embedding needed.
3. **The token-saving claim fails on this corpus — zg cost 2.3× more
   overall.** zg's output is a fixed-shape ranked list: ~325–393 tokens
   *every* time, hit or miss. rg's cost is bimodal: heavy when a common
   word matches everywhere (655 for `timeout`, 445 for `no_proxy` — the only
   two queries where zg is meaningfully cheaper), trivial when the guess
   narrowly hits (69–115), and ~free when it misses (0–22). Failed greps are
   cheap in tokens; they cost *round-trips*, not context. So zg's economics
   only work if the avoided follow-up queries are priced in — the
   single-shot token comparison it implicitly invites goes the other way.
4. **BM25 didn't need the vectors — and once, the vectors hurt.** `--fts`
   with the raw NL sentence went 12/12 on files, *beating* hybrid (11/12).
   On `url-credentials`, FTS ranks `get_netrc_auth` (#2, right file, wrong
   function — the query said "URL", not netrc) while hybrid's vector
   component floods the top 10 with thematically-"auth-ish" chunks from
   `sessions.py`/`adapters.py` and pushes `utils.py` out entirely. zg's own
   chunk-level BM25 over symbol-aware chunks is doing most of the work here;
   the embedding (a 32M-param potion model) adds latency (+0.3 s/query) and,
   at least once, noise. Hybrid's edge over FTS is at the *function*
   granularity: 11 vs 10 strict.
5. **strict vs file-level barely differs — when zg finds the file, it finds
   the function.** Only two cells split (both zg-fts): `url-credentials` and
   `content-length`, where FTS ranked a plausible-but-wrong function in the
   right file. Chunk-level retrieval with symbol ranges means a hit is
   usually directly actionable, not just a file name.

## Verdict

- **zg's retrieval quality claim holds where it matters**: intent queries
  whose wording doesn't match the code's naming — the case grep structurally
  cannot handle and agents cannot predict in unfamiliar code. 11–12/12
  file-level on real library code is a strong single-shot result.
- **Its token claim, as a per-call statement, is backwards** — zg costs a
  near-constant ~360 tokens/query while grep misses cost ~0. The saving has
  to come from avoided *iterations*, which this benchmark deliberately does
  not measure.
- **A cheap best-of-both for agents**: grep first (5 ms, free when it
  misses), fall back to intent search only when the keyword guess returns
  nothing useful. On this query set that policy gets 6/12 for ~free and
  recovers the rest for one zg call each — strictly cheaper in both tokens
  and wall time than always-zg (which also pays 6.9 s + 5.8 MB per corpus up
  front).
- The `--fts` mode is underrated: same index, no embedding inference, 0.3 s
  faster, and it went 12/12 on files with raw NL sentences. If you have the
  index anyway, BM25-over-chunks is the workhorse.

## Reproduce

```bash
cd retrieval/intent-search
./fetch_corpus.sh        # shallow-clones psf/requests @ v2.32.3 into corpus/ (gitignored)
PATH=$HOME/.nvm/versions/node/v22.23.2/bin:$PATH \
    ../../.venv/bin/python run.py   # sanity-checks ground truth, rebuilds the
                                    # zg index cold (timed), runs 3 tools x 12
                                    # queries, writes results.json
```

`run.py` deletes and rebuilds `corpus/.zvec-grep/` on every run so the
reported index build time is always cold.

## Limitations

- **Single repository, single language.** requests is small (~5.6k indexed
  lines), idiomatic, and unusually well-commented Python — docstrings give
  BM25 a lot to grab onto. Results on terse, comment-poor, or non-English
  codebases may differ in either direction; index cost also scales with
  corpus size while grep's doesn't.
- **The query set was written by the benchmark author** with the codebase
  open, then ground-truth-verified. Despite the tiering discipline, there is
  survivorship bias risk: queries that felt "askable" made the list. 12
  queries is a signal, not a distribution.
- **No agent loop is measured.** zg's 40–58% figure is about multi-turn tool
  calls; we measure single-shot hit rate and token cost, which bound but do
  not determine loop behavior (e.g. an agent may recover from a bad grep in
  one cheap retry, or waste turns paging through zg output).
- **`rg_keyword` choice is subjective.** Mitigated by pre-committing one
  keyword per query in `queries.json` before running anything, and by
  drawing keywords from the query's own wording — but a different author
  would guess differently, and a real agent gets more than one guess.
- **zg amortized costs are underweighted**: 6.9 s cold index + 5.8 MB disk
  per corpus, ~1.5–1.8 s per query (local CPU embedding at query time for
  hybrid) vs 5 ms for rg. In an interactive agent loop, latency is also a
  cost, just not a token-denominated one.
- Scoring is at file/function granularity with a top-5/top-10 window; it
  does not grade rank position within the window or partial credit for
  adjacent code.
