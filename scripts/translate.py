#!/usr/bin/env python3
"""
translate.py — Thailand10 Translation Step

Usage:
  python3 translate.py --input <deduped.json> --output <translated.json> --date <YYYY-MM-DD>
"""

import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from claude_call import call_claude, ClaudeCallError


# ── Config ──────────────────────────────────────────────────────────────────

MODEL = "claude-haiku-4-5"
BATCH_SIZE = 5


SYSTEM_PROMPT = """你是泰国华文新闻翻译专员。输入是一批英文/泰文新闻条目（JSON数组），输出每条对应的中文字段。

注意：每条输入已包含 topic_tag、city_tag、relevance_score，由 filter 阶段确定，**translate 不重复打 tag**。`desc_original` 由 python 机械截取 desc，translate **不输出** desc_original。

## 字段规则

### title_cn
- 信达雅，不要机翻腔
- 专有名词首次出现附英文（如：披集县 Phichit、素坤逸路 Sukhumvit）

### summary_cn
- 基于 desc 提炼翻译成中文，100-150字
- 抓核心事实，结合泰国背景解读，保持客观中立
- 专有名词同 title_cn 规则
- 禁止 Markdown，纯文字
- 若 desc 为空填 ""

### importance
- P1：直接影响在泰外国人日常（政策/签证/治安/法律/物价）
- P2：基建大项目、重大楼盘、重要经济数据、奇闻要案
- P3：常规经济、促销活动、一般旅游资讯

## 输出要求
**只输出每条的 id 字段 + 新生成的 3 个字段**（不要回显原始 title/desc/source/url/origin/topic_tag/city_tag/relevance_score/lang/date 等任何输入字段，避免转义问题导致 JSON 失败）。

每条只需输出：id, title_cn, summary_cn, importance

格式：{"items": [...]}，与输入条目一一对应，顺序不变。无代码块标记，无说明文字。

## ⚠️ JSON 转义铁律（违反会导致整批失败）
- **中文引号一律用「」或『』，绝对不要在中文里用 ASCII 双引号 `"`**
  - 错误：`"title_cn": ""高风险"行业"`（内嵌 `"` 破坏 JSON）
  - 正确：`"title_cn": "「高风险」行业"`
- 英文专有名词不需要加引号包裹（如直接写 `Sukhumvit` 不写 `"Sukhumvit"`）
- 若必须在 JSON 字符串值里出现 ASCII 双引号，必须转义为 `\"`
"""


def call_translate(items: list, added_date: str) -> list:
    """对一批条目调 Haiku 翻译，返回包含中文字段的条目数组。"""
    items_with_date = [{**item, "added_date": added_date} for item in items]
    user_prompt = (
        f"今日日期: {added_date}\n\n"
        f"请翻译以下 {len(items)} 条新闻，返回完整 JSON 数组（字段名: items）：\n\n"
        + json.dumps(items_with_date, ensure_ascii=False)
    )
    full_prompt = SYSTEM_PROMPT + "\n\n" + user_prompt

    parsed = call_claude(full_prompt, model=MODEL, expect_json=True, timeout=600)

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
    parser.add_argument("--input", required=True, help="Path to deduped JSON")
    parser.add_argument("--output", required=True, help="Path to write translated JSON")
    parser.add_argument("--date", default=str(date.today()), help="YYYY-MM-DD (default: today)")
    parser.add_argument("--batch", type=int, default=BATCH_SIZE, help="Items per API call")
    args = parser.parse_args()

    with open(args.input) as f:
        items = json.load(f)

    print(f"📥 Loaded {len(items)} items from {args.input}")

    results = []
    batches = [items[i:i+args.batch] for i in range(0, len(items), args.batch)]

    for i, batch in enumerate(batches, 1):
        print(f"🔄 Batch {i}/{len(batches)} ({len(batch)} items)...", end=" ", flush=True)
        try:
            translated = call_translate(batch, args.date)
        except ClaudeCallError as e:
            sys.exit(f"❌ Translate API failed on batch {i}: {e}")

        if len(translated) != len(batch):
            print(f"⚠️  count mismatch: sent {len(batch)}, got {len(translated)}")
        else:
            print("✅")

        # Model 只回新字段 + id，按 id 查回原 batch item 并 merge 原始字段
        # desc_original 由 python 机械截取（避免模型回显引号导致 JSON 失败）
        # DEAD_FIELDS 从 orig 透传剔除（避免 RSS 源的 tags 等死字段渗入 pool）
        DEAD_FIELDS = {"section_hint", "location_detail", "event_id", "status", "tags"}
        batch_by_id = {it["id"]: it for it in batch}
        for new_fields in translated:
            tid = new_fields.get("id") if isinstance(new_fields, dict) else None
            if tid and tid in batch_by_id:
                orig = batch_by_id[tid]
                orig_clean = {k: v for k, v in orig.items() if k not in DEAD_FIELDS}
                desc_original = (orig.get("desc") or "")[:500]
                merged = {**orig_clean, **new_fields, "desc_original": desc_original, "added_date": args.date}
                results.append(merged)
            else:
                results.append({**new_fields, "added_date": args.date})
        time.sleep(1)

    # Fallback: title_cn 为空则用 title 兜底
    fallback_count = 0
    for item in results:
        if not item.get('title_cn') and item.get('title'):
            item['title_cn'] = item['title']
            fallback_count += 1
    if fallback_count:
        print(f"⚠️  title_cn fallback: {fallback_count} 条（用 title 兜底）")

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    p1 = sum(1 for x in results if x.get("importance") == "P1")
    p2 = sum(1 for x in results if x.get("importance") == "P2")
    p3 = sum(1 for x in results if x.get("importance") == "P3")
    print(f"✅ Written {len(results)} items to {args.output}")
    print(f"TRANSLATION_RESULT: total={len(results)} P1={p1} P2={p2} P3={p3}")


if __name__ == "__main__":
    main()
