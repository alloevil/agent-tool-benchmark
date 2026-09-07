#!/usr/bin/env python3
"""Search-API benchmark harness.

Runs the same query suite against every provider whose API key is present in
the environment, recording per-query wall latency, response size, token count
(cl100k_base), and hit@5 against committed ground-truth URL substrings.

Keys (provider skipped when unset):
  EXA_API_KEY, TAVILY_API_KEY, SERPER_API_KEY, BRAVE_API_KEY,
  FIRECRAWL_API_KEY, JINA_API_KEY (all six required-per-provider)

Usage: python3 run.py [--queries queries.json] [--out results.json]
"""

import argparse
import json
import os
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent

try:
    import tiktoken
    ENC = tiktoken.get_encoding("cl100k_base")
    def ntokens(s): return len(ENC.encode(s, disallowed_special=()))
except ImportError:  # tokens column becomes byte-based estimate
    def ntokens(s): return len(s) // 4


def post(url, body, headers, timeout=30):
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", **headers})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode()
    return raw, time.perf_counter() - t0


def get(url, headers, timeout=30):
    req = urllib.request.Request(url, headers=headers)
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode()
    return raw, time.perf_counter() - t0


# Each provider fn: (query) -> (raw_response_text, latency_s, result_urls[:5])

def exa(q):
    raw, dt = post("https://api.exa.ai/search",
                   {"query": q, "numResults": 5, "contents": {"text": True}},
                   {"x-api-key": os.environ["EXA_API_KEY"]})
    urls = [r["url"] for r in json.loads(raw).get("results", [])][:5]
    return raw, dt, urls


def tavily(q):
    raw, dt = post("https://api.tavily.com/search",
                   {"query": q, "max_results": 5},
                   {"Authorization": f"Bearer {os.environ['TAVILY_API_KEY']}"})
    urls = [r["url"] for r in json.loads(raw).get("results", [])][:5]
    return raw, dt, urls


def serper(q):
    raw, dt = post("https://google.serper.dev/search",
                   {"q": q, "num": 5},
                   {"X-API-KEY": os.environ["SERPER_API_KEY"]})
    urls = [r["link"] for r in json.loads(raw).get("organic", [])][:5]
    return raw, dt, urls


def brave(q):
    from urllib.parse import quote
    raw, dt = get(
        f"https://api.search.brave.com/res/v1/web/search?count=5&q={quote(q)}",
        {"X-Subscription-Token": os.environ["BRAVE_API_KEY"],
         "Accept": "application/json"})
    web = json.loads(raw).get("web", {}).get("results", [])
    return raw, dt, [r["url"] for r in web][:5]


def firecrawl(q):
    raw, dt = post("https://api.firecrawl.dev/v2/search",
                   {"query": q, "limit": 5},
                   {"Authorization": f"Bearer {os.environ['FIRECRAWL_API_KEY']}"})
    data = json.loads(raw).get("data", {})
    web = data.get("web", data) if isinstance(data, dict) else data
    urls = [r.get("url") for r in web if isinstance(r, dict)][:5] \
        if isinstance(web, list) else []
    return raw, dt, urls


def jina(q):
    from urllib.parse import quote
    headers = {"Accept": "application/json", "X-Respond-With": "no-content",
               "Authorization": f"Bearer {os.environ['JINA_API_KEY']}"}
    raw, dt = get(f"https://s.jina.ai/?q={quote(q)}", headers)
    urls = [r["url"] for r in json.loads(raw).get("data", [])][:5]
    return raw, dt, urls


PROVIDERS = [
    ("exa", "EXA_API_KEY", exa),
    ("tavily", "TAVILY_API_KEY", tavily),
    ("serper", "SERPER_API_KEY", serper),
    ("brave", "BRAVE_API_KEY", brave),
    ("firecrawl", "FIRECRAWL_API_KEY", firecrawl),
    ("jina", "JINA_API_KEY", jina),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--queries", default=str(HERE / "queries.json"))
    ap.add_argument("--out", default=str(HERE / "results.json"))
    args = ap.parse_args()

    queries = json.loads(Path(args.queries).read_text())
    active = [(n, fn) for n, key, fn in PROVIDERS if os.environ.get(key)]
    print("providers:", ", ".join(n for n, _ in active) or "none (set keys)")

    results = {}
    for name, fn in active:
        results[name] = []
        for q in queries:
            row = {"id": q["id"], "query": q["query"]}
            try:
                raw, dt, urls = fn(q["query"])
                row.update(
                    latency_s=round(dt, 3), bytes=len(raw),
                    tokens=ntokens(raw), urls=urls,
                    hit=any(sub in u for sub in q["expect_url_contains"]
                            for u in urls))
            except Exception as e:  # noqa: BLE001
                row.update(error=str(e)[:200], hit=False)
            results[name].append(row)
            status = "HIT " if row.get("hit") else ("ERR " if "error" in row
                                                    else "miss")
            print(f"{name:10s} {q['id']:24s} {status} "
                  f"{row.get('latency_s', '-'):>7} s  "
                  f"{row.get('tokens', '-'):>7} tok")

    Path(args.out).write_text(json.dumps(results, indent=2) + "\n")
    print(f"\nwrote {args.out}")
    for name, rows in results.items():
        hits = sum(r.get("hit", False) for r in rows)
        lat = [r["latency_s"] for r in rows if "latency_s" in r]
        tok = [r["tokens"] for r in rows if "tokens" in r]
        print(f"{name:10s} hit@5 {hits}/{len(rows)}  "
              f"median latency {sorted(lat)[len(lat)//2] if lat else '-'}s  "
              f"median tokens {sorted(tok)[len(tok)//2] if tok else '-'}")


if __name__ == "__main__":
    main()
