# Thailand10 技术工作流文档

> **版本：** v2.1  
> **最后更新：** 2026-03-20  
> **状态：** 生产运行中，架构稳定  
> **仅供内部参考**

---

## 目录

1. [整体架构](#1-整体架构)
2. [触发层：OpenClaw Cron](#2-触发层openclaw-cron)
3. [Ingest Pipeline（每日 08:30）](#3-ingest-pipeline每日-0830)
4. [Publish Pipeline（周一/四 09:30）](#4-publish-pipeline周一四-0930)
5. [数据层：JSON 文件](#5-数据层json-文件)
6. [抓取层：fetch_rss.py](#6-抓取层fetch_rsspy)
7. [渲染层：build_html.py](#7-渲染层build_htmlpy)
8. [发布层：GitHub Pages](#8-发布层github-pages)
9. [完整数据流图](#9-完整数据流图)
10. [文件结构](#10-文件结构)

---

## 1. 整体架构

Thailand10 是一个**零服务器、零运营成本**的自动化新闻简报系统。除 AI API 调用费用外，所有基础设施完全免费。

| 层级 | 技术 | 成本 |
|---|---|---|
| 调度触发 | OpenClaw Cron（Mac Mini 后台）× 3 个 job | 免费 |
| Ingest 主控 | haiku orchestrator | ~$0.0004/次 |
| 过滤 + 去重 | flash（Python 直调 OpenRouter API） | ~$0.005/次 |
| 翻译 + 标注 | flash（Python 直调 OpenRouter API，JSON mode） | ~$0.010/次 |
| 数据入库 | Python pool_merge.py | 免费 |
| Publish 主控 | haiku publish agent | ~$0.001/次 |
| 页面渲染 | Python build_html.py（无第三方依赖） | 免费 |
| 网站托管 | GitHub Pages（全球 CDN） | 免费 |

📊 **每日 Ingest 合计 ~$0.015，每月 ~$0.45**

**核心设计原则：** AI 只做编辑判断。格式化、存储、发布等确定性工作全部用 Python 完成，不依赖 AI，可靠、可复现、成本可控。

---

## 2. 触发层：OpenClaw Cron

OpenClaw Gateway 运行在 Mac Mini 后台，维护 3 个 Cron 任务：

| Cron ID | 任务名 | 时间 | Prompt 文件 | 模型 |
|---|---|---|---|---|
| `c9fbffa7` | 每日 Ingest | 每天 08:30 BKK | `prompts/orchestrator.md` | haiku |
| `de8116d8` | Thailand10 周一 | 每周一 09:30 BKK | `prompts/publish.md` | sonnet |
| `a3aa4070` | Thailand10 周四 | 每周四 09:30 BKK | `prompts/publish.md` | sonnet |

Ingest 每天跑，补充素材进 `data/news_pool.json`；Publish 每周一/四从 pool 选编并发布。**两个流程完全解耦。**

---

## 3. Ingest Pipeline（每日 08:30）

负责将原始新闻素材处理入库，由 haiku Orchestrator 主控（读取 `prompts/orchestrator.md`），分步完成：

```
Step 1  确定今日日期 + 上次入库时间（last_ingest.txt）
Step 2  fetch_rss.py → TODAY-raw.json
Step 3  Python 展平 → TODAY-flat.json
        取近10天 pool 前100条 → TODAY-pool-excerpt.json
Step 4  filter.py（flash API）→ TODAY-filtered.json
Step 5  dedup.py（flash API）→ TODAY-deduped.json
Step 6  translate.py（flash API）→ TODAY-translated.json
Step 7  pool_merge.py → news_pool.json（+ 备份 .bak）
Step 8  git push
Step 9  Telegram 通知（条数 / topic 分布）
```

### Layer 1 — 相关性过滤（filter.py）

- **模型：** flash（OpenRouter JSON mode），10条/批
- **新增字段：** `topic_tag`（9个 topic 之一）、`relevance_score`（0.0–1.0）
- **淘汰条件：** `relevance_score < 0.4`；纯全球新闻（无泰国具体行动/数据）；维基/广告页

### Layer 2 — 语义去重 + 控量（dedup.py）

- **模型：** flash（OpenRouter JSON mode），10条/批（含 pool 上下文）
- **去重逻辑：** URL 完全相同→skip；标题语义高度重合且无新信息→skip；同事件有新进展→keep；不确定→偏向 keep
- **Pool 比对范围：** 最近10天内最多100条（TODAY-pool-excerpt.json）
- **Topic 控量（按 relevance_score 降序截断）：**

| 级别 | Topics | 每日上限 |
|---|---|---|
| 一级 | #时政 #经济 #治安 #旅居 #社会 | 5条 |
| 二级 | #房产 #科技 #中泰 #健康 | 3条 |

### Layer 3 — 中文翻译（translate.py）

- **模型：** flash（OpenRouter JSON mode），5条/批
- **继承字段：** `topic_tag`、`relevance_score`（Layer 1 输出，不重新生成）
- **LLM 填充：** `title_cn`、`summary_cn`（100–150字）、`importance`（P1/P2/P3）、`section_hint`

---

## 4. Publish Pipeline（周一/四 09:30）

从 pool 中选题编写，由 haiku/sonnet Publish Agent 执行（读取 `prompts/publish.md`）：

```
Step 1  读取 news_pool.json（status=pending 条目）
Step 2  参考 data/editorial_feedback.md 编辑规则，选 15-25 条
Step 3  AI 撰写正文（扩写 summary_cn，加编辑视角）
Step 4  输出期数 JSON → thailand10/YYYY-MM-DD-NNN.json
Step 5  build_html.py → 生成期刊 HTML
Step 6  git push → GitHub Pages 自动部署
Step 7  Telegram 通知
```

**选题原则：** 重要性优先（P1→P2→P3）；topic 多样性；时效性（优先最近3天内容）；参考 editorial_feedback.md 编辑偏好。

---

## 5. 数据层：JSON 文件

所有持久化数据存在 `data/` 目录下，用 JSON 文件模拟轻量级数据库。

### data/news_pool.json — 核心素材库

Ingest 每天新增的翻译后条目，是 Publish 的唯一原料来源。每条完整字段：

```json
{
  "id": "c7614545a657",
  "source": "Bangkok Post",
  "source_id": "bangkokpost_top",
  "url": "https://...",
  "date": "2026-03-20T05:12:00+07:00",
  "desc_original": "...",
  "title_cn": "泰国总理...",
  "summary_cn": "...",
  "importance": "P1",
  "section_hint": "thailand",
  "topic_tag": "#时政",
  "relevance_score": 1.0,
  "time_sensitive": true,
  "expires_date": "2026-04-04",
  "status": "pending",
  "origin": "rss",
  "added_date": "2026-03-20"
}
```

**当前规模（2026-03-20）：** ~530条

### data/issues/ — 每日中间产物

| 文件 | 内容 |
|---|---|
| `TODAY-raw.json` | RSS 原始抓取 |
| `TODAY-flat.json` | 展平后统一数组 |
| `TODAY-filtered.json` | Layer 1 过滤结果 |
| `TODAY-deduped.json` | Layer 2 去重+控量结果 |
| `TODAY-translated.json` | Layer 3 翻译结果（入 pool 前） |
| `TODAY-pool-excerpt.json` | Pool 近10天摘录（去重比对用） |

### 其他数据文件

| 文件 | 说明 |
|---|---|
| `data/last_ingest.txt` | 上次入库日期，控制抓取时间窗口 |
| `data/published_history_thai10.json` | 已发布条目记录 |
| `data/editorial_feedback.md` | 人工编辑偏好，Publish Agent 参考 |
| `data/buffer.json` | 内容储备库（待启用） |

---

## 6. 抓取层：fetch_rss.py

纯 Python 标准库实现，无第三方依赖。抓取 9 个英文媒体 RSS 源：

| 来源 ID | 媒体 | 特点 |
|---|---|---|
| `bangkokpost_top` | Bangkok Post 头条 | 最权威英文媒体 |
| `bangkokpost_property` | Bangkok Post 房产 | 房产专版，精准 |
| `bangkokpost_thailand` | Bangkok Post Thailand | 泰国政治/社会 |
| `bangkokpost_business` | Bangkok Post Business | 商业/经济 |
| `bangkokpost_life` | Bangkok Post Life | 生活/文化 |
| `thaiger` | The Thaiger | 外籍读者视角，覆盖广 |
| `thaiger_bangkok` | The Thaiger Bangkok | 曼谷本地 |
| `khaosod` | Khaosod English | 泰文主流媒体英文版 |
| `pattaya_mail` | Pattaya Mail | 芭提雅专属 |

**已停用：** Brave Search（泛搜索噪音大、日期格式不标准，不适合新闻采编）

**脚本处理流程：**
1. HTTP GET 每个 RSS XML，过滤上次入库日期后的条目
2. 解析 `<item>`，用 `md5(title+url)` 生成12位哈希作为唯一 ID
3. 剥离 HTML 标签，提取纯文字摘要（最多600字）
4. 跨源去重（同一条被多个源收录只保留一条）
5. 按发布日期倒序排列，输出标准化 JSON

---

## 7. 渲染层：build_html.py

纯 Python 标准库，无第三方依赖。输入期数 JSON，输出完整 HTML 页面。

```bash
python3 scripts/build_html.py data/issues/2026-03-20.json
# 输出：
# → thailand10/2026-03-20-NNN.html（期刊正文页）
# → thailand10/index.html（归档列表，自动插入新条目）
```

**板块配置（5个，定义在脚本顶部 SECTIONS 列表）：**

| 板块 ID | 图标 | 显示名 | 配额 |
|---|---|---|---|
| `thailand` | 📡 | 政经动态 | 无上限，兜底板块 |
| `property` | 🏠 | 房地产 | 动态，可为0 |
| `bangkok` | 🛺 | 曼谷 | 动态，严格本地新闻 |
| `pattaya` | 🌅 | 芭提雅 | 动态，可为0 |
| `cn_thai` | 🚅 | 中泰 | 触发式，可为0 |

空板块自动跳过，不渲染板块标题。

所有样式存在独立的 `assets/style-thailand10.css`，修改样式无需重新生成历史页面。

---

## 8. 发布层：GitHub Pages

`thailand10/` 整个目录是一个 GitHub 仓库（[JiuTing6/thailand10](https://github.com/JiuTing6/thailand10)）。每次 `git push` 后，GitHub 自动重建静态站点，约1–2分钟后全球上线。

| URL | 内容 |
|---|---|
| `/` | 主页 |
| `/newsroom.html` | 新闻库实时浏览（动态加载 news_pool.json） |
| `/thailand10/index.html` | 期刊归档列表 |
| `/thailand10/YYYY-MM-DD-NNN.html` | 每期正文 |
| `/docs/tech-workflow.md` | 本技术文档 |

---

## 9. 完整数据流图

```
OpenClaw Gateway（Mac Mini 后台）
Cron ×3：Ingest 每天08:30 / Publish 周一/四 09:30
     │
     ├──────────────────────────────────────────────────────┐
     ▼                                                      ▼
── INGEST（每日 08:30）──                    ── PUBLISH（周一/四 09:30）──

haiku Orchestrator（prompts/orchestrator.md）  haiku/sonnet（prompts/publish.md）
     │                                                      │
fetch_rss.py（9个RSS源）                    读取 news_pool.json（pending条目）
     │                                        + data/editorial_feedback.md
TODAY-raw.json                                              │
     │                                       AI 选题（15-25条）
Python: flatten                                             │
TODAY-flat.json + TODAY-pool-excerpt.json    撰写正文 + 期数 JSON
     │                                                      │
filter.py（flash API）                       build_html.py
TODAY-filtered.json                                         │
     │                                       thailand10/YYYY-MM-DD-NNN.html
dedup.py（flash API）                        index.html 更新
TODAY-deduped.json                                          │
     │                                       git push → GitHub Pages
translate.py（flash API）                                   │
TODAY-translated.json                        Telegram 通知（发布成功）
     │
pool_merge.py
→ news_pool.json（+ 备份 news_pool.bak.json）
     │
git push
     │
Telegram 通知（条数 / topic 分布）
```

---

## 10. 文件结构

```
thailand10/
├── index.html                      # 主页
├── newsroom.html                   # 新闻库实时浏览
├── prompts/                        # ★ 生产 Prompt 文件
│   ├── orchestrator.md             # Ingest 总控
│   ├── publish.md                  # Publish 总控
│   ├── filter_agent.md             # Filter 规则参考
│   └── dedup_agent.md              # Dedup 规则参考
├── scripts/                        # Python 脚本
│   ├── fetch_rss.py                # RSS 抓取
│   ├── filter.py                   # Layer 1 过滤
│   ├── dedup.py                    # Layer 2 去重+控量
│   ├── translate.py                # Layer 3 翻译
│   ├── pool_merge.py               # Pool 合并入库
│   ├── build_html.py               # HTML 渲染
│   └── generate_newsroom.py        # Newsroom 生成
├── data/
│   ├── news_pool.json              # ★ 核心素材库
│   ├── last_ingest.txt             # 上次入库日期
│   ├── published_history_thai10.json
│   ├── editorial_feedback.md       # 编辑规则（人工维护）
│   ├── buffer.json                 # 内容储备库（待启用）
│   └── issues/                     # 每日中间产物
│       └── YYYY-MM-DD-{stage}.json
├── thailand10/                     # 已发布期刊
│   ├── index.html
│   └── YYYY-MM-DD-NNN.html
├── docs/                           # 文档
│   ├── tech-workflow.md            # ★ 本文档
│   ├── ingest-pipeline-v2.1-spec.md  # Ingest 详细规格
│   ├── ingest-pipeline-v2-design.md  # 设计文档
│   └── tech-workflow-v1.html       # 旧版 HTML 文档（存档）
├── assets/
│   └── style-thailand10.css        # 期刊样式
├── moments/                        # 素坤逸拾光（待开坑）
└── archive/                        # 历史文件归档
    ├── bak-prompts/                # Prompt 历史备份
    ├── data-backups/               # Pool bak 文件
    ├── one-time-scripts/           # 已用完的一次性脚本
    ├── v1-scripts/                 # v1 旧脚本
    └── experiment-README.md        # 实验阶段说明（存档）
```
