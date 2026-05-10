#!/usr/bin/env python3
"""
migrate_pool_to_archive.py — 一次性迁移：把现有 news_pool.json 按 added_date
月份分桶写入 data/archive/YYYY-MM.json，并生成 data/archive/index.json。

不修改 news_pool.json 本身（pool 仍是滚动 30 天窗口，与归档天然重叠）。

幂等：可重复跑，url 去重保留新版本。

Usage:
  python3 scripts/migrate_pool_to_archive.py [--dry-run]
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

POOL_PATH = Path("data/news_pool.json")
ARCHIVE_DIR = Path("data/archive")
INDEX_PATH = ARCHIVE_DIR / "index.json"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    with open(POOL_PATH) as f:
        pool = json.load(f)
    print(f"📂 pool: {len(pool)} 条")

    by_month: dict = defaultdict(list)
    for item in pool:
        ad = item.get("added_date", "")
        if len(ad) < 7:
            print(f"⚠️  跳过无 added_date: id={item.get('id')}", file=sys.stderr)
            continue
        by_month[ad[:7]].append(item)

    print(f"📊 月份分布: {dict((m, len(v)) for m, v in sorted(by_month.items()))}")

    if args.dry_run:
        print("🔍 Dry-run，不写文件")
        return

    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    for month, items in by_month.items():
        path = ARCHIVE_DIR / f"{month}.json"
        existing = json.load(open(path)) if path.exists() else []
        seen = {}
        for it in existing + items:
            url = it.get("url")
            if url:
                seen[url] = it
        merged = list(seen.values())
        merged.sort(key=lambda x: x.get("added_date", ""), reverse=True)
        with open(path, "w") as f:
            json.dump(merged, f, ensure_ascii=False, indent=2)
        print(f"💾 {path}: {len(merged)} 条")

    months = sorted(
        {p.stem for p in ARCHIVE_DIR.glob("*.json") if p.name != "index.json"},
        reverse=True,
    )
    with open(INDEX_PATH, "w") as f:
        json.dump(months, f, ensure_ascii=False, indent=2)
    print(f"📅 index.json: {months}")


if __name__ == "__main__":
    main()
