"""Thailand10 Claude CLI helper.

封装本机 `claude -p` 调用，复用 Claude.app Max 订阅。
所有 LLM 调用入口统一走这里。

成本铁律：
- filter / dedup / translate 永远用 claude-haiku-4-5
- publish 选题用 claude-sonnet-4-6（项目里唯一允许的 Sonnet 用法）
- 不设 model 默认值，强制调用方显式传，防止"忘了写"默认成贵模型
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from typing import Any


class ClaudeCallError(RuntimeError):
    """Claude CLI 调用失败的统一异常。"""


def call_claude(
    prompt: str,
    model: str,
    expect_json: bool = True,
    timeout: int = 120,
    max_retries: int = 3,
) -> Any:
    """调本机 claude CLI 跑一次推理。

    Args:
        prompt: 发给模型的完整 prompt（system + user 合并；如需分离用 \\n\\n 隔）
        model: 必传。"claude-haiku-4-5" 或 "claude-sonnet-4-6"
        expect_json: True → 把模型回复当 JSON 二次 parse 后返回 dict/list；False → 返回原文 str
        timeout: 单次调用超时秒数
        max_retries: 网络/CLI 错误重试次数（不重试模型逻辑错误）

    Returns:
        expect_json=True → dict / list；expect_json=False → str

    Raises:
        ClaudeCallError: CLI 退出非零、超时、模型 is_error、JSON parse 失败
        ValueError: model 字段缺失
    """
    if not model:
        raise ValueError("model 必须显式传入（'claude-haiku-4-5' 或 'claude-sonnet-4-6'）")

    cmd = ["claude", "-p", "--model", model, "--output-format", "json"]
    last_err: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            proc = subprocess.run(
                cmd,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as e:
            last_err = e
            print(f"[claude_call] timeout (attempt {attempt}/{max_retries})", file=sys.stderr)
            if attempt < max_retries:
                time.sleep(2 ** attempt)
                continue
            raise ClaudeCallError(f"timeout after {max_retries} attempts: {e}") from e

        if proc.returncode != 0:
            last_err = ClaudeCallError(f"CLI exit {proc.returncode}: {proc.stderr.strip()}")
            print(f"[claude_call] CLI exit {proc.returncode} (attempt {attempt}/{max_retries})", file=sys.stderr)
            if attempt < max_retries:
                time.sleep(2 ** attempt)
                continue
            raise last_err

        try:
            envelope = json.loads(proc.stdout)
        except json.JSONDecodeError as e:
            raise ClaudeCallError(
                f"CLI 输出非合法 JSON: {e}\nstdout 前 500 字: {proc.stdout[:500]}"
            ) from e

        # 模型逻辑错误 — 不重试，直接抛
        if envelope.get("is_error"):
            raise ClaudeCallError(
                f"model is_error: {envelope.get('result', '<no result field>')}"
            )

        result_text = envelope.get("result", "")
        usage = envelope.get("usage", {})
        cache_read = usage.get("cache_read_input_tokens", 0)
        cache_write = usage.get("cache_creation_input_tokens", 0)
        out_tok = usage.get("output_tokens", 0)
        cache_status = "HIT" if cache_read > cache_write else "miss"
        print(
            f"[claude_call] model={model} out={out_tok}tok "
            f"cache={cache_status} (read={cache_read} write={cache_write})",
            file=sys.stderr,
        )

        if not expect_json:
            return result_text

        # 模型回复本身是 JSON 字符串，二次 parse
        # 容忍模型偶发包了 ```json ... ``` 代码块
        cleaned = result_text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            lines = [ln for ln in lines if not ln.strip().startswith("```")]
            cleaned = "\n".join(lines).strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            raise ClaudeCallError(
                f"模型回复非合法 JSON: {e}\nresult 前 500 字: {result_text[:500]}"
            ) from e

    # 不应到达
    raise ClaudeCallError(f"unexpected: exhausted retries; last_err={last_err}")


if __name__ == "__main__":
    # 自测：python3 scripts/claude_call.py
    print("=== 测试 1：纯文本 ===", file=sys.stderr)
    r = call_claude("Reply with exactly the word: OK", model="claude-haiku-4-5", expect_json=False)
    print(f"返回: {r!r}")

    print("\n=== 测试 2：JSON 模式 ===", file=sys.stderr)
    r = call_claude(
        'Return ONLY this JSON, no other text, no code fences: {"status": "ok", "n": 42}',
        model="claude-haiku-4-5",
        expect_json=True,
    )
    print(f"返回: {r!r}")
    assert isinstance(r, dict) and r.get("status") == "ok" and r.get("n") == 42, "JSON parse 失败"
    print("✅ 自测通过")
