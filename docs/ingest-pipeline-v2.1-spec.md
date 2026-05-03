# Thailand10 Ingest Pipeline v2 — 定型规格文档

> **版本：** v2.1（tag-v2-refactor 上线后）  
> **定型日期：** 2026-03-20  
> **状态：** 生产运行中，架构稳定

---

## 一、系统概述

Thailand10（泰兰德10:00）是面向曼谷/芭提雅外籍华人的双周中文新闻简报，每周一、四 09:30 BKK 自动发布。

Ingest Pipeline 负责每日新闻采集与入库，为 Publish Pipeline 提供原料。两者解耦运行：

- **Ingest Cron（每日 08:30 BKK）** → 抓取、过滤、去重、翻译 → 写入 `news_pool.json`
- **Publish Cron（周一、四 09:30 BKK）** → 从 pool 选编 → 生成 HTML → 发布

本文档覆盖 **Ingest Pipeline v2** 的完整规格。

---

## 二、数据流总览

```
RSS 9个源
    ↓ fetch_rss.py
TODAY-raw.json（原始抓取）
    ↓ 展平
TODAY-flat.json（统一数组）
    ↓ filter.py [Layer 1 — Gemini Flash]
TODAY-filtered.json（过滤 + topic_tag + relevance_score）
    ↓ dedup.py [Layer 2 — Gemini Flash]
TODAY-deduped.json（去重 + 按 topic 控量）
    ↓ translate.py [Layer 3 — Gemini Flash]
TODAY-translated.json（中文字段补全）
    ↓ pool_merge.py
news_pool.json（主数据库）
    ↓ git push
GitHub Pages → newsroom.html（动态加载展示）
```

---

## 三、RSS 数据源

共 9 个 RSS 源，全部英文，覆盖泰国主流英文媒体：

| source_id | 媒体 | RSS URL |
|---|---|---|
| bangkokpost_top | Bangkok Post Top Stories | `.../rss/data/topstories.xml` |
| bangkokpost_property | Bangkok Post Property | `.../rss/data/property.xml` |
| bangkokpost_thailand | Bangkok Post Thailand | `.../rss/data/thailand.xml` |
| bangkokpost_business | Bangkok Post Business | `.../rss/data/business.xml` |
| bangkokpost_life | Bangkok Post Life | `.../rss/data/life.xml` |
| thaiger | The Thaiger | `thethaiger.com/feed` |
| thaiger_bangkok | The Thaiger Bangkok | `thethaiger.com/news/bangkok/feed` |
| khaosod | Khaosod English | `khaosodenglish.com/feed/` |
| pattaya_mail | Pattaya Mail | `pattayamail.com/feed` |

**已停用：** Brave Search（`fetch_brave.py`）—— 泛搜索噪音大、日期格式不标准，不适合新闻采编场景。

**抓取范围：** 上次入库日期（`last_ingest.txt`）至今，默认不超过4天。

---

## 四、处理管道详细规格

### Layer 1 — 相关性过滤（filter.py）

**模型：** Gemini Flash（via OpenRouter，JSON mode）  
**批量：** 10条/次  
**脚本：** `scripts/filter.py`

**输入字段：** `id, title, desc, url, date, source, origin`

**新增字段：**
- `topic_tag`：9个 topic 之一（见下节），不相关填 `null`
- `relevance_score`：0.0–1.0

**过滤规则：**
- `relevance_score < 0.4` → 直接丢弃（不进入下一层）
- 纯全球新闻（无泰国具体行动/数据）→ 丢弃
- Wikipedia、YouTube、学术论文、广告页 → 丢弃

**输出统计格式：** `FILTER_RESULT: input=N keep=M skip=K`

---

### Layer 2 — 语义去重 + 控量（dedup.py）

**模型：** Gemini Flash（via OpenRouter，JSON mode）  
**批量：** 10条/次（含 pool 上下文）  
**脚本：** `scripts/dedup.py`

**去重逻辑：**
1. URL 完全相同 → skip
2. 标题语义高度重合（同角度，无新增信息）→ skip
3. 同事件但有新进展/新角度 → keep
4. 不确定 → 偏向 keep（宁漏勿过滤）

**Pool 比对范围：** 最近10天内最多100条（`TODAY-pool-excerpt.json`）

**去重后 topic 控量（按 relevance_score 降序截断）：**

| 级别 | Topics | 每日上限 |
|---|---|---|
| 一级 | #时政 #经济 #治安 #旅居 #社会 | 5条 |
| 二级 | #房产 #科技 #中泰 #健康 | 3条 |

**输出统计格式：** `DEDUP_RESULT: input=N keep=M skip=K`

---

### Layer 3 — 中文翻译（translate.py）

**模型：** Gemini Flash（via OpenRouter，JSON mode）  
**批量：** 5条/次  
**脚本：** `scripts/translate.py`

**输入继承字段：** `topic_tag`、`relevance_score`（Layer 1 输出，不再重新生成）

**LLM 填充字段：**

| 字段 | 说明 |
|---|---|
| `desc_original` | 原文 `desc` 截断至500字符，原样保留不翻译 |
| `title_cn` | 中文标题，信达雅，专有名词首现附英文 |
| `summary_cn` | 基于 desc 提炼，100–150字，核心事实+泰国背景解读 |
| `importance` | P1（直接影响在泰外国人）/ P2（重大项目/数据）/ P3（常规资讯） |
| `section_hint` | `bangkok / pattaya / property / cn_thai / thailand` |

**注意：** 若 RSS 原始条目无英文 `title`（仅有 `desc`），LLM 根据 desc 直接生成 `title_cn`，质量通常优于直译。

**Fallback：** 若 LLM 未返回 `title_cn`，用原 `title` 字段兜底。

**输出统计格式：** `TRANSLATION_RESULT: total=N P1=X P2=Y P3=Z`

---

### Pool Merge（pool_merge.py）

**脚本：** `scripts/pool_merge.py`

- 去重检查（URL hash），避免二次入库
- 将新条目追加写入 `data/news_pool.json`
- 更新 `data/last_ingest.txt`（今日日期）
- 备份：每次运行前 `cp news_pool.json news_pool.bak.json`

---

## 五、Topic 分类体系（9个）

| Tag | 含义 |
|---|---|
| #时政 | 泰国政治/外交/地缘/政府决策 |
| #经济 | 宏观经济/金融/贸易/能源/BOI/投资 |
| #治安 | 犯罪/交通/灾害/骗局预警/污染 |
| #旅居 | 旅游/生活/美食/文化/签证移民/健康日常 |
| #社会 | 社会事件/奇闻/人情味/争议/普通社会新闻 |
| #房产 | 房地产/基建/开发商/买房政策/商业地产 |
| #科技 | AI/新能源/数据中心/智慧城市/科技产业 |
| #中泰 | 中泰双边关系/中国在泰投资/华人社区/中国游客 |
| #健康 | 医疗/食品安全/公共卫生/药品/流行病 |

**版本历史：**
- v2 重构（2026-03-19）前：10个 topic，含独立的 #旅游/#生活/#文化/#教育
- v2 重构后：上述4个合并为 #旅居；新增 #中泰 #健康

---

## 六、数据结构 — news_pool.json

每条条目结构（完整字段）：

```json
{
  "id": "c7614545a657",           // 8字符 hash（title+url）
  "source": "Bangkok Post",       // 显示名称
  "source_id": "bangkokpost_top", // RSS源标识
  "weight": 5,                    // 源权重（备用）
  "url": "https://...",           // 原文链接
  "date": "2026-03-20T05:12:00+07:00", // 发布时间（ISO 8601）
  "desc_original": "...",         // 原文摘要（≤500字符）
  "title_cn": "泰国总理...",       // 中文标题（LLM生成）
  "summary_cn": "...",            // 中文摘要（100-150字）
  "importance": "P1",             // P1/P2/P3
  "section_hint": "thailand",     // bangkok/pattaya/property/cn_thai/thailand
  "location_detail": "",          // 地点补充（可空）
  "city_tag": "#泰国",            // 城市标签
  "topic_tag": "#时政",           // 9个topic之一
  "relevance_score": 1.0,         // 相关度 0.0-1.0
  "tags": [],                     // 扩展标签（暂未使用）
  "time_sensitive": true,         // 是否时效性强
  "expires_date": "2026-04-04",   // 过期日期（time_sensitive条目）
  "event_id": "thailand_fuel_...", // 事件ID（同系列新闻聚合）
  "status": "pending",            // pending（待发布）/ published
  "origin": "rss",                // 数据来源（固定为rss）
  "added_date": "2026-03-20"      // 入库日期
}
```

**⚠️ 注意：** 部分历史条目缺少 `title` 字段（RSS 原始数据无英文标题），这是正常现象，前端应优先使用 `title_cn`。

**当前规模（2026-03-20）：** 531条

---

## 七、Newsroom.html — 前端展示

**文件：** `newsroom.html`（仓库根目录）  
**访问：** https://jiuting6.github.io/thailand10/newsroom.html

**数据加载：** 动态 fetch `data/news_pool.json`（不内嵌数据）

**核心功能：**
- 按 `date`（优先）或 `added_date` 倒序排列（最新在前）
- 按 topic_tag 筛选（9个 topic 按钮）
- 按关键词搜索（title_cn + summary_cn）
- 点击卡片展开详情 Modal（含原文链接）

**排序注意事项（已修复，2026-03-20）：**  
历史遗留的 Brave 来源条目存在相对时间日期（如 `"6 days ago"`），已全部转换为 ISO 格式。v2 架构下 RSS 来源均为标准 ISO 时间，不会再出现此问题。

---

## 八、Cron 调度

| Cron ID | 触发时间 | 任务 | 模型 |
|---|---|---|---|
| `c9fbffa7` | 每日 08:30 BKK | Ingest Pipeline（orchestrator.md） | haiku 总控 + flash 脚本 |
| `de8116d8` | 周一 09:30 BKK | Publish Pipeline（publish.md） | haiku 总控 |
| `a3aa4070` | 周四 09:30 BKK | Publish Pipeline（publish.md） | haiku 总控 |

---

## 九、Prompt 文件索引

| 文件 | 用途 |
|---|---|
| `prompts/orchestrator.md` | Ingest 总控（haiku 执行） |
| `prompts/filter_agent.md` | Layer 1 过滤规则（仅参考，实际由 filter.py 内嵌 prompt） |
| `prompts/dedup_agent.md` | Layer 2 去重规则（仅参考，实际由 dedup.py 内嵌 prompt） |
| `prompts/publish.md` | Publish 总控（haiku 执行） |

**注：** filter/dedup/translate 的实际 system prompt 内嵌于对应 Python 脚本中，agent prompt 文件为设计参考。

---

## 十、成本架构

```
haiku（总控 orchestrator）
  → flash（filter.py 直调 API）
  → flash（dedup.py 直调 API）
  → flash（translate.py 直调 API）
```

- **不使用 subagent**：线性流程，subagent 无并发收益，只增加 sessions_yield 风险
- **不使用 sessions_yield**：已知 OpenClaw issue #49572，callback 生命周期限制会导致翻译步骤被静默跳过
- **Python 直调 OpenRouter API**：完全绕开 sessions_yield，稳定可靠

---

## 十一、已知问题 & 注意事项

| 问题 | 状态 | 处理方式 |
|---|---|---|
| sessions_yield 在 cron lane 断链 | OpenClaw issue #49572，未修复 | Python 直调 API 绕开，不受影响 |
| Brave 来源日期格式问题 | 已修复（2026-03-20） | Brave 已停用，存量9条已修正为 ISO 格式 |
| `title` 字段缺失（仅有 `title_cn`） | 正常现象 | 部分 RSS 源无英文标题，LLM 从 desc 生成中文标题 |
| PS API 分页参数 | 无关 | （记录于 ps-auto-sync-oc 文档）|

---

## 十二、变更历史

| 日期 | 变更 |
|---|---|
| 2026-03-19 | tag-v2-refactor 上线：topic 9个化、filter 新增 relevance_score、dedup 新增 topic 控量、RSS 源扩至9个、停用 Brave |
| 2026-03-20 | 修复历史 Brave 条目相对日期格式；移除 publish.md Brave 兜底逻辑；本文档定型 |
