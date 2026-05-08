# Daily Ingest 架构

**最后更新**：2026-05-04

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
- **Pipeline 入口**：[`ingest_runner.py`](../ingest_runner.py) —— 抓 RSS → filter → dedup → translate → pool merge → git commit/push
- **Push 凭证**：用 Mac 上日常 `~/.gitconfig` + macOS keychain，`git push` 直接走

### 性能基线

完整 ingest（约 39 条 RSS / day）耗时 **~12.5 分钟**：

| Step | 耗时占比 |
|---|---|
| Step 7 Translation（7 batches × 5 items via Haiku CLI） | **~85%（~10 分钟）** |
| Step 6a Filter | ~5% |
| Step 6b Dedup | ~5% |
| Fetch RSS / Pool merge / Git push | <5% |

**警戒线**：突然超过 20 分钟应排查（API 慢 / batch 卡死 / RSS 站点改版导致重试）。如果想加速，最直接的方向是 Translation 批次并行化。

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
