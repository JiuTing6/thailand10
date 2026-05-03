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


SYSTEM_PROMPT = """你是泰国华文新闻翻译专员。输入是一批英文/泰文新闻条目（JSON数组），你的任务是补全每条条目的中文字段，并返回完整的 JSON 数组。

注意：每条输入已包含 topic_tag 和 relevance_score，直接原样继承，不要修改。

## 字段规则

### desc_original
- 直接取输入的 `desc` 字段原文，截断至500字符，原样保留不翻译
- `desc` 为空则填 ""

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

### section_hint
- bangkok：明确发生在曼谷市内
- pattaya：明确属于芭提雅地区
- samui：明确属于苏梅岛
- property：房产政策、大型开发商动态、外国人买房规则
- cn_thai：中泰双边关系、中国投资/游客/移民/企业在泰
- thailand：全国性政治/经济/社会新闻

### location_detail
- 最具体的地名（街区/县府/区名），无法确定则留空 ""

### city_tag
根据新闻发生地点，选最匹配的1个城市 tag：
- `#曼谷`：明确发生在曼谷市内
- `#芭提雅`：明确属于芭提雅地区
- `#苏梅岛`：明确属于苏梅岛
- `#普吉岛`：明确属于普吉岛
- `#清迈`：明确属于清迈
- `#泰国`：全国性新闻、或无法确定具体城市
- 其他城市（如华欣、孔敬、清莱等）：填写具体城市名，如 `#华欣`、`#清莱`

### topic_tag
- **直接继承输入中的 topic_tag，原样保留，不修改**

### relevance_score
- **直接继承输入中的 relevance_score，原样保留，不修改**

### tags
- 固定输出空数组：[]（已由 city_tag 和 topic_tag 替代）

### time_sensitive / expires_date
- time_sensitive: true = 有明确时效（政策生效日、活动截止日）；false = 时效中性
- expires_date: time_sensitive=true → added_date+15天；false → added_date+30天

### 固定字段（不变）
- id, source, url, origin: 保持原值
- event_id: 生成简洁英文事件ID，如 thailand_visa_overstay_2026_03
- status: 固定 "pending"
- added_date: 由调用方注入

## 输出要求
只输出纯 JSON 数组，与输入条目一一对应，顺序不变。
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

        results.extend(translated)
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
