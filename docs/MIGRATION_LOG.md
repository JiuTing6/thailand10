# Thailand10 迁移计划

> **UPDATE 2026-05-04**：本文档作为历史记录保留。原计划"由 Claude Code Routines（云端）调度"在 2026-05-04 试运行后**放弃**——Anthropic 数据中心出站 IP 被全部 4 个 RSS 源 403 屏蔽（Cloudflare ASN 黑名单）。
>
> **当前实际架构**：Mac mini 本地 cron 9:30am，详见 [`docs/ingest-architecture.md`](ingest-architecture.md)。

---

**目标**：将 `bangkok-news` 项目从 OpenClaw 环境完整搬迁到本机 Claude Code 环境，所有模型调用改用 Claude Max 订阅 token，由 Claude Code Routines（云端）调度。

## ⚠️ 成本铁律（最重要，绝对不能违反）

**绝大多数 LLM 调用必须用 Haiku（`claude-haiku-4-5`）。Sonnet 只用于一处：周四 publish 的选题。**

| 用途 | 模型 | 频次 | 备注 |
|------|------|------|------|
| filter（每条新闻打标签） | **Haiku** | 每天数十次 | 高频、简单分类 |
| dedup（语义去重） | **Haiku** | 每天数十次 | 高频、模式判断 |
| translate（标题/摘要翻译） | **Haiku** | 每天数十次 | 高频、翻译 |
| publish 选题（10 条→1 期） | **Sonnet** | 每周 1 次 | 唯一需要推理质量的环节 |
| Routine 外层 session 本身 | **Haiku**（创建 routine 时显式指定） | 每天/每周触发 | 见下方"成本陷阱" |

**成本陷阱**：Claude Code Routine 的"外层 session"本身也消耗 token。如果创建 routine 时不指定模型，可能默认 Sonnet/Opus——那么即便内部 `subprocess` 调的都是 Haiku，外层编排照样烧贵的。**创建两个 routine 时都必须显式指定 `--model claude-haiku-4-5`**，外层只负责"clone → 跑脚本 → push"这种零思考的工作，Haiku 完全够用。

**Code Review 检查项**：每次改动 `filter.py` / `dedup.py` / `translate.py` / `claude_call.py` / routine prompt，都要 grep 一遍 `sonnet` / `opus` 确认没有意外引入贵模型。

**源**：`/Users/Ade/.openclaw/workspace/bangkok-news/`（保留不动，只读参考。迁移成功稳定后可删除）
**目标**：`/Users/Ade/Projects/Thailand10/`
**GitHub remote（新建）**：`https://github.com/JiuTing6/thailand10.git`（**全新 public repo**，与老 `bangkok-news` 完全分离）
**新发布 URL**：`https://jiuting6.github.io/thailand10/newsroom.html`（GitHub Pages 自动启用）

**仓库策略说明（方案 B）**：
- 不复用老 repo `JiuTing6/bangkok-news`，**全新 repo `JiuTing6/thailand10`** 从零起步
- 不沿用老 repo 的 commit 历史；老 repo 上最后一期内容（2026-04-23）会**永远停在那**
- 老 URL 上的链接不再更新；如果以前对外分享过老 URL，新内容只在新 URL 上有
- 老 repo 与本地老目录都保留作为只读备份，迁移跑稳一段时间后再删除

---

## 已确认的关键决策

| # | 决策 |
|---|------|
| 1 | **`claude` CLI**：本机全局安装 `npm i -g @anthropic-ai/claude-code`，脚本调 `claude -p ...` headless 模式，复用 Claude.app 登录的 Max 订阅 |
| 2 | **调度**：**Claude Code Routines**（云端定时 agent，零本机依赖，复用 Max 订阅）。**不用** macOS launchd / crontab |
| 3 | **老目录**：`bangkok-news/` 保留作为只读备份，本次迁移不写它 |
| 4 | **模型分工**：**Haiku 是默认**，仅 publish 选题用 Sonnet。Routine 外层 session 也用 Haiku。详见顶部"成本铁律" |
| 5 | **Git 凭证 & 仓库**：沿用 `gh` 已登录的 `JiuTing6` 账号（has `repo` scope）；**新建 repo `JiuTing6/thailand10`**，与老 `bangkok-news` 完全分离 |
| 6 | **开发/调度分离**：本机 = 开发环境（改代码、调 prompt、改样式、手动测试）；GitHub repo = 唯一真相源；云端 Routine = 定时工人（按时 pull → 跑 runner → push）。HTML 样式改动一律本机改，push 后下次 routine 自动用新模板 |

---

## 架构对比

| 环节 | 旧（OpenClaw） | 新（本机开发 + 云上 Routine 调度） |
|------|---------------|----------------------|
| 调度 | OpenClaw cron agent (`c9fbffa7`, `a3aa4070`) | **Claude Code Routines（云端）** |
| 执行环境 | OpenClaw runtime | 本机开发用 macOS；定时跑用云端 Linux session |
| Filter | OpenRouter HTTP → `llama-3.3-70b` | `claude -p` → `claude-haiku-4-5` |
| Dedup | 同上 | 同上 |
| Translate | 同上 | 同上 |
| Publish 选题 | OpenClaw cron agent + Sonnet | `claude -p` → `claude-sonnet-4-6` |
| HTML 拼装 | `build_issue.py`（无模型） | 不变 |
| Git push | 同账号 | 同账号 |

API key 依赖（`~/.openclaw/openclaw.json` 里的 `OPENROUTER_API_KEY`）**全部移除**。

---

## 实施步骤

### Step 0：前置准备（动手前手动确认）
- [ ] `npm i -g @anthropic-ai/claude-code` 安装成功，`claude --version` 可用
- [ ] `claude -p "say hi" --model claude-haiku-4-5 --output-format json` 跑通，确认走 Max 订阅
- [ ] Claude.app 保持登录态
- [ ] 确认 `/Users/Ade/Projects/Thailand10/` 可写
- [ ] **从 OpenClaw 备份关键资产**（OpenClaw 后续删除前的最后机会）：
  - `~/.openclaw/workspace/bangkok-news/prompts/orchestrator.md`（每日 ingest 编排说明，Step 1a 复制后 runner 改造时要逐行核对）
  - publish 选题 prompt——若 `prompts/` 下无独立文件，需从老 cron agent (`a3aa4070`) 配置里 dump 文本存成 `prompts/publish_select.md`
  - **预扫描所有 prompt 里 `/Users/Ade/.openclaw/workspace/bangkok-news/` 硬编码路径**，记下出现位置，搬过来后必须改成相对路径
- [ ] **新申请 Telegram bot**（项目通用通知通道，非 Thailand10 专属）：
  - 详细步骤见 [`docs/telegram-notify.md`](docs/telegram-notify.md)
  - 拿到 token + chat_id 后写入 `~/.config/thailand10/env`（权限 600）
  - 老 OpenClaw 时代的 Telegram bot 不复用，迁移完成稳定后可在 BotFather 里删掉

### Step 1：搬文件 + 建新仓库 + 改路径硬编码

**1a 复制核心文件**（**不**复制 `.git/`，新 repo 从零起步）：
从 `bangkok-news/` 复制到 `Thailand10/`：
- `data/news_pool.json`（核心资产，~962 条历史新闻）
- `data/last_ingest.txt`
- `data/issues/`（最近几期中间产物，可选）
- `data/published_history_thai10.json`
- `scripts/`（除 `__pycache__/`）
- `prompts/`（**特别确认 `orchestrator.md` 在内**；如有 publish 选题 prompt 也一并搬）
- `docs/`（注意：本次迁移已新增 `docs/telegram-notify.md`，复制时勿覆盖）
- `thailand10/`（历史期号 HTML，否则 newsroom 翻不到旧期）
- `newsroom.html`、`index.html`、`assets/`、`moments/`
- `ingest_runner.py`、`PROJECT.md`

**复制后立刻**：人工读一遍 `prompts/orchestrator.md`（以及 publish prompt），把所有 `/Users/Ade/.openclaw/workspace/bangkok-news/` 改成相对路径或 `Path(__file__).parent` 风格。Step 1b 的 grep 会再兜一次底，但 prompt 文件 grep 也能扫到，最好同步处理。

**不复制**：`.git/`、`_archive/`、`archive/`、`run_*.sh`（老脚本，新流程用 runner 代替）、`.DS_Store`、各种 `*.bak.*`

**1b 改硬编码路径**：
- `ingest_runner.py:9` `os.chdir('/Users/Ade/.openclaw/workspace/bangkok-news')` → 改成相对路径或 `Path(__file__).parent`
- 全仓 `grep -rn "openclaw/workspace/bangkok-news"` 找其他硬编码并替换
- 全仓 `grep -rn "bangkok-news"` 检查有无对老 repo 名的引用（README、docs 里可能有）

**1c 建新 GitHub repo + git init**：
```bash
cd /Users/Ade/Projects/Thailand10
git init -b main
gh repo create JiuTing6/thailand10 --public --source=. --remote=origin --description "Thailand10 泰兰德10:00 weekly Chinese news brief"
# 还不要 push，等 1d 加好 .gitignore 再首次 commit
```

**1d 加 `.gitignore`**：
```
__pycache__/
*.pyc
.DS_Store
*.bak
*.bak.*
.env
.env.*
data/news_pool.bak.json
logs/
data/issues/*-raw.json
data/issues/*-flat.json
data/issues/*-pool-excerpt.json
data/issues/*-filtered.json
data/issues/*-deduped.json
# 注意：translated.json 和 news_pool.json 必须 commit
```
（`.env*` 是为防意外 commit 任何含 token 的本地配置；实际 secrets 文件在 `~/.config/thailand10/env`，不在 repo 里）
（中间产物 raw/flat/filtered/deduped 不进 repo，体积大且无价值；只有 `news_pool.json` 是真相源）

**1e 首次 commit & push**：
```bash
git add .
git commit -m "init: migrate from bangkok-news, fresh start"
git push -u origin main
```

**1f 启用 GitHub Pages**：
```bash
gh api -X POST repos/JiuTing6/thailand10/pages -f source[branch]=main -f source[path]=/
```
然后访问 `https://jiuting6.github.io/thailand10/newsroom.html` 验证能打开。**首次启用 Pages 后 URL 通常需 5–10 分钟才生效**，404 不要立即判定失败，等一会儿再试。

**验证**：`git remote -v` 指向新 repo；GitHub web 上能看到所有核心文件；Pages URL 能渲染 newsroom。

### Step 1.5：提前落地 `requirements.txt` 与依赖体检
原计划 Step 6 才新增 `requirements.txt`，但 Step 4 手动跑 ingest 时已经需要依赖到位，所以提前。

- [ ] 在 repo 根新建 `requirements.txt`，至少包含 `requests`；通读 `scripts/*.py` 看 import，把所有非标准库依赖（如 `feedparser`、`beautifulsoup4` 等）补上
- [ ] `du -sh data/` 看一眼大小；如果接近 100MB 需重新评估是否要把历史 issues 全部纳入 repo
- [ ] 文件名大小写注意：本仓库用 `PLAN.md`（大写）。云端 routine 在 Linux 上跑，文件名大小写敏感，所有 runner / prompt 内的引用统一用 `PLAN.md`，别混 `plan.md`

### Step 2：写 `scripts/claude_call.py` helper
封装本机 `claude` CLI 调用，提供统一接口：

```python
def call_claude(prompt: str, model: str = "claude-haiku-4-5",
                expect_json: bool = True, timeout: int = 120) -> dict | str:
    """调本机 claude CLI（用 Max 订阅），返回响应。"""
```

实现要点：
- `subprocess.run(["claude", "-p", prompt, "--model", model, "--output-format", "json"], ...)`
- 捕获非零退出 / 超时 / 配额耗尽，抛出明确错误
- `expect_json=True` 时 parse JSON 并返回 `result` 字段；否则返回原文
- 加个 retry（指数退避，3 次），对付偶发网络/限流

### Step 3：改造三个 LLM 脚本
共同改动模式：
- 删 `OPENROUTER_URL`、`OPENROUTER_API_KEY` 读取、`requests.post` 调用
- **`MODEL = "claude-haiku-4-5"`（铁律：这三个脚本永远 Haiku）**
- 调 `claude_call.call_claude(prompt, model=MODEL)`
- prompt 主体**完全不动**（已经调好的 prompt 不破坏）

涉及文件：
- `scripts/filter.py`
- `scripts/dedup.py`
- `scripts/translate.py`

`claude_call.py` 的 `call_claude(prompt, model=...)` 不设默认值，**强制调用方显式传 model**，避免任何脚本"忘了写"就默认 Sonnet。

### Step 3.5：写 `scripts/notify.py`（Telegram 通知 helper）
完整代码与设计见 [`docs/telegram-notify.md`](docs/telegram-notify.md) 第二节。要点：
- 从 `TG_BOT_TOKEN` / `TG_CHAT_ID` 环境变量读凭据，缺失时静默跳过（**不抛异常，绝不能让通知挂导致主流程失败**）
- 暴露 `notify(text, project="Thailand10")` 函数，消息一律带 `[Thailand10]` 前缀
- `ingest_runner.py` / `publish_runner.py` 末尾用 try/except 包住主逻辑：成功发 ✅ + 摘要，失败发 ❌ + 异常类型，然后 re-raise

验收：
- [ ] 本机 `source ~/.config/thailand10/env && python3 scripts/notify.py "test ping"` 能收到消息

### Step 4：手动跑一次 ingest 验证
```bash
cd /Users/Ade/Projects/Thailand10
python3 ingest_runner.py 2>&1 | tee logs/ingest-manual-$(date +%Y%m%d).log
```
验收：
- [ ] `data/issues/<today>-{raw,flat,filtered,deduped,translated}.json` 全部生成
- [ ] `data/news_pool.json` 增加新条目
- [ ] `data/last_ingest.txt` 更新
- [ ] git commit + push 成功，GitHub 上能看到新 commit
- [ ] Telegram 收到 `[Thailand10] ✅ ingest done ...` 一条消息

### Step 5：复刻 publish 流程为 `publish_runner.py`
原来 publish 是 OpenClaw cron agent 编排的（agent 调 `7days_filter_pool.py` 预筛 → 自己用 Sonnet 选题 → 调 `build_issue.py`）。改为单脚本 `publish_runner.py`：

1. 跑 `scripts/7days_filter_pool.py` 生成 `data/7days_news_<date>.json`
2. 调 `claude_call.call_claude(选题prompt, model="claude-sonnet-4-6")` 输出 `selected_<date>.json`
   - **整个项目唯一允许使用 Sonnet 的地方**
   - 选题 prompt 从原 OpenClaw cron agent 的 prompt 里提取，存到 `prompts/publish_select.md`
3. 跑 `scripts/build_issue.py` 生成 newsroom.html 更新
4. git commit + push

验收（手动跑）：
- [ ] 周四生成新一期，newsroom.html 更新，GitHub Pages 能看到

### Step 6：配 Claude Code Routines（云端调度）

#### 前置：准备云端能跑的产物
- 在 repo 根新增 `requirements.txt`（已知依赖：`requests`，其余都是标准库）
- 确保 runner 脚本能在干净环境从头跑：`git clone → pip install -r requirements.txt → python3 ingest_runner.py`
- runner 脚本里如果有任何"本机绝对路径"假设，全部改成相对当前 repo 根

#### 关键架构问号（首次手动 trigger 时验证）
本机时 `filter.py` / `dedup.py` / `translate.py` 是 `subprocess` 调本机 `claude -p` CLI。云端 routine 本身就是一个 Claude session，里面 python 脚本要做 LLM 工作有两条路：

- **方案 A（首选）**：云端环境如果也带 `claude` CLI，脚本零修改直接跑——**与本机 100% 同构**。
- **方案 B（备选）**：若云端没 `claude` CLI，则给脚本加 `--llm-mode {cli,stdio}` 参数。云上跑 stdio 模式：脚本把 prompt 写到 stdout、读 stdin 的回复，由外层 routine session 配合处理。

**首次跑 routine 时第一件事**：`which claude && claude --version`。能跑 → 走 A；不能跑 → 退到 B（多一周左右工作量）。

#### 两个 Routine 设计

**Ingest routine** — 每天 08:30 BKK
prompt 模板大致：
```
You are an automation worker. Do not improvise.
1. git clone https://github.com/JiuTing6/thailand10.git /tmp/repo (use gh auth)
2. cd /tmp/repo && pip install -q -r requirements.txt
3. python3 ingest_runner.py
4. If exit code != 0, print last 100 log lines and stop
5. Done. The runner already commits & pushes.
```

**Publish routine** — 每周四 09:30 BKK
prompt 类似，跑 `python3 publish_runner.py`。

#### 云端 secrets（Git 凭证 + Telegram）
云端 routine 需要的 secrets：
1. **GitHub push 身份**——三种可能：
   - routine 内置 GitHub 集成（最干净）
   - 注入 `GH_TOKEN` env（用 `JiuTing6` 账号生成 PAT）
   - deploy key
   倾向 1 → 2。
2. **Telegram 通知**：注入 `TG_BOT_TOKEN` 和 `TG_CHAT_ID`，与 `GH_TOKEN` 同样机制处理
3. **Claude CLI 登录态**（**关键不确定项**）：本机 `claude -p` 走 Claude.app 的 Max 订阅登录态。云端 session 是否自动是同一个 Max 账号？还是匿名 / 独立计费？**首次创建 routine 时第一件要确认**。如果云端不是 Max 订阅而走计费 API，整个成本模型崩了，必须立即停下重新评估。

#### 创建方式
用 `/schedule` 这个 skill 创建 routine（明天动手时我直接调）。每个 routine 有独立 ID，可以 list / update / delete。

**创建时必须显式指定 routine 外层 session 用 Haiku**（参数名届时确认，可能是 `model: claude-haiku-4-5`）。外层只做 git+subprocess，不需要推理能力。

#### 日志与监控
- routine 跑完 transcript 在 web 端可看
- runner 脚本仍把摘要日志写到 `logs/`（commit 进 repo），失败时易于事后排查

### Step 7：监控与回退
- `logs/` 滚动日志，保留 30 天
- **失败感知**：runner 末尾的 `notify()` 会发 ✅/❌ 到 Telegram，是主要的失败感知渠道（详见 [`docs/telegram-notify.md`](docs/telegram-notify.md)）
- 双向交互（你给 bot 发命令触发动作）当前**不做**，保持单向通知；升级路径见 telegram-notify.md 第六节
- **回退路径**：保留老 `bangkok-news/` 不动，万一新管线出问题，仍可手动从老目录跑
  - ⚠️ 老目录依赖 `OPENROUTER_API_KEY`（在 `~/.openclaw/openclaw.json`）和 OpenClaw runtime；OpenClaw cron 已停，但**手动 export key + python 直接跑老脚本**这条路是否还能走，**Step 0 完成时务必验证一次**，否则"回退"只是纸面承诺

---

## 风险 & 待观察

| 风险 | 应对 |
|------|------|
| Claude Max 5 小时滚动限额 | Ingest 量小（一次几十条 LLM 调用），单次远低于上限；首跑观察 |
| `claude` headless 模式输出格式变化 | helper 集中封装，只改一处 |
| 云端 routine 环境无 `claude` CLI | 退到方案 B（脚本加 stdio 模式） |
| 云端 routine 环境缺其他依赖 | `requirements.txt` + `apt-get` 兜底 |
| GitHub push 凭证 | 优先用 routine 原生 GitHub 集成；备用 `GH_TOKEN` PAT |
| OpenClaw 旧 cron 仍在跑导致重复 push | ✅ 用户已确认 OpenClaw cron 已停 |
| 老 URL 上的内容停在 04-23 引发误会 | 老 repo 保留只读，URL 还能访问；新内容只看新 URL；自己留意分享时用新链接 |
| 新 repo Pages 没启用导致新 URL 404 | Step 1f 验证一次；之后每次 push 都自动重发布 |

---

## 不在本次范围

- 虚拟滚动 / newsroom 性能优化（PROJECT.md 路线图，等 1000+ 条再做）
- prompt 调优

---

## 文件清单（Step 1 复制后 Thailand10 应有结构）

```
Thailand10/
├── PLAN.md                     ← 本文件
├── PROJECT.md                  ← 从源复制，可能需小改
├── ingest_runner.py            ← 改路径
├── publish_runner.py           ← 新增（Step 5）
├── newsroom.html               ← 当前最新一期，后续覆盖
├── index.html
├── assets/
├── moments/
├── thailand10/                 ← 历史期号
├── data/
│   ├── news_pool.json          ← 主数据
│   ├── last_ingest.txt
│   ├── issues/                 ← 每日中间产物
│   └── 7days_news_*.json
├── scripts/
│   ├── claude_call.py          ← 新增（Step 2）
│   ├── fetch_rss.py
│   ├── filter.py               ← 改造
│   ├── dedup.py                ← 改造
│   ├── translate.py            ← 改造
│   ├── pool_merge.py
│   ├── 7days_filter_pool.py
│   ├── build_issue.py
│   ├── build_html.py
│   ├── generate_newsroom.py
│   └── notify.py               ← 新增（Step 3.5，Telegram 通知 helper）
├── prompts/
│   ├── orchestrator.md         ← 从老 OpenClaw 复制，需改硬编码路径
│   └── publish_select.md       ← 新增，从老 cron agent 提取
├── docs/
│   ├── ingest-pipeline-v2-design.md
│   └── telegram-notify.md      ← 新增，Telegram bot 设置/使用/升级指南
├── requirements.txt            ← Step 1.5 前置（提前到首次手动跑前）
├── logs/                       ← 新增
├── .gitignore                  ← 新增（Step 1d）
└── .git/                       ← `git init` 新建，remote = JiuTing6/thailand10
```

---

## 明天动手时的入口

1. 读这份 PLAN.md
2. 读 [`docs/telegram-notify.md`](docs/telegram-notify.md)（独立的 Telegram 配置参考，不放进主流程，避免噪音）
3. 从 Step 0 逐项过 checklist
4. 遇到决策点再问用户

---

## 待用户在 Step 0 之前提供的输入

- [ ] Telegram bot token（按 `docs/telegram-notify.md` 第一节申请）
- [ ] Telegram chat_id
- [ ] 确认 OpenClaw 老 cron agent (`a3aa4070`) 的 publish prompt 还能访问（用来 dump 出来）
