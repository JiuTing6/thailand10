# Ingest Pipeline v2 设计文档

**版本：** v2.1  
**更新：** 2026-03-11  
**状态：** 生产运行中（v2 已上线，v1 已归档）

---

## 背景

当前 Ingest（v1）是单一 Sonnet 4.6 session 从头跑到尾，存在以下问题：

- 成本偏高（~$0.29-0.47/次，月度 ~$9-12）
- 曾出现连续 timeout（2026-03-05 两次超时）
- 过滤/去重/翻译混在一个 session，出错难定位

---

## v2 实际架构：Orchestrator + 子Agent + Python 流水线

```
Cron（minimax）→ Orchestrator session（主控 LLM）
  ├── exec: fetch_rss.py + fetch_brave.py → raw.json        [Python]
  ├── exec: flatten + pool_excerpt（Python 内联）            [Python]
  ├── sessions_spawn(model=scanner) → Filter + Dedup Agent  [LLM-FD]
  ├── exec: python3 scripts/translate.py                    [Python→API]
  │    └── OpenRouter API (scanner, JSON mode, batch=5)
  └── exec: pool_merge.py → news_pool.json                  [Python]
```

**关键设计：Translation 不再由 sub-agent 完成，改为 Python 脚本直调 OpenRouter API（JSON mode），Python 负责写文件，100% 可靠。**

数据传递：通过文件（各步骤读写 `data/issues/TODAY-*.json`）

---

## 各步骤执行方与成本

| # | 步骤 | 执行方 | 模型 | 估算 tokens（in/out） | 估算成本/次 |
|---|---|---|---|---|---|
| 0 | Orchestrator 调度 | LLM-O | minimax-m2.5 | 3k / 0.5k | ~$0.0004 |
| 1 | RSS + Brave 抓取 | Python | — | — | $0 |
| 2 | 展平 + Pool 摘录 | Python | — | — | $0 |
| 3 | Layer 1：过滤 + Layer 2：去重 | LLM-FD | scanner（Gemini Flash） | ~25k / 2k | ~$0.005 |
| 4 | Layer 3：翻译 + 标注 | Python→API | scanner（JSON mode，batch=5） | ~22k / 20k | ~$0.01 |
| 5 | pool_merge 入库收尾 | Python | — | — | $0 |

**每次运行合计：~$0.015 → 月度 ~$0.45（vs v1 ~$9-12，节省 95%+）**

> 注：Translation 从 Sonnet 4.6（$0.18/次）换成 scanner JSON mode（$0.01/次），是成本下降的主要原因。

---

## 关键设计决策与实验结论

### 1. Cron → 子Agent spawn 可行性 ✅ 已验证

- 实验：建立一次性 isolated cron job，内部调用 `sessions_spawn`
- 结果：成功，childSessionKey 正常返回
- 结论：isolated cron session（`cron:<jobId>`）与 sub-agent（`subagent:<uuid>`）是不同 session 类型，cron 不受"sub-agent 不能再 spawn"的限制

### 2. Scanner JSON 输出能力 ✅ 已验证

- **过滤测试**（10条假数据）：10/10 正确，纯 JSON，无杂质，7秒
- **过滤测试**（29条真实 3/3 数据）：判断质量优秀，15秒，tokens 13.2k/5.2k
- **去重测试**（25条候选 vs 116条 pool）：URL精确匹配100%正确，语义去重90%准确，10秒，tokens 32.2k/1.8k
- 注意：去重测试输出带了 ``` 代码框，需在 prompt 加强"纯JSON"指令

### 3. Scanner 工具调用（写文件）不可靠 ❌ 已确认 → 改用 Python

**2026-03-11 测试（4次）：**
- Run 1/2（原 prompt，45条）：scanner 输出 JSON 为文字，从未调用 write/exec 工具 → 文件不落盘
- Run 3（明确要求用 write 工具，20条）：同样不写文件
- Run 4（同上）：偶发成功写文件

**结论：** scanner 工具调用写文件成功率约 25%，不可依赖，与 prompt 措辞关系不大。

**解决方案：** `scripts/translate.py` — Python 直调 OpenRouter API（scanner，JSON mode），分批处理，Python 负责写文件，100% 可靠。测试：45条 9个 batch 全部成功，约 2 分钟完成。

### 3. Gemini 关于 maxSpawnDepth 的说法 ❌ 错误

- Gemini 声称有 `maxSpawnDepth` 配置和"嵌套子代理"功能，版本号 v2026.2.17
- 实际 OpenClaw 文档无此配置，为 LLM 编造内容
- 教训：LLM 输出的技术细节必须查官方文档验证

---

## Layer 2 去重简化方案（2026-03-09 确认）

### 原始设计痛点
- 需要比对整个 pool（可能 200+ 条）
- 需要区分"重复" vs "追踪进展"两种情况

### 简化决策
1. **10天窗口**：只比对最近10天内的 pool 条目，更早的不参与去重
   - 理由：10天前的事情若再出现，要么有新进展（值得入库），要么无所谓重复
   - 效果：参与比对的条目从 100+ 降至 ~50条

2. **100条上限**：pool 输入硬上限 100条（取最新的100条）
   - 与10天窗口结合，实际传入 token 大幅减少

3. **取消追踪标签（#追踪）**：
   - 6期实测观察：RSS 内容频率本身即反映话题重要性
   - 追踪标签在 Publish 阶段使用率低
   - 取消后：Layer 2 只做去重（keep/skip），Layer 3 Sonnet 不需处理追踪逻辑

### 去重简化后的规则
- **URL 完全相同** → 直接 skip
- **标题语义高度重合（同一事件，10天内）** → skip
- **同一事件有新角度/新进展** → keep（不打特殊标签，正常入库）
- **超过10天的同类话题** → keep（无论是否重复）

---

## 地理名称识别能力确认 ✅

Scanner 对泰国地名识别无需依赖"Thailand"字样：
- 已确认识别：Bangkok、Pattaya、Phuket、Koh Samui、Krabi、Mae Sai、Kamphaeng Phet、Chon Buri、Udon Thani、Rawai（普吉）、Nong Prue（芭提雅）等
- 依据：3/3 过滤测试，无"Thailand"字样的 Phuket / Kamphaeng Phet 条目均正确判断

---

## 当前状态（2026-03-11）

### ✅ 已完成
- v2 pipeline 完整上线，v1 脚本已归档至 `archive/v1-scripts/`
- `experiment/prompts/orchestrator.md`：主控 prompt，步骤1-9
- `experiment/prompts/filter_agent.md`：Layer 1 过滤
- `experiment/prompts/dedup_agent.md`：Layer 2 去重（10天窗口）
- `scripts/translate.py`：Layer 3 翻译，Python + OpenRouter JSON mode
- `experiment/scripts/pool_merge.py`：入库收尾
- `data/news_pool.bak.json`：每次 ingest 前自动备份
- 2026-03-09 第6期成功发布（v2 首期）

### 待验证
- [ ] 2026-03-12 08:30 Ingest（首次用新 translate.py）
- [ ] 2026-03-13 09:30 Publish（验收 → experiment 转正）

### experiment 转正条件（2026-03-13 后）
ingest 连续正常 + 周四发布成功后：
1. `experiment/prompts/` 路径固化（或移入正式目录）
2. 旧 v1 archive 保留不删
3. MEMORY.md 路径同步更新

---

## 参考

- OpenClaw 文档：`sessions_spawn` 限制说明 → `/opt/homebrew/lib/node_modules/openclaw/docs/concepts/session-tool.md`
- OpenClaw 文档：Cron isolated session → `/opt/homebrew/lib/node_modules/openclaw/docs/automation/cron-jobs.md`
- 实验日志：`memory/2026-03-09.md`
