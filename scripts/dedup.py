#!/usr/bin/env python3
"""
dedup.py — Thailand10 Layer 2: 语义去重

Usage:
  python3 dedup.py --input <filtered.json> --pool <pool-excerpt.json> --output <deduped.json>

All non-duplicate items pass through. Topic quota control is handled at publish time.
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from claude_call import call_claude, ClaudeCallError


# ── Config ──────────────────────────────────────────────────────────────────

MODEL = "claude-haiku-4-5"
BATCH_SIZE = 10


SYSTEM_PROMPT = """你是新闻去重过滤器。给定一批候选新闻条目和现有 pool（最近10天），判断候选条目是否与 pool 重复，返回不重复的条目。

## 去重规则（按优先级）
1. URL 完全相同 → skip（直接跳过）
2. 标题语义高度重合（同一事件，同一角度，无新增信息）→ skip
3. 同一事件但有新进展/新数据/新角度 → keep（正常保留）
4. 不确定 → 偏向 keep（宁可放进来，不要漏掉）

## 注意
- Pool 摘录已限定最近10天，因此比对范围有限，不要过于保守
- 目标是去掉明显重复，不是精细语义过滤

## 输出要求
只输出纯 JSON（字段名: items），只包含 keep 的候选条目，原样保留所有原始字段。
不含任何说明文字、不含代码块标记。
格式：{"items": [...]}
"""


def call_dedup(candidates: list, pool_excerpt: list) -> list:
    """对一批候选条目 + pool 上下文调 Haiku，返回保留的不重复条目。"""
    user_prompt = (
        f"## 现有 Pool（最近10天，共 {len(pool_excerpt)} 条）\n"
        + json.dumps(pool_excerpt, ensure_ascii=False)
        + f"\n\n## 候选条目（共 {len(candidates)} 条，请判断是否与 pool 重复）\n"
        + json.dumps(candidates, ensure_ascii=False)
        + "\n\n返回不重复的候选条目（JSON格式，字段名 items）："
    )
    full_prompt = SYSTEM_PROMPT + "\n\n" + user_prompt

    parsed = call_claude(full_prompt, model=MODEL, expect_json=True, timeout=180)

    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict):
        if "items" in parsed:
            return parsed["items"]
        for v in parsed.values():
            if isinstance(v, list):
                return v
    sys.exit(f"❌ Unexpected response shape: {type(parsed).__name__} {str(parsed)[:200]}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Path to filtered JSON (candidates)")
    parser.add_argument("--pool", required=True, help="Path to pool excerpt JSON")
    parser.add_argument("--output", required=True, help="Path to write deduped JSON")
    parser.add_argument("--batch", type=int, default=BATCH_SIZE, help="Candidates per API call")
    args = parser.parse_args()

    with open(args.input) as f:
        candidates = json.load(f)

    with open(args.pool) as f:
        pool_excerpt = json.load(f)

    # Use only id, title, url from pool to save tokens
    pool_slim = [
        {"id": x.get("id", ""), "title": x.get("title_cn") or x.get("title", ""), "url": x.get("url", "")}
        for x in pool_excerpt
    ]

    total_input = len(candidates)
    print(f"📥 Loaded {total_input} candidates, {len(pool_slim)} pool items")

    results = []
    batches = [candidates[i:i+args.batch] for i in range(0, len(candidates), args.batch)]

    for i, batch in enumerate(batches, 1):
        print(f"🔄 Batch {i}/{len(batches)} ({len(batch)} candidates)...", end=" ", flush=True)
        try:
            kept = call_dedup(batch, pool_slim)
        except ClaudeCallError as e:
            sys.exit(f"❌ Dedup API failed on batch {i}: {e}")
        print(f"✅ kept {len(kept)}/{len(batch)}")
        results.extend(kept)
        time.sleep(1)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    kept_count = len(results)
    skip_count = total_input - kept_count
    print(f"✅ Written {kept_count} items to {args.output}")
    print(f"DEDUP_RESULT: input={total_input} keep={kept_count} skip={skip_count}")


if __name__ == "__main__":
    main()
