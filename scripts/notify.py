#!/usr/bin/env python3
"""Telegram 通知 helper。从环境变量读 token / chat_id。

配置真相源：docs/telegram-notify.md
Secrets: ~/.config/claude-notify/env (TG_BOT_TOKEN, TG_CHAT_ID)
"""
import os
import sys
import urllib.parse
import urllib.request


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
