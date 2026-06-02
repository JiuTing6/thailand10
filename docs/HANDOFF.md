# 交接：2026-06-01 接手指南

> 写于 2026-05-31，更新于 2026-06-01（用户指定起点）。
> 读完这份 + 跑下面的验证命令，就能无缝接上。完事后可删本文件或归档。

**进度（2026-06-02 更新）**：
- ✅ **§B dedup 改造已完成上线**（main + push）：两阶段去重（当天互比聚类 + 确定性源优先级 tie-break；vs-pool 窗口帽 100→200 + 防错杀 prompt）。06-02 回放验证通过，06-03 09:30 起生效。
- ⏳ 剩余：§A translate 并行化（耗时仍 ~18min < 20min 线，不急）、§C Hostinger 迁移（待用户拍板）。

## 一句话现状

昨天（5/31）给 Thailand10 ingest 做了一批升级，**代码已全部上线 main + GitHub Pages**，但要等 **06-01 09:30 launchd 自动跑第一次**才看到实际效果。三件后续 todo 都卡在"先看这次真实跑批结果再定"。

## 昨天上线了什么（已 commit + push，无需再动）

1. **Telegram 通知**：ingest 成功/失败各发一条（`scripts/notify.py` + `ingest_runner.py` 顶层 try/except）。成功含耗时。
2. **Pool/归档双视图**：`news_pool.json`=滚动30天；`data/archive/YYYY-MM.json`=按月物化；newsroom 顶部"时段"tab。
3. **新增 RSS 源**：
   - Thairath 泰文 4 feed（news/business/money/scoop，`lang=th`）
   - Bangkok Post 扩到 3 feed（topstories + thailand + business），跳过 news.xml（国际/体育 wire feed）
   - 共 8 feed，实测原始抓取 ~95 条/天
4. **配图**：所有源提取图片 URL（Thairath enclosure / 其余正文 img / **BKK 抓原文页 og:image**），newsroom 卡片+弹窗显示，hotlink 不下载。实测覆盖率 100%。
5. **正文加长** 500→1200 字。
6. **降治安噪音**：`filter.py` 给 `#治安` 单独阈值 0.7（其余 0.4）+ prompt 引导琐碎犯罪低分。

## 明早第一件事：验证 09:30 这次 ingest

```bash
cd /Users/Ade/Projects/Thailand10
# 1. 看最新日志：耗时 + 是否成功完成
ls -t logs/ingest-*.log | head -1 | xargs tail -30
#   关注：结尾 "✅ Pipeline completed successfully!" + 总耗时（launchd start→end）

# 2. 今天进库情况（Thairath 是否进来 / 各源占比 / 图片覆盖 / 治安占比）
python3 - <<'PY'
import json
from collections import Counter
pool=json.load(open('data/news_pool.json'))
today=[i for i in pool if i.get('added_date')=='2026-06-01']
print("今日新增:", len(today))
print("各源:", dict(Counter(i.get('source') for i in today)))
print("有图:", sum(1 for i in today if i.get('image')), "/", len(today))
print("治安占比:", sum(1 for i in today if i.get('topic_tag')=='#治安'), "/", len(today))
print("含 Thairath:", sum(1 for i in today if i.get('source')=='Thairath'))
PY

# 3. 跨月验证（06-01 是首次跨月！）
cat data/archive/index.json    # 应出现 "2026-06"
ls data/archive/              # 应新增 2026-06.json
#   newsroom 时段 bar 应自动多出"六月"
```

也可以直接看 Telegram：那条 `✅ ingest done 2026-06-01: +N 条，pool 共 M，耗时 Xm Ys` 的**耗时**是关键数字。

## 三条 pending todo（都在 ~/TASKS.md，[Thailand10] 前缀）

按优先级 / 触发条件：

### A. translate 批次并行化（看耗时定）
- **触发**：若上面耗时 **> 20 分钟** → 该做了
- 方案：`scripts/translate.py` 串行 for → `ThreadPoolExecutor(max_workers=4)`。底层并发 spawn `claude -p`，非 multi-agent。预期翻译步 ~3.3×、整体 ~2.2×（12.5→~5.5min）。注意 max_workers 先 4、去掉 sleep(1)、逐批收结果。

### B. dedup 去重改造包（拿今天撞车样本验证再改）
源多了同事件多源报道激增。今天跑的是**未改版 dedup**，会放一些当天跨源重复进 pool——**正好当取证样本**。先查有几组撞车：
```bash
# 粗看今天有没有明显同事件多源重复（人工扫标题）
python3 -c "import json; [print(i['source'],'|',i.get('title_cn','')) for i in json.load(open('data/news_pool.json')) if i.get('added_date')=='2026-06-01']" | sort -t'|' -k2
```
四件事（详见 ~/TASKS.md 该条 + 5/31 对话）：
1. **防错杀**：prompt 强化"多日反复报道=重要且在发展"，只 collapse 同角度零新信息
2. **当天候选互比**：现在只比候选 vs pool 且按10条切批，当天同事件双双漏过；候选全在 `data/issues/{today}-filtered.json`，加一轮内部互比
3. **pool 参照窗口**：`ingest_runner.py` Step 5 的 `recent[:100]` 硬帽，量涨后实际窗口从10天缩到~3天；放大到 300-400 或去帽
4. **源优先级 tie-break**（确定性 Python，LLM 只聚类）：默认 泰国头条>Thaiger>Bangkok Post>Thairath>Pattaya Mail；主题翻转 #中泰→头条、#治安(芭提雅)→Pattaya Mail、#旅居→Thaiger、#经济/#时政→Bangkok Post、#社会→Thairath

### C. newsroom 迁出 GitHub Pages 到 Hostinger（待用户拍板）
- 卡在三个决策：Hostinger 套餐是否支持 SSH / 子域 vs 路径 / 要不要 Basic Auth
- 方案：Mac mini ingest 完跑 `scripts/deploy.sh` rsync 到 Hostinger，GitHub 留作代码+归档备份

## 工作环境备注

- 真相源文档：`docs/ingest-architecture.md`（架构）、`docs/telegram-notify.md`（通知）
- 生产 Python：`/usr/local/bin/python3`（**不是**系统 `python3`，后者 LibreSSL 会让 Thaiger SSL 失败）
- 本轮所有改动在 git worktree `claude/eloquent-maxwell-601f87` 分支上做、rebase 后推 main；主 repo `/Users/Ade/Projects/Thailand10` 已 pull 同步
- ingest 跑在主 repo（launchd `com.thailand10.daily-ingest`，09:30），**不是 worktree**
