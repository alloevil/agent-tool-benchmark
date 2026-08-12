<p align="center">
  <img src="./assets/readme/hero.svg" width="100%" alt="agent-tool-benchmark: hands-on benchmarks of AI agent tooling. Same machine, same tasks, full scripts.">
</p>

<p align="center">
  <a href="https://github.com/alloevil/agent-tool-benchmark/releases/latest"><img alt="Release" src="https://img.shields.io/github/v/release/alloevil/agent-tool-benchmark?logo=github&color=blue"></a>
  <img alt="License" src="https://img.shields.io/github/license/alloevil/agent-tool-benchmark?color=green">
</p>

Every benchmark here is a real run on real tools — same machine, same task suite, same hour. Each one ships with its full methodology, rerunnable task scripts, fixtures, and honest limitations, so you can reproduce the numbers instead of trusting a vendor chart.

## Benchmarks

| Category | Comparison | Date | Verdict |
| --- | --- | --- | --- |
| [browser](browser/) | [ego lite vs browser-use CLI](browser/ego-lite-vs-browser-use/) | 2026-07-28 | ego lite wins for local everyday agent tasks (cross-origin iframe piercing, parallel Spaces, zero tab interference); browser-use CLI remains the only option for servers, CI, and cross-platform |

## Principles

- **Same machine, same tasks.** Every tool in a comparison runs the identical task suite on the identical hardware, within the same session.
- **Reproducible.** All task scripts and fixtures are committed. `bash tasks/<tool>/<task>.sh` reruns any measurement.
- **Honest about limits.** Single runs, network variance, and untested modes (such as autonomous LLM planning) are stated, not hidden.
- **No invented numbers.** Every figure in every chart comes from a captured run. Vendor claims are labeled as claims.

## Planned

- Agent web-search tools (search APIs and scrapers)
- Agent terminal and sandbox execution environments
- Document and spreadsheet agent tools

## License

MIT
