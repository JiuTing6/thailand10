# Thailand10（泰兰德10:00）

## 概要
每周中文新闻简报，面向曼谷/芭提雅外籍华人。

- **网址：** https://jiuting6.github.io/thailand10/
- **仓库：** `/Users/Ade/Projects/Thailand10/`（public）
- **Git：** https://github.com/JiuTing6/thailand10
- **发布节奏：** 每周四 09:30 BKK，全自动

## 架构（v2 两阶段）
- **Ingest：** 每天 08:30，RSS → Filter → Dedup → Translation → `data/news_pool.json`
- **Publish：** 周四 09:30，`7days_filter_pool.py` 预筛 → Sonnet 选题 → Python 拼装 → HTML 发布

## 模型分工（重要，勿忘）
| 步骤 | 脚本 | 模型 | 备注 |
|------|------|------|------|
| Orchestrator | cron agent | Haiku（default） | 调度、spawn subagent |
| RSS 抓取 | fetch_rss.py | 无模型 | 纯代码，requests库 |
| 过滤/打标签 | filter.py | Flash（hardcode） | `google/gemini-3-flash-preview` |
| 语义去重 | dedup.py | Flash（hardcode） | `google/gemini-3-flash-preview` |
| 翻译 | translate.py | Flash（hardcode） | `google/gemini-3-flash-preview` |
| Publish 选题 | cron agent prompt | Haiku（default） | 走 agent，非直调 |
| HTML 拼装 | build_issue.py | 无模型 | 纯 Python |

> Flash 模型名写死在各脚本顶部 `MODEL =` 常量，改模型直接改该常量。

## Cron
- `c9fbffa7` — 每日 Ingest 08:30
- `a3aa4070` — 周四 Publish 09:30

## 已知问题
- ⚠️ **sessions_yield 断链 Bug（OpenClaw issue #49572）：** 已用 Python 直调 API 绕开，不受影响。每次 OC 更新后关注修复进展。

## 性能优化路线图
- **当前状态：** 962 条新闻，全量渲染，可控但接近临界
- **临界点：** 1000+ 条时必须优化
- **优化方案（按优先级）：**
  1. **虚拟滚动** — Intersection Observer，只渲染视口内 + 前后 5 条，性能提升 10~50 倍，30 分钟集成
  2. **分页/无限滚动** — 每页 50 条
  3. **全文检索索引** — Lunr.js / MiniSearch
- **当下策略：** 暂不动，每月检查数据增长，1000+ 条立即启动虚拟滚动

## 详细设计
`thailand10/docs/ingest-pipeline-v2-design.md`

## 大事记
- 2026-02-26 — 第1期手动发布上线
- 2026-02-26 — Cron 自动发布启动
- 2026-03-xx — v2 两阶段架构重构完成
- 2026-04-24 — 增加 city_tag `#苏梅岛` 及 section_hint `samui`（translate.py prompt 更新）

## 下一步
- 关注 sessions_yield bug 修复进展
- 监控新闻条数，接近 1000 条启动虚拟滚动
