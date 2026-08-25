# Hostinger 反馈端点部署

`feedback.php` 是 newsroom 👍/👎 投票的回流端点，跑在 Ade 的 Hostinger 共享主机（PHP）。

**目标域名**：`https://thailand10.j2cay.com`（Hostinger 上 `j2cay.com` 的子域，与 §C 迁站后的 newsroom **同一主机同一域名**）。
newsroom 页面与端点同源，因此 **无跨域、无混合内容问题**，前端可用相对路径调用。

## 数据流（同源版）

```
浏览器 newsroom（https://thailand10.j2cay.com/newsroom.html）
   │ POST(Bearer token)  ← 相对路径 "feedback.php"，同源
   ▼
https://thailand10.j2cay.com/feedback.php ──append──▶ votes.jsonl
   ▲
   │ GET(Bearer token) 聚合每 id 最新票
Mac mini ingest（pull_feedback）─────────────────────┘
```

## 三处共享 secret 必须一致

本次生成的 token（与 newsroom.html 客户端可见，仅作轻量防滥用）：

```
45e1b02db0d75cd0b0e902d1d12393f7ed67243f1f04d175
```

填入三处：

1. `feedback.php` 顶部 `$TOKEN`
2. `newsroom.html` 里 `FEEDBACK_TOKEN`；同时把 `FEEDBACK_URL` 设为相对路径 `"feedback.php"`（同源，最稳）
3. Mac mini `~/.config/claude-notify/env`：
   ```sh
   export T10_FEEDBACK_URL="https://thailand10.j2cay.com/feedback.php"
   export T10_FEEDBACK_TOKEN="45e1b02db0d75cd0b0e902d1d12393f7ed67243f1f04d175"
   ```
   （wrapper 脚本 `scripts/thailand10-daily-ingest.sh` 已 `source` 这个文件，ingest_runner 的 `pull_feedback()` 读这两个环境变量。ingest 是从本机发 GET，跨主机，所以用**绝对 https 地址**。）

> 注：token 嵌在公开页面的 JS 里、任何人查看源码可见，本就只是“轻量防滥用”而非真正机密；提交进 repo 不增加额外暴露。若日后要更强的防护，再上 rate-limit / 服务端校验。

## 部署步骤（hPanel 文件管理器 / FTP，无需 SSH）

1. hPanel → Subdomains → 建子域 `thailand10.j2cay.com`，记下它的 Document Root（形如 `/home/u239979640/domains/j2cay.com/public_html/thailand10` 或独立目录）。
2. 把 `feedback.php` 上传到该 Document Root（与 `newsroom.html`、`data/` 同级）。`votes.jsonl` 首次 POST 时自动创建——确保目录对 PHP 可写。
3. 改 `feedback.php` 里的 `$TOKEN` 为上面的 token。
4. 同源后 CORS 非必需：`$ALLOWED_ORIGIN` 留 `'*'` 无害；要收紧可设 `'https://thailand10.j2cay.com'`。
5. 确认子域已启用 **HTTPS**（Hostinger 免费 SSL）。

## 验证

```sh
URL="https://thailand10.j2cay.com/feedback.php"
TOK="45e1b02db0d75cd0b0e902d1d12393f7ed67243f1f04d175"
# 1. 无 token → 403
curl -s -o /dev/null -w '%{http_code}\n' "$URL"                     # 403
# 2. 投一票
curl -s -X POST "$URL" -H "Authorization: Bearer $TOK" \
  -H 'Content-Type: application/json' \
  -d '{"id":"test123","vote":"down","title_cn":"测试标题","topic_tag":"#社会","source":"Test"}'
# → {"ok":true}
# 3. 拉取聚合
curl -s "$URL" -H "Authorization: Bearer $TOK"
# → {"updated_at":"...","votes":[{"id":"test123","vote":"down",...}]}
# 4. 预检 CORS（同源时浏览器不发，但保留可用）
curl -s -o /dev/null -w '%{http_code}\n' -X OPTIONS "$URL"          # 204
```

## 与 §C 迁站的关系

本端点与 newsroom 迁站（见 `~/TASKS.md`「newsroom 迁出 GitHub Pages 到 Hostinger」）**合并到同一域名 `thailand10.j2cay.com`**：
- newsroom.html + `data/` + `assets/` 同步到该子域 Document Root（rsync/FTP）；
- `feedback.php` 放同一目录，前端相对路径调用；
- GitHub repo 保留作代码 + 数据归档备份。
