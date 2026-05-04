# Daily Ingest 架构

**最后更新**：2026-05-04

## 当前架构（本地 cron）

Daily ingest 跑在 Ade 的 **Mac mini 本地**（24/7 不关机）。

- **触发器**：`crontab -l`
  ```
  30 9 * * * /Users/Ade/Projects/Thailand10/scripts/cron_ingest.sh
  ```
- **wrapper 脚本**：[`scripts/cron_ingest.sh`](../scripts/cron_ingest.sh) — 设置 PATH/locale，cd 到 repo，跑 `ingest_runner.py`，输出 tee 到日志
- **日志位置**：`logs/ingest-cron-YYYYMMDD-HHMMSS.log`（gitignored）
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

## 未完成 TODO

- **监控 + 告警**（用户明确表示不会去看 log，自动化必须自己 alert）
  - `scripts/monitor_ingest.sh`：cron 9:50am 跑（晚于 ingest 20 分钟）
  - 检查当天 `logs/ingest-cron-YYYYMMDD-*.log` 是否存在 + 末尾是否含 `✅ Pipeline completed successfully!`
  - 缺失或失败 → 发 Telegram 告警（用 [`docs/telegram-notify.md`](telegram-notify.md) 描述的 bot）
  - 成功则静默
  - 前置：Telegram bot token 应在 `~/.config/thailand10/env`，但 2026-05-04 检查时 mini 上该路径不存在，需先把配置补上

## macOS cron 三个坑

1. **Mac 必须在 9:30 醒着** —— cron 跟 launchd 不同，错过不补跑
2. **Full Disk Access**：macOS 较新版本可能要求 `/usr/sbin/cron` 有 FDA 权限。如果某天没跑，去 系统设置 → 隐私与安全性 → 完整磁盘访问 → 加 `cron`
3. **launchd 才是 macOS 推荐做法**（cron 是 deprecated 的 BSD 遗物）。cron 简单够用先这样跑；遇到莫名不触发再迁 launchd
