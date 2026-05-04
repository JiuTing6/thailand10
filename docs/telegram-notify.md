# Telegram 通知设置 & 使用指南

> **这份文档是 Claude 名下所有项目 Telegram 通知配置的「真相源」**。Thailand10 是首个落地项目，但本文档目的是供所有未来项目复用。
>
> Bot 一个就够，全局共享。每个新项目只做 §五.5「新项目接入 3 步」即可。
>
> （文档当前位置在 Thailand10 repo 下；如果未来有第二个 Claude Code 项目接入，可考虑迁到项目无关的共享位置——但现在不用提前迁。）

---

## 一、申请新 Bot（一次性，由用户完成）

### 1. 创建 bot
1. Telegram 里搜 `@BotFather` → 开对话
2. 发 `/newbot`
3. 起显示名（任意中文/英文，例：`Claude Notify`）
4. 起 username（必须以 `bot` 结尾，全局唯一，例：`ClaudeJiuTingNotifyBot`）
5. BotFather 返回一段消息，里面有 token，形如：
   ```
   1234567890:ABCdefGhIJKlmnOpQrStUvWxYz
   ```
   **token 要保密**，泄露 = 任何人能假冒此 bot。

### 2. 获取 chat_id
1. 在 Telegram 里点开你的新 bot，发任意一条消息（例如 `/start` 或 `hi`），**这步不能省**——bot 没收到过你的消息就不能主动给你发
2. 浏览器打开（替换 `<TOKEN>`）：
   ```
   https://api.telegram.org/bot<TOKEN>/getUpdates
   ```
3. 在返回 JSON 里找：
   ```json
   "chat": { "id": 12345678, "first_name": "...", ... }
   ```
   那个 `id` 就是 chat_id（个人是正整数）

### 3. 把 token + chat_id 给 Claude
贴格式：
```
TG_BOT_TOKEN=1234567890:ABC...
TG_CHAT_ID=12345678
```

---

## 二、本机配置（Claude 完成）

### 1. 写入 secrets 文件
不进 git，权限 600：
```bash
mkdir -p ~/.config/claude-notify
cat > ~/.config/claude-notify/env <<'EOF'
export TG_BOT_TOKEN=1234567890:ABC...
export TG_CHAT_ID=12345678
EOF
chmod 600 ~/.config/claude-notify/env
```

### 2. 项目 `.gitignore` 加一条
```
.env*
```
（防止误把 `.env` 类文件 commit 进 repo）

### 3. 写 `scripts/notify.py`
统一通知 helper。所有 runner 末尾调它。

```python
#!/usr/bin/env python3
"""Telegram 通知 helper。从环境变量读 token / chat_id。"""
import os, sys, urllib.parse, urllib.request

def notify(text: str, project: str = "Thailand10") -> bool:
    token = os.environ.get("TG_BOT_TOKEN")
    chat_id = os.environ.get("TG_CHAT_ID")
    if not token or not chat_id:
        print("notify: TG_BOT_TOKEN/TG_CHAT_ID 未设置，跳过", file=sys.stderr)
        return False
    msg = f"[{project}] {text}"
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": msg}).encode()
    try:
        with urllib.request.urlopen(url, data=data, timeout=10) as r:
            return r.status == 200
    except Exception as e:
        print(f"notify: 失败 {e}", file=sys.stderr)
        return False

if __name__ == "__main__":
    text = " ".join(sys.argv[1:]) or "test ping"
    ok = notify(text)
    sys.exit(0 if ok else 1)
```

### 4. 验证
```bash
source ~/.config/claude-notify/env
python3 scripts/notify.py "test ping"
```
Telegram 收到 `[Thailand10] test ping` → 配置成功。

---

## 三、运行时使用

### Runner 集成模式
`ingest_runner.py` / `publish_runner.py` 末尾：

```python
from scripts.notify import notify

try:
    # ... 跑 pipeline ...
    notify(f"✅ ingest done {today}: +{n_new} 条新闻，pool 共 {pool_size}")
except Exception as e:
    notify(f"❌ ingest FAILED {today}: {type(e).__name__}: {e}")
    raise
```

### 消息格式约定
- **必带项目前缀** `[Thailand10]`（多项目共用 bot 时方便区分）
- 成功用 ✅，失败用 ❌
- 失败消息把异常类型 + 简短原因放在前面，详细 traceback 写日志即可（Telegram 消息别太长）

---

## 四、本地 cron 注入 secrets

> **Note 2026-05-04**：原本规划的"云端 Claude Code Routine 注入 secrets"方案已不适用——云端 routine 因 RSS 源 IP 屏蔽问题被弃用（详见 [`ingest-architecture.md`](ingest-architecture.md)）。Daily ingest 现在跑在 Mac mini 本地 cron。

cron wrapper 脚本（如 `scripts/cron_ingest.sh`）只需 source 同一份共享 env：

```bash
[ -f ~/.config/claude-notify/env ] && source ~/.config/claude-notify/env
```

放在 `cd $REPO` 之后、跑主程序之前即可。所有 Claude Code 负责的项目都 source 这同一份文件，token/chat_id 全局唯一。

---

## 五、多项目复用规约

未来其他 Claude Code 项目要发通知时**复用此 bot，不再申请新的**。规约：

1. **共享 secrets 文件**：路径就是 `~/.config/claude-notify/env`，各项目 source 同一份
2. **前缀必须区分**：每个项目调 `notify()` 时改 `project=` 参数
3. **频率自律**：bot 是共享通道，单项目别一天发几十条；通知应该是"事件级"（成功/失败/异常），不是"日志级"
4. **失败静音问题**：notify 本身不抛异常（见上面实现），所以通知挂了不影响主流程。代价是 token 失效你不会知道——建议每月手动 ping 一次确认还活着

### 五.5 新项目接入 3 步

Bot 已经存在、`~/.config/claude-notify/env` 已经配好的前提下，新项目（假设叫 `Foo`）只需要：

1. **拷 `notify.py` 进新项目**：从已有项目（如 Thailand10）复制 `scripts/notify.py` 到 `Foo/scripts/notify.py`，无需改代码
2. **runner 末尾调用，前缀换成项目名**：
   ```python
   from scripts.notify import notify
   notify(f"✅ build done", project="Foo")
   ```
3. **触发器（cron / launchd / 手动脚本）开头 source 共享 env**：
   ```bash
   [ -f ~/.config/claude-notify/env ] && source ~/.config/claude-notify/env
   ```

完。同一个 chat 里收到的消息会按前缀自动区分：

```
[Thailand10] ✅ ingest done 5/4: +33 条
[Foo] ❌ build FAILED: TypeError ...
[Bar] ✅ deploy 2026-05-04
```

**反模式（别做）**：每个项目申请新 bot；每个项目自己存一份 token；或者去掉 `project=` 前缀让 chat 里全是无来源的消息。

---

## 六、未来升级：双向交互

**当前能力**：单向，runner → 用户。

**OpenClaw 旧体验**：用户给 bot 发命令 → agent 即时响应。

**Claude Code 原生不支持事件驱动**，要做双向得加层。三种方案：

### 方案 A：轮询（不推荐）
每 5/10 分钟跑一个 routine，调 `getUpdates` 拉新消息处理。
- ❌ 延迟大（一个轮询周期）
- ❌ 烧 token（每次都启动外层 session）
- ✅ 实现简单
- 仅在没有更好选择时考虑

### 方案 B：Webhook 中转（推荐升级路径）
Telegram 支持 `setWebhook`：消息进来 → POST 到指定 URL。
- 中转 URL 选 Cloudflare Worker（免费、零运维、就近边缘）
- Worker 收到消息 → 校验来源 → 调 Claude Code 的 `RemoteTrigger` 触发对应 routine（带参数）
- 体验：秒级响应，按调用计费
- 工作量：半天到一天（写 Worker + 配 webhook + 配 RemoteTrigger）

升级触发条件（满足任一即升级）：
- 出现 ≥3 次"在外面想立即触发 ingest 但要回去开 Mac"的真实场景
- Thailand10 跑稳后想接入更多自动化指令（手动补跑、查 pool、看上期统计）

### 方案 C：保持单向（默认）
不升级。需要交互时打开 Mac 操作。
- ✅ 零额外复杂度
- ✅ 零额外成本
- ❌ 离开 Mac 时无法干预

**当前选择：方案 C**。单向通知足够覆盖 Thailand10 的"知道跑没跑成"需求。

---

## 七、维护 & 故障排查

### 常用操作
- **撤换 token**（疑似泄露）：BotFather → `/mybots` → 选 bot → API Token → Revoke current token → 拿新 token → 改 `~/.config/claude-notify/env`
- **改 bot 显示名/头像**：BotFather → `/mybots` → 选 bot → Edit Bot
- **暂停通知**（不删 bot）：临时把 `TG_BOT_TOKEN` 改成空字符串，notify 会静默跳过
- **彻底删 bot**：BotFather → `/mybots` → 选 bot → Delete Bot

### 常见问题
| 现象 | 原因 | 解法 |
|---|---|---|
| 收不到消息 | bot 没收到过你的 `/start` | 在 Telegram 里给 bot 发任意消息 |
| `getUpdates` 返回空 | 你已经设置了 webhook，updates 被 webhook 消费 | 调 `deleteWebhook` 即可 |
| 401 Unauthorized | token 错 | 重核对，注意末尾别多空格 |
| 400 chat not found | chat_id 错，或没给 bot 发过消息 | 重新 `getUpdates` 拿正确 id |
| 消息太长被截断 | Telegram 单条消息 4096 字符上限 | notify 时只发摘要，详情写日志 |

---

## 八、Checklist（首次配置完成前过一遍）

- [ ] BotFather 创建新 bot，拿到 token
- [ ] 给新 bot 发过至少一条消息
- [ ] `getUpdates` 拿到 chat_id
- [ ] token + chat_id 写入 `~/.config/claude-notify/env`，权限 600
- [ ] `.gitignore` 包含 `.env*`
- [ ] `scripts/notify.py` 落地
- [ ] 本机手动 `python3 scripts/notify.py test ping` 收到消息
- [ ] runner 末尾调 `notify()` 集成完成
- [ ] cron wrapper（如 `scripts/cron_ingest.sh`）开头 source `~/.config/claude-notify/env`
- [ ] 首次本地 cron 跑通，Telegram 收到一条 `[Thailand10] ✅ ingest done ...`
