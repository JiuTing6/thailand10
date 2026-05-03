#!/usr/bin/env python3
"""
pool_merge.py — 将翻译标注后的新条目合并入 news_pool.json

用法：
  python3 pool_merge.py \
    --new-items translated.json \
    --pool ../../data/news_pool.json \
    --out ../../data/news_pool.json \
    --today 2026-03-09

  实验模式（不动生产）：
  python3 pool_merge.py \
    --new-items ../data/translated.json \
    --pool ../../data/news_pool.json \
    --out ../data/pool_result.json \
    --today 2026-03-09 \
    --dry-run
"""

import argparse
import json
import sys
from datetime import datetime, date


def main():
    parser = argparse.ArgumentParser(description="Merge new items into news_pool.json")
    parser.add_argument("--new-items", required=True, help="Path to translated.json (new items array)")
    parser.add_argument("--pool", required=True, help="Path to existing news_pool.json")
    parser.add_argument("--out", required=True, help="Output path for merged pool")
    parser.add_argument("--today", required=True, help="Today's date YYYY-MM-DD")
    parser.add_argument("--update-last-ingest", help="Path to last_ingest.txt to update after merge")
    parser.add_argument("--dry-run", action="store_true", help="Print stats only, don't write files")
    args = parser.parse_args()

    today = datetime.strptime(args.today, "%Y-%m-%d").date()

    # 读取现有 pool
    try:
        with open(args.pool, "r", encoding="utf-8") as f:
            pool = json.load(f)
        print(f"📂 现有 pool: {len(pool)} 条")
    except FileNotFoundError:
        pool = []
        print("📂 现有 pool: 空（首次运行）")

    # 读取新条目
    try:
        with open(args.new_items, "r", encoding="utf-8") as f:
            new_items = json.load(f)
        print(f"📥 新条目: {len(new_items)} 条")
    except FileNotFoundError:
        print(f"❌ 新条目文件不存在: {args.new_items}")
        sys.exit(1)

    # 归档过期条目
    before_archive = len(pool)
    pool = [
        item for item in pool
        if datetime.strptime(item["expires_date"], "%Y-%m-%d").date() >= today
    ]
    archived = before_archive - len(pool)
    if archived > 0:
        print(f"🗑️  归档过期: {archived} 条")

    # URL 去重：过滤掉 pool 中已存在 URL 的新条目
    existing_urls = {item["url"] for item in pool}
    before_dedup = len(new_items)
    new_items = [item for item in new_items if item["url"] not in existing_urls]
    skipped_url = before_dedup - len(new_items)
    if skipped_url > 0:
        print(f"⚠️  URL重复跳过: {skipped_url} 条")

    # 追加新条目
    pool.extend(new_items)

    # 按 added_date 降序排序
    pool.sort(key=lambda x: x.get("added_date", ""), reverse=True)

    print(f"✅ 合并后 pool: {len(pool)} 条（新增 {len(new_items)} 条）")

    # 统计
    if new_items:
        p_counts = {"P1": 0, "P2": 0, "P3": 0}
        section_counts = {}
        for item in new_items:
            p = item.get("importance", "?")
            p_counts[p] = p_counts.get(p, 0) + 1
            s = item.get("section_hint", "?")
            section_counts[s] = section_counts.get(s, 0) + 1
        print(f"   重要性: P1={p_counts.get('P1',0)} P2={p_counts.get('P2',0)} P3={p_counts.get('P3',0)}")
        print(f"   板块: {dict(section_counts)}")

    if args.dry_run:
        print("🔍 Dry-run 模式，不写入文件")
        return

    # 写回
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(pool, f, ensure_ascii=False, indent=2)
    print(f"💾 写入: {args.out}")

    # 更新 last_ingest.txt（可选）
    if args.update_last_ingest:
        with open(args.update_last_ingest, "w") as f:
            f.write(args.today + "\n")
        print(f"📅 last_ingest.txt → {args.today}")


if __name__ == "__main__":
    main()
