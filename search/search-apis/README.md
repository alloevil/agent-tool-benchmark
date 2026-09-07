# Agent search APIs: Exa vs Tavily vs Serper vs Brave vs Firecrawl vs Jina

**Status: harness + query suite committed; no captured run yet.**
This benchmark requires per-provider API keys and was prepared on a machine
without them (Brave and Jina endpoints additionally time out from this
network without a proxy). Per the repo's no-invented-numbers principle, no
results table is published until a real run is captured.

## What it will measure

Same query suite (8 queries, committed in [`queries.json`](queries.json))
against every provider with a key present, recording per query:

| Metric | Why it matters for agents |
| --- | --- |
| hit@5 | Did a ground-truth URL substring appear in the top 5 results |
| latency | Wall time per call, measured client-side |
| response tokens | cl100k_base tokens of the raw response — what the agent actually pays to read the tool result |
| response bytes | Raw payload size |

The token column is the underexplored one: providers differ by an order of
magnitude in how much they return for the same question, and that cost lands
in the agent's context window on every call.

## Query suite design

8 queries spanning: canonical docs lookup, long-tail error message, niche DB
documentation, exact GitHub repo, recency-sensitive release info, RFC/spec
lookup, CVE lookup, and a Chinese-language query. Ground truth is a set of
acceptable URL substrings per query — deliberately generous (any authoritative
source counts), so hit@5 measures retrieval, not ranking taste.

## Run it

```bash
pip install tiktoken   # optional; falls back to byte-based estimate
export TAVILY_API_KEY=... EXA_API_KEY=... SERPER_API_KEY=... \
       BRAVE_API_KEY=... FIRECRAWL_API_KEY=... JINA_API_KEY=...
python3 run.py         # providers without a key are skipped
```

Writes `results.json` and prints a hit@5 / median-latency / median-token
summary per provider.

## Known limitations (pre-registered)

- Single run per query; search-engine results are nondeterministic and
  time-varying. The run date must be recorded with any published table.
- hit@5 with URL substrings measures "found an authoritative page", not
  answer quality or content extraction fidelity.
- Endpoint shapes verified against provider docs as of 2026-08; `firecrawl`
  uses the v2 `/search` response shape and may need adjusting.
