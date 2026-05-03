#!/usr/bin/env python3
"""
7days_filter_pool.py
从 news_pool.json 筛选过去7天（含今天）的候选条目，
输出到 data/7days_news_MM-DD-YYYY.json，供 publish cron 使用。

Usage:
    python3 scripts/7days_filter_pool.py
    python3 scripts/7days_filter_pool.py --date 2026-03-26  # 指定基准日期（调试用）
"""

import json
import sys
import argparse
from datetime import date, timedelta
from pathlib import Path

# 路径
WORKSPACE = Path(__file__).parent.parent
POOL_FILE = WORKSPACE / "data" / "news_pool.json"
OUTPUT_DIR = WORKSPACE / "data"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="基准日期 YYYY-MM-DD（默认今天）")
    args = parser.parse_args()

    today = date.fromisoformat(args.date) if args.date else date.today()
    cutoff = today - timedelta(days=6)  # 含今天共7天

    # 读取 pool
    pool = json.loads(POOL_FILE.read_text(encoding="utf-8"))
    items = pool if isinstance(pool, list) else pool.get("items", [])

    # 过滤：added_date 在窗口内
    candidates = [
        item for item in items
        if item.get("added_date", "") >= str(cutoff)
    ]

    # 按 importance 升序（P1 最高），再按 relevance_score 降序
    importance_order = {"P1": 0, "P2": 1, "P3": 2}
    candidates.sort(key=lambda x: (
        importance_order.get(x.get("importance", "P3"), 2),
        -float(x.get("relevance_score", 0))
    ))

    # 只保留 Sonnet 选题需要的精简字段（无 summary_cn，选题靠 title_cn 即可）
    KEEP_FIELDS = [
        "id", "title_cn", "importance", "relevance_score",
        "section_hint", "topic_tag", "city_tag", "source", "url",
        "added_date", "event_id",
    ]
    slim = [{k: item.get(k) for k in KEEP_FIELDS} for item in candidates]

    # 输出文件名：7days_news_MM-DD-YYYY.json
    fname = f"7days_news_{today.strftime('%m-%d-%Y')}.json"
    out_path = OUTPUT_DIR / fname

    result = {
        "generated": str(today),
        "window_start": str(cutoff),
        "window_end": str(today),
        "total": len(slim),
        "items": slim,
    }
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"✅ 筛选完成：{len(candidates)} 条（{cutoff} ~ {today}）")
    print(f"📄 输出：{out_path}")
    return str(out_path)


if __name__ == "__main__":
    main()
