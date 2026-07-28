# agent-browser-benchmark

ego lite vs browser-use CLI — 同机、同任务的 agent 浏览器实测对比。

**TL;DR (English):** Hands-on benchmark of two agent-browser tools on the same Mac and the same 5-task suite. Both passed basic scraping, SPA interaction, and login-state reuse. Differentiators: ego lite's `snapshotText()` pierces **cross-origin nested iframes** transparently (browser-use requires hand-written CDP `Target.attachToTarget`), and ego lite runs **parallel isolated Spaces** locally (browser-use local mode shares your real Chrome tabs). browser-use retains cross-platform / headless-server / cloud-infra advantages.

## 环境

| 项 | 值 |
|---|---|
| 日期 | 2026-07-28 |
| 机器 | Apple M5 Max, macOS 26.5 (Darwin 25.5.0) |
| browser-use CLI | 0.1.8（attach 本机真实 Chrome，CDP 模式） |
| ego lite | ego-browser 0.4.5.5 / Chromium 150.0.7871.101 / Node v24.18.0 |
| ego 初始化 | 首次启动迁移了 Chrome 数据（登录态 + localStorage） |

两者均为脚本直驱（agent 写代码一次执行多步），非"LLM 自主规划"模式，因此测的是**工具能力与工效**，不是模型成功率。

## 任务设计

| # | 任务 | 考察点 |
|---|---|---|
| 1 | Hacker News top 5 标题+分数 | 静态抓取基线 |
| 2 | TodoMVC：添 3 项、勾 1 项、读计数 | JS 重交互 / 表单可靠性 |
| 3 | 打开 github.com 读当前登录用户名 | 真实登录态复用 |
| 4a | 同源双层嵌套 iframe 提取秘密串 | 帧穿透 |
| 4b | **跨域**双层嵌套 iframe 提取秘密串 | OOPIF 处理（ego 宣称强项） |
| 5 | 并行 / 干扰性观察 | 人机共用浏览器体验 |

iframe fixture 见 [`fixtures/`](fixtures/)，用 `python3 -m http.server 8973`（外层）+ `8974`（跨域内层）本地服务。

## 结果

| 任务 | browser-use CLI | ego lite |
|---|---|---|
| 1. HN top 5 | ✅ 6.4s / 2 次调用 | ✅ 9.7s / 1 次调用（含建 Space） |
| 2. TodoMVC | ✅ 9.1s | ✅ 1.3s（净状态） |
| 3. GitHub 登录态 | ✅ 拿到用户名 | ✅ 拿到用户名（迁移数据生效） |
| 4a. 同源 iframe | ✅ `contentDocument` 直接穿透 | ✅ 同左 |
| 4b. 跨域 iframe | ⚠️ `js()` 返回 None；须手写 CDP `Target.attachToTarget` 才拿到 | ✅ **`snapshotText()` 语义树直接呈现内层文本，零额外操作** |
| 5. 并行 | ✗ 本地共用真实 Chrome 标签页；并行需其云服务 | ✅ 两 Space 并发（1.5s / 2.4s），用户窗口全程不动 |

计时为 `time` 实测 wall time，含 CLI 启动开销；绝对值受网络波动影响，量级和相对关系可参考。

## 关键发现

1. **跨域嵌套 iframe 是真实差距。** browser-use 路径要求 agent 理解 OOPIF 与 CDP target 附着，模型实操中容易在此多轮试错；ego 一次 `snapshotText()` 即得。
2. **Space 隔离 + 本地并行是 ego 独有。** browser-use 本地模式所有任务在用户 Chrome 里开关标签页，肉眼可见跳动；ego 全程后台 Space。
3. **ego 的 Chrome 迁移是快照式复制。** 连测试残留的 TodoMVC localStorage 都带了过来（首轮测试因此出现 6 条重复待办），之后两浏览器状态各自独立演化——依赖会话时效的站点（如银行）需注意。
4. **工效小坑。** browser-use：`close_tab("current")` 别名无效（须传真实 target id）、帮助文档示例的 `evaluate` 实际叫 `js`。ego：首次必须 GUI onboarding，无法纯 CLI 完成；仅支持 macOS。

## 结论

- **本机日常 agent 任务（macOS）**：ego lite 更好——登录态、隔离、并行、iframe 穿透全部实测占优。
- **服务器 / CI / 跨平台 / 需要代理与 CAPTCHA 基建**：browser-use CLI 仍是唯一选择。
- 两者免费且不互斥，按任务场景分工使用。

## 复现

```bash
# browser-use
uv tool install --python 3.12 browser-use
bash tasks/browser-use/01-hn.sh   # 依次 01–04

# ego lite（macOS，需先装 app 并完成 GUI onboarding）
# 下载: https://github.com/citrolabs/ego-lite
bash tasks/ego/01-hn.sh           # 依次 01–05

# iframe fixture
python3 -m http.server 8973 --directory fixtures &
python3 -m http.server 8974 --directory fixtures &
```

## 局限

- 单机单次运行，非多次取均值；网络波动未控制。
- 任务由人工编写脚本完成，未测"LLM 自主规划"模式下的 token 消耗与成功率（ego 官方 2.5× 提速宣称针对该模式，本测不构成验证或反驳）。
- ego 官方对比表称 browser-use 不继承 Chrome 数据；实测其本地模式 attach 真实 Chrome 同样可用登录态，真实差异在**隔离性**而非登录态有无。
