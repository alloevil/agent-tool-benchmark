# agent-tool-benchmark

对各类 AI agent 工具做同条件、可复现的实测对比。每个 benchmark 独立成目录，附完整方法、脚本与原始结果。

Hands-on, reproducible benchmarks of AI agent tooling. Each benchmark lives in its own directory with methodology, scripts, and raw results.

## Benchmarks

| 类别 | 对比 | 日期 | 结论摘要 |
|---|---|---|---|
| [browser](browser/) | [ego lite vs browser-use CLI](browser/ego-lite-vs-browser-use/) | 2026-07-28 | 本机日常任务 ego lite 占优（跨域 iframe 穿透、并行 Space、零干扰）；服务器/CI/跨平台场景 browser-use 仍是唯一选择 |

## 原则

- **同机同任务**：同一台机器、同一套任务、同一时段运行。
- **可复现**：所有任务脚本与 fixture 入库，`bash` 即可重跑。
- **诚实标注局限**：单次运行、网络波动、未覆盖的模式（如 LLM 自主规划）都写明。

## 计划中

- Agent 搜索工具（web search API / scraper）
- Agent 终端与沙箱执行环境
- 文档/表格类 agent 工具
