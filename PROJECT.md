# Thailand10（泰兰德10:00）

每天自动抓取的泰国本地中文新闻看板，面向在泰华人/外籍人士。

## 关键信息

- **网站：** https://jiuting6.github.io/thailand10/newsroom.html
- **本地仓库：** `/Users/Ade/Projects/Thailand10/`
- **GitHub：** https://github.com/JiuTing6/thailand10（public）
- **更新节奏：** 每天一次 ingest（早 08:30 BKK，由 Claude Code Routine 调度，待配置）
- **发布形式：** 单页 newsroom，浏览器实时 fetch `news_pool.json` 渲染。一次抓取，永远显示最新

## 架构

```
RSS（9 源）
  ↓ fetch_rss.py（纯代码，无模型）
raw → flat
  ↓ filter.py（Haiku：泰国相关性 + topic 分类）
filtered
  ↓ dedup.py（Haiku：与 pool 最近 10 天去重）
deduped
  ↓ translate.py（Haiku：title_cn / summary_cn 等中文字段）
translated
  ↓ pool_merge.py（纯代码：合并、过期归档）
data/news_pool.json
  ↓ git commit + push
GitHub → Pages → 用户浏览器 fetch news_pool.json → newsroom.html 渲染
```

**入口脚本：** `ingest_runner.py`（顺序跑完上述全部步骤，最后 git push）

## 模型分工

**整个项目只用一个模型：Haiku（`claude-haiku-4-5`）**。

| 步骤 | 脚本 | 模型 |
|---|---|---|
| RSS 抓取 | `scripts/fetch_rss.py` | 无 |
| 过滤 + topic 分类 | `scripts/filter.py` | Haiku |
| 语义去重 | `scripts/dedup.py` | Haiku |
| 翻译（中文字段） | `scripts/translate.py` | Haiku |
| Pool 合并 | `scripts/pool_merge.py` | 无 |
| Newsroom 渲染 | `newsroom.html`（浏览器端） | 无 |

调用方式：所有 LLM 调用走 `scripts/claude_call.py`，subprocess 调本机 `claude -p`，复用 Claude.app Max 订阅 token，**API 账单零产生**。

## Tag 系统（当前版本）

新闻有两类 tag，每条新闻**至少一个 city_tag + 一个 topic_tag**。

### City Tags（已知 6 个 + 兜底）

定义点：
- `scripts/translate.py` SYSTEM_PROMPT 的 `### city_tag` 段
- `newsroom.html` 顶部 `const KNOWN_CITIES`

| Tag | 含义 |
|---|---|
| `#曼谷` | 明确发生在曼谷市内 |
| `#芭提雅` | 明确属于芭提雅地区 |
| `#普吉岛` | 明确属于普吉岛 |
| `#清迈` | 明确属于清迈 |
| `#苏梅岛` | 明确属于苏梅岛 |
| `#泰国` | 全国性新闻 / 无法确定具体城市 |

其他城市（华欣、清莱、孔敬、巴真等）→ 模型按 `#<具体城市名>` 输出，newsroom 归入 **#更多地区** 显示。

### Topic Tags（9 个，固定）

定义点：
- `scripts/filter.py` `VALID_TOPICS` 集合 + SYSTEM_PROMPT 的 9 topic 定义
- `newsroom.html` 顶部 `const TOPIC_TAGS`

| Tag | 含义 |
|---|---|
| `#时政` | 泰国政治 / 外交 / 政府决策 |
| `#经济` | 宏观经济 / 金融 / 贸易 / BOI / 投资 |
| `#治安` | 犯罪 / 交通事故 / 灾害 / 骗局预警 / 污染 |
| `#旅居` | 旅游 / 生活 / 美食 / 文化 / 教育 / 签证 / 健康日常 |
| `#社会` | 社会事件 / 奇闻 / 人情味 / 一般社会新闻 |
| `#房产` | 房地产 / 基建 / 开发商 / 买房政策 |
| `#科技` | AI / 新能源 / 数据中心 / 智慧城市 |
| `#中泰` | 中泰双边 / 中国在泰投资 / 华人社区 / 中国游客 |
| `#健康` | 医疗 / 食品安全 / 公共卫生 / 流行病 |

### 演变规则（重要）

Tag 系统会随新闻量与用户关注度演变。**任何增减都必须同步以下 4 处**，否则 newsroom 会出现"数量为 0"或"漏显示"的 bug：

1. **`scripts/filter.py`** — `VALID_TOPICS` 集合 + SYSTEM_PROMPT 的 topic 定义和示例
2. **`scripts/translate.py`** — SYSTEM_PROMPT 的 `### city_tag` 段（city 类）
3. **`newsroom.html`** — `KNOWN_CITIES` / `TOPIC_TAGS` 数组
4. **本文（PROJECT.md）** — 上面两个表

新增 city/topic 的标准操作：
- 新增 topic → 4 处全改 → 跑一次 ingest 看新 tag 是否被分配 → 历史 pool 不回补（向前生效）
- 新增 city → 上面 1, 2, 3 改 → 不需要 filter 改（city_tag 由 translate 负责）
- 删除 / 改名 → 历史 pool 里旧 tag 仍然存在；要么 newsroom 仍展示老 tag，要么写一次性脚本 migrate

## 数据文件

```
data/
├── news_pool.json              ← 主数据，浏览器 fetch 这个
├── last_ingest.txt             ← 上次 ingest 日期（fetch_rss 起始点）
├── published_history_thai10.json  ← 历史发布记录（已停刊，保留参考）
├── selected_*.json             ← 历史每周选出的 10 条（已停刊，保留参考）
└── issues/
    ├── YYYY-MM-DD-raw.json        ← RSS 原始（gitignore）
    ├── YYYY-MM-DD-flat.json       ← 展平（gitignore）
    ├── YYYY-MM-DD-filtered.json   ← 过滤后（gitignore）
    ├── YYYY-MM-DD-deduped.json    ← 去重后（gitignore）
    └── YYYY-MM-DD-translated.json ← 翻译后（commit）
```

**只有 `news_pool.json` 和 `*-translated.json` 进 git**。中间产物 `.gitignore` 排除。

## 文件清单

```
Thailand10/
├── PROJECT.md                  ← 本文件（项目说明 + tag 系统记录）
├── PLAN.md                     ← 迁移计划（OpenClaw → Claude Code）
├── README 类                   ← 暂无
├── newsroom.html               ← 单页看板，浏览器 fetch news_pool.json
├── index.html                  ← 简单 landing page（指向 newsroom）
├── ingest_runner.py            ← 每日 ingest 入口
├── requirements.txt            ← Python 依赖（仅 requests）
├── scripts/
│   ├── claude_call.py          ← 唯一的 LLM 调用入口（claude -p subprocess）
│   ├── fetch_rss.py            ← 9 个 RSS 源抓取
│   ├── filter.py               ← Layer 1：过滤 + topic 分类（Haiku）
│   ├── dedup.py                ← Layer 2：语义去重（Haiku）
│   ├── translate.py            ← Layer 3：中文字段（Haiku）
│   ├── pool_merge.py           ← 合并 + 过期归档（无模型）
│   ├── 7days_filter_pool.py    ← 老 publish 流程的预筛（已停刊，保留参考）
│   ├── build_issue.py          ← 老 publish 拼装 issue HTML（已停刊）
│   ├── build_html.py           ← 老 publish 渲染 issue（已停刊）
│   └── notify.py               ← TODO：Telegram 通知（待实现）
├── prompts/
│   ├── orchestrator.md         ← 老 OpenClaw 编排说明（已不再执行，保留参考）
│   ├── filter_agent.md         ← 老版 prompt 副本（参考）
│   ├── dedup_agent.md          ← 老版 prompt 副本（参考）
│   └── publish.md              ← 老 publish 选题 prompt（已停刊）
├── docs/
│   ├── ingest-pipeline-v2-design.md
│   ├── ingest-pipeline-v2.1-spec.md
│   ├── tech-workflow.md
│   ├── tech-workflow-v2.1.html
│   └── telegram-notify.md      ← Telegram bot 设置 / 升级路径
├── thailand10/                 ← 历史 issue HTML（已停刊，保留作为旧期归档）
├── assets/
├── moments/
├── data/                       ← 见上节
├── logs/                       ← runtime 日志（gitignore）
└── .gitignore
```

## 一些重要决策（避免重蹈覆辙）

1. **不要再用 `generate_newsroom.py`** — 它会把 newsroom.html 改回静态内嵌版本。本项目用 fetch 模式，newsroom.html 是模板，不应被脚本改写。已删除。
2. **整个 pipeline 只用 Haiku** — 老项目 publish 步用 Sonnet，但 publish 已停刊，整个项目无 Sonnet 调用。任何新增 LLM 调用默认用 Haiku，需要 Sonnet 必须明确说明并经评审。
3. **JSON 输出纪律** — Haiku 在 JSON 模式下偶尔会产生未转义引号。filter / translate prompt 都已要求"只输出 id + 新生成字段，不要回显输入"+"中文用「」不用 `"`"。改 prompt 时这两条不能丢。
4. **Newsroom 永远 fetch json** — 浏览器加载时拉 `data/news_pool.json` 渲染，不要回到内嵌方式（体积大、git diff 噪音、必须脚本重生）。
5. **API 调用一律 Max 订阅** — 通过 `claude -p` CLI 走本机登录态，零 API 账单。验证方法：`console.anthropic.com` 看不到任何 usage 记录。

## 历史与现状

| 阶段 | 时间 | 说明 |
|---|---|---|
| v1 | 2026-02 | 第 1 期手动发布；之后 OpenClaw cron 每日 ingest + 周四 publish |
| v2 | 2026-03 | 两阶段架构重构（filter/dedup/translate Python 化） |
| v2.1 | 2026-04 | RSS 源精简，新增苏梅岛 city_tag |
| **当前** | **2026-05** | 从 OpenClaw 迁移到本机 Claude Code，全 Haiku，停刊周刊，只保留每日 newsroom 看板 |

老 OpenClaw 仓库（`bangkok-news`）保留只读，迁移稳定后删除。

## 性能 / 数据规模

- 当前 pool: ~500 条
- 过期策略：`expires_date` 到期归档（time_sensitive=true 的 15 天，否则 30 天）
- 体量临界点：**1000+ 条**时考虑虚拟滚动 / 分页（暂未到）

## TODO

- Telegram 通知集成（详见 `docs/telegram-notify.md`）
- 云端 Claude Code Routine 调度（详见 `PLAN.md` Step 6）
- 失败感知 / 监控（runner 末尾发 ✅/❌ 到 Telegram）
