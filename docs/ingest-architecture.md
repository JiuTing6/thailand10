# Daily Ingest 架构

**最后更新**：2026-06-12

## 当前架构（本地 launchd）

Daily ingest 跑在 Ade 的 **Mac mini 本地**（24/7 不关机）。

- **触发器**：launchd（macOS 原生），plist 在 `~/Library/LaunchAgents/com.thailand10.daily-ingest.plist`，Label `com.thailand10.daily-ingest`
  - `StartCalendarInterval`：每天 09:30 本地时间
  - 关键属性：Mac 在 09:30 处于睡眠 → launchd **唤醒后自动补跑**（cron 不会，这是当初从 cron 迁过来的核心理由）
  - 装载/拆卸：`launchctl load -w <plist>` / `launchctl unload <plist>`
  - 查看状态：`launchctl print gui/$(id -u)/com.thailand10.daily-ingest`
- **wrapper 脚本**：[`scripts/thailand10-daily-ingest.sh`](../scripts/thailand10-daily-ingest.sh) — 设置 PATH/locale，cd 到 repo，跑 `ingest_runner.py`，输出 tee 到日志
- **日志位置**：
  - 主日志：`logs/ingest-YYYYMMDD-HHMMSS.log`（wrapper 内 tee 出，每次一份）
  - launchd 自带 stdout/stderr：`logs/launchd-stdout.log` / `logs/launchd-stderr.log`（追加，主要兜底用）
  - 三类日志都 gitignored
- **Pipeline 入口**：[`ingest_runner.py`](../ingest_runner.py) —— 抓 RSS → filter（L1 相关性）→ dedup（L2 两阶段去重）→ translate（L3 翻译标注，**并行**）→ pool merge → git commit/push
- **数据流起点 `LAST_DATE`**：抓取窗口 `[LAST_DATE, TODAY]`，`LAST_DATE` 读自 `data/last_ingest.txt`。**该文件只在 pool_merge（最后一步）成功后才写**，所以任何一步失败都不会推进它 → 下次跑自动从上次**成功**之日重抓（天然 catch-up）。
- **Push 凭证**：用 Mac 上日常 `~/.gitconfig` + macOS keychain，`git push` 直接走
- **自动提交清单**（Step 8.5 `git add`）：`news_pool.json` / `last_ingest.txt` / `data/archive/` / 当日 `*-translated.json`。**`data/archive/` 必须在内**（2026-06-12 补上），否则跨月物化的归档大文件会一直堆在工作区不提交。

### 性能基线（2026-06-12 更新）

源从 4→**8 feed**（Thairath 泰文 4 + Bangkok Post 3 + 头条/Thaiger/Pattaya），原始抓取 **~90 条/天**，filter 后 ~67、入库 ~60。完整 ingest **~17 分钟**（translate 并行化后）。耗时已不是 translate 一家独大，而是**三分天下**：

| Step | 耗时 | 说明 |
|---|---|---|
| Step 6a Filter | ~8.6 分钟 | 串行 ~14 批 × 5 |
| Step 6b Dedup | ~5.9 分钟 | 阶段1 全量聚类(1调用) + 阶段2 vs-pool ~7 批 |
| Step 7 Translate | **~2.9 分钟** | **并行**（ThreadPoolExecutor，4 workers）；并行化前是串行 ~10 分钟 |
| Fetch / Pool merge / Git push | <1 分钟 | |

**警戒线**：超过 20 分钟应排查。**每步在 `run_step` 里有独立 timeout**（translate=600s 等）——单步超时即 `TimeoutExpired` 整条挂掉。translate 串行版曾在 2026-06-11/12 撞 600s（见下「失败模式」）；并行化后远离红线，600s 反成健康兜底。
**下一个提速对象**：filter / dedup 仍串行，量再涨可用与 translate 相同的 `ThreadPoolExecutor` 模式并行（批次互相独立）。

## 去重架构：dedup 两阶段（2026-06-02 改造）

源从 4→8 后同事件多源报道激增，[`scripts/dedup.py`](../scripts/dedup.py) 改为两阶段：

1. **阶段1 — 当天候选互比**（新增）：LLM **单次全量**聚类当天所有候选里「同事件 + 同角度 + 零新信息」的组，Python 按确定性规则每组选 1 个幸存者。
   - 选谁：`SOURCE_PRIORITY[topic]` 源优先级表 → desc 长者 → 有图者 → id 字典序兜底（**LLM 只聚类，留谁由 Python 定，可复现零额外 token**）。
   - 默认优先级 `泰国头条 > Thaiger > Bangkok Post > Thairath > Pattaya Mail`（头条中文原生无翻译损耗）；按主题翻转（#治安/芭提雅→Pattaya Mail、#旅居→Thaiger、#经济/#时政→Bangkok Post、#社会→Thairath、#中泰→头条）。
   - **防错杀**：聚类标准从严，不同角度（如政策「启动」vs「使用指南」vs「首日效果」）判为不同条目全保留；只 collapse 真冗余。
2. **阶段2 — 幸存者 vs pool**（跨天去重）：按批比对 pool 摘录，prompt 强化「多日反复报道=发展信号，有新进展/数据/表态一律 keep」。

**pool 参照窗口**：Step 5 取 `data/news_pool.json` 近 10 天、按 `added_date` 降序 `recent[:200]`（旧版 `[:100]` 在量涨后把名义 10 天砍到 ~2 天，跟进报道比不中；只传 id/title/url，token 代价小）。

## Translate 并行化（2026-06-12）

[`scripts/translate.py`](../scripts/translate.py) 把串行 for 改成 `ThreadPoolExecutor(max_workers=4)`，批次互相独立天然可并行（底层并发 spawn `claude -p` 子进程，**非 multi-agent**）。

- **保序**：`batch_results[idx]` 按索引回填，`as_completed` 乱序完成不影响最终顺序。
- **单批失败降级**：`merge_batch` 对翻译失败/漏译的批**原文透传**（靠 `title_cn` 用 `title` 兜底），一批失败不再 `sys.exit` 拖垮整条 pipeline。
- `--workers` 可调（撞 Max 订阅速率限制就调小；`claude_call.py` 已有指数退避重试兜底）。

## 失败模式与补跑恢复（2026-06-10/11/12 三天事故教训）

三天连续失败，**两个完全独立的根因**：

- **06-10 — 瞬时网络故障**：09:30 那刻本机所有 socket 报 `[Errno 49] Can't assign requested address`，5 个 RSS 源全连不上 → `raw=0` → runner 按设计硬失败（`fetch_rss returned 0 items`）。**同一网络问题让 notify 也发不出**（连 Telegram API 都连不上）→ 当天**零通知**。孤立事件，次日自愈（前后 raw 量 77/90/**0**/94/92）。非代码 bug。
- **06-11/12 — translate 串行撞 600s**：量涨到 66/65 条（13-14 批），串行翻译 >10 分钟 → 撞 `run_step(timeout=600)` 被 kill → `TimeoutExpired` → 整条挂、`translated.json` 没产出。这两天网络正常，失败告警正常发到 Telegram。→ 直接催生 translate 并行化。

**补跑恢复要点**：
- **RSS 是滚动窗口**（只留最近一两天、几十条）。失败几天后，靠加大 `LAST_DATE` 窗口重抓**补不全**旧日新闻——源里已经滚走了。
- 但 pipeline 中间产物落盘：`data/issues/{date}-{flat,filtered,deduped,translated}.json`。**只要 `deduped.json` 在**（抓取/过滤/去重已完成、只差翻译入库），就能**精确**补跑：
  ```bash
  # 对每个待补日期（用真实日期保留 added_date）：
  python3 scripts/translate.py --input data/issues/{D}-deduped.json \
      --output data/issues/{D}-translated.json --date {D} --workers 4
  python3 scripts/pool_merge.py --new-items data/issues/{D}-translated.json \
      --pool data/news_pool.json --out data/news_pool.json --today {D}
      # 不传 --update-last-ingest：保留 last_ingest 让次日自动跑撒大网，
      # pool_merge 按 URL 去重 + dedup 幂等，重叠不会双份
  ```
  - `06-10` 因 `raw=0` 无任何中间产物 → 无法恢复。
  - 实例：2026-06-12 用此法补回 06-11(+66)/06-12(+57，8 条跨天 URL 重复自动跳过)。

## 为什么不走云端

2026-05-04 试过 Anthropic Routines（路径：UI 上 "Thailand10 daily ingest"，已删除）。失败原因：

**Anthropic 数据中心出站 IP 被全部 4 个泰国新闻 RSS 源 403 屏蔽**：
- Bangkok Post (`bangkokpost.com`)
- The Thaiger (`thethaiger.com`)
- 泰国头条新闻 (`thaiheadlines.com`)
- Pattaya Mail (`pattayamail.com`)

试过的对策：
- ❌ 换 User-Agent 为完整浏览器（`Mozilla/5.0 ... Chrome/126`）+ Accept headers — 仍然 4/4 全 403
- 结论：纯 ASN/IP 黑名单封锁（Cloudflare datacenter blocklist），跟 UA 无关

完整失败诊断和当时的 transcript 在 git log 5/4 那批 commit 里：
- `13b0f3e fix: surface fetch_rss diagnostics and fail loud on 0 items`
- `751dd49 fetch_rss: spoof browser User-Agent + Accept headers`

## 未来如果想重新云化

任何 datacenter（AWS / GCP / Anthropic / Vercel / Cloudflare Workers）大概率都共享同一份 Cloudflare ASN 黑名单 → **同样会被屏蔽**。可行方向只剩：

1. **Residential 性质的 VPS**（如 Ade 自有的 Hostinger）—— 中小型 hosting 通常不在主流黑名单。代价：自己运维一台服务器
2. **第三方 RSS 代理服务**（rss2json.com / rss.app 等）—— 让他们的 residential IP 替我们抓。代价：依赖第三方稳定性 + 限额
3. **混合架构**：Mac mini 抓 RSS → push raw JSON 到 GitHub → cloud routine 读 GitHub raw URL 跑后续 LLM 处理。代价：架构复杂度 +1，仍有本地依赖

短期内本地 cron 足够，不打算重新云化。

## Pool / 月度归档（2026-05-10 重构）

新闻数据有两份**平行的物化视图**：

- **`data/news_pool.json`** — 滚动 30 天窗口（按 `added_date`）。前端默认看到的就是这个。
- **`data/archive/YYYY-MM.json`** — 按自然月分桶，永不丢数据。每次 ingest 把当日新条目同时追加到当月归档。
- **`data/archive/index.json`** — 可用月份列表（降序），前端用它生成时段 tab。

两份视图自然重叠：4 月的条目今天既在 pool 里（在 30 天窗口内），也在 `archive/2026-04.json` 里。重叠是 feature 不是 bug——`最近30天` 是滚动窗口（跨月），`四月`是绝对自然月，两种视角都成立。

旧机制（每条新闻按 `time_sensitive` 分配 15/30 天 `expires_date`，超期直接从 pool 删除）已废弃。`translate.py` 的 prompt 不再生成这两个字段；旧条目里残留的 `expires_date` / `time_sensitive` 不再被读取，会被时间稀释掉。

实现位置：
- 写入：[`scripts/pool_merge.py`](../scripts/pool_merge.py) — 每次 ingest 同时写 pool（滚动 30 天）和当月归档；维护 `index.json`
- Prompt：[`scripts/translate.py`](../scripts/translate.py) — 输出字段 `id, title_cn, summary_cn, importance`（去掉 `time_sensitive`、`expires_date`）
- 一次性迁移：[`scripts/migrate_pool_to_archive.py`](../scripts/migrate_pool_to_archive.py) — 把现有 pool 按 `added_date[:7]` 拆成 `archive/YYYY-MM.json`，幂等可重跑
- 前端：[`newsroom.html`](../newsroom.html) — 顶部 "时段" tab `[最近30天 | 五月 | 四月 | ...]`，懒加载（点了才 fetch 对应文件，结果缓存内存里）

## 通知策略（2026-05-08 落地）

极简两条：每次 ingest 跑完发一条 Telegram，成功 ✅ + 失败 ❌ 二选一。

- **成功**：`[Thailand10] ✅ ingest done YYYY-MM-DD: +N 条，pool 共 M，耗时 Xm Ys`
- **失败**：`[Thailand10] ❌ ingest FAILED YYYY-MM-DD: <ExceptionType>: <短消息>`

实现位置：
- 通知 helper：[`scripts/notify.py`](../scripts/notify.py)（urllib，零依赖）。配置见 [`docs/telegram-notify.md`](telegram-notify.md)。
- Hook：[`ingest_runner.py`](../ingest_runner.py) 的 `if __name__ == "__main__"` 顶层 try/except。任何 step 抛 `RuntimeError` → except 发失败 ping → re-raise（保留非零退出码给 launchd）。`main()` 末尾发成功 ping。
- Secrets 注入：[`scripts/thailand10-daily-ingest.sh`](../scripts/thailand10-daily-ingest.sh) 在 `cd $REPO` 之后 `source ~/.config/claude-notify/env`（launchd 的子进程默认 env 极少）。

### 为什么不做 watchdog

**不写** `monitor_ingest.sh`，**不加**第二个 launchd job。原因：

- 每天必收一条 ✅ → "沉默 = 异常" 由用户自己识别。这就是终极告警层。
- 加 watchdog 只能补"runner 根本没启动"这一类盲点，但它本身也跑在同一台 Mac 同一个 launchd 下——和 ingest 一起挂的概率不可忽略。再叠 watchdog2 是无尽递归。
- 用户明确选择"不收到通知就主动来问 Claude"，把可靠性最后一层外包给人脑而不是再写一层代码。

## 为什么不用 cron（2026-05-05 教训）

2026-05-05 cron 静默失败，今早 09:30 没跑。诊断：

```
log show --predicate 'process == "cron"' --start "2026-05-05 09:00" --end "2026-05-05 10:00"
→ cron[3138] 触发了
log show --predicate '(process == "sandboxd")' ...
→ 09:29:54 起 sandboxd 每 15 秒一次 TCC 权限审批请求
```

**根因**：现代 macOS 的 sandbox/TCC 会拦住 `/usr/sbin/cron` 启动的子进程，要求弹窗授权——但 cron 是 headless 进程，**没人能点"允许"**，请求超时 → 脚本直接没跑，也没 mail，也没日志。

历史回放：用户 2025-12-25 同一台 Mac 也因为这个原因失败过另一份 cron（`update_epg.sh: Operation not permitted`），mail spool 里能找到。

**修法**：迁到 launchd，绕开 cron 的 TCC 困境。launchd 是 macOS 一等公民，TCC 路径正常工作；同时获得"睡眠错过会补跑"的 bonus。

如果未来某天 launchd 也出问题，备选思路是给 `/usr/sbin/cron` 授予 Full Disk Access（系统设置 → 隐私与安全性 → 完整磁盘访问 → +`/usr/sbin/cron`）。但 launchd 是更长期解。

## launchd 注意事项

1. **plist 改动后必须 reload**：`launchctl unload ~/Library/LaunchAgents/com.thailand10.daily-ingest.plist && launchctl load -w ~/Library/LaunchAgents/com.thailand10.daily-ingest.plist`
2. **检查最近一次执行**：`launchctl print gui/$(id -u)/com.thailand10.daily-ingest` 看 `last exit code`、`last exit reason`、`runs`
3. **launchd 自身的 stdout/stderr 日志**：在 `logs/launchd-stdout.log` / `logs/launchd-stderr.log`，与 wrapper 的主日志互补——wrapper 没启动时的失败信息会落在这里
4. **不要把 plist 放进 git** —— 路径里硬编码了 `/Users/Ade/...`，对其他机器无意义。如需在另一台 Mac 部署，从此文档中模板化重新生成
