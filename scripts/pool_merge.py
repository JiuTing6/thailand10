#!/usr/bin/env python3
"""
pool_merge.py — 将翻译标注后的新条目合并入 news_pool.json + 月度归档

机制（2026-05 重构后）：
- pool（data/news_pool.json）：滚动窗口，只保留最近 30 天的条目（按 added_date）
- 月度归档（data/archive/YYYY-MM.json）：按 added_date 月份分桶的物化视图
  - 每次 ingest 都把新条目追加到当月归档（与 pool 平行写入，不是"毕业转移"）
  - 归档永不丢数据；pool 滚出窗口的条目仍在归档里
  - pool 与归档的同月条目自然重叠，前端按 tab 切换展示
- data/archive/index.json：可用月份列表（降序），前端读这个生成 tab 列表

用法：
  python3 pool_merge.py \\
    --new-items translated.json \\
    --pool data/news_pool.json \\
    --out data/news_pool.json \\
    --today 2026-05-10
"""

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path


WINDOW_DAYS = 30
ARCHIVE_DIR = Path("data/archive")
INDEX_PATH = ARCHIVE_DIR / "index.json"


def load_json(path: Path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def append_to_monthly_archive(items: list, dry_run: bool) -> dict:
    """把条目按 added_date 月份追加到 archive/YYYY-MM.json（url 去重，新覆盖旧）。"""
    if not items:
        return {}

    by_month: dict = defaultdict(list)
    for item in items:
        ad = item.get("added_date", "")
        if len(ad) < 7:
            print(f"⚠️  跳过无 added_date 的条目: id={item.get('id')}", file=sys.stderr)
            continue
        by_month[ad[:7]].append(item)

    stats = {}
    for month, month_items in by_month.items():
        path = ARCHIVE_DIR / f"{month}.json"
        existing = load_json(path, [])
        # url 去重：新版本覆盖旧版本（重译/重刷可正确覆盖）
        seen = {}
        for it in existing + month_items:
            url = it.get("url")
            if url:
                seen[url] = it
        merged = list(seen.values())
        merged.sort(key=lambda x: x.get("added_date", ""), reverse=True)
        stats[month] = len(month_items)
        if not dry_run:
            write_json(path, merged)

    if not dry_run:
        existing_months = {p.stem for p in ARCHIVE_DIR.glob("*.json") if p.name != "index.json"}
        existing_months.update(by_month.keys())
        write_json(INDEX_PATH, sorted(existing_months, reverse=True))

    return stats


def main():
    parser = argparse.ArgumentParser(description="Merge new items into pool + monthly archive")
    parser.add_argument("--new-items", required=True)
    parser.add_argument("--pool", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--today", required=True, help="YYYY-MM-DD")
    parser.add_argument("--update-last-ingest", help="Path to last_ingest.txt to update after merge")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    today = datetime.strptime(args.today, "%Y-%m-%d").date()
    cutoff = (today - timedelta(days=WINDOW_DAYS)).isoformat()

    # 现有 pool
    pool = load_json(Path(args.pool), [])
    print(f"📂 现有 pool: {len(pool)} 条")

    # 新条目
    try:
        with open(args.new_items, "r", encoding="utf-8") as f:
            new_items = json.load(f)
        print(f"📥 新条目: {len(new_items)} 条")
    except FileNotFoundError:
        print(f"❌ 新条目文件不存在: {args.new_items}")
        sys.exit(1)

    # URL 去重：过滤掉 pool 中已存在的
    existing_urls = {item["url"] for item in pool}
    before_dedup = len(new_items)
    new_items = [item for item in new_items if item["url"] not in existing_urls]
    skipped_url = before_dedup - len(new_items)
    if skipped_url > 0:
        print(f"⚠️  URL 重复跳过: {skipped_url} 条")

    # 写月度归档（pool 的平行物化视图，永不丢数据）
    if new_items:
        stats = append_to_monthly_archive(new_items, dry_run=args.dry_run)
        details = ", ".join(f"{m}: +{n}" for m, n in sorted(stats.items()))
        print(f"📦 写入月度归档: {details}")

    # 合并进 pool 并按 added_date 降序
    pool.extend(new_items)
    pool.sort(key=lambda x: x.get("added_date", ""), reverse=True)

    # 滚动窗口：丢弃超过 30 天的（它们已在归档里）
    before_trim = len(pool)
    pool = [item for item in pool if item.get("added_date", "") >= cutoff]
    trimmed = before_trim - len(pool)
    if trimmed > 0:
        print(f"✂️  pool 滚出窗口: {trimmed} 条（仍保留在归档里）")

    print(f"✅ 合并后 pool: {len(pool)} 条（窗口 cutoff={cutoff}，新增 {len(new_items)} 条）")

    if new_items:
        p_counts = {"P1": 0, "P2": 0, "P3": 0}
        topic_counts = {}
        for item in new_items:
            p = item.get("importance", "?")
            p_counts[p] = p_counts.get(p, 0) + 1
            t = item.get("topic_tag", "?")
            topic_counts[t] = topic_counts.get(t, 0) + 1
        print(f"   重要性: P1={p_counts.get('P1',0)} P2={p_counts.get('P2',0)} P3={p_counts.get('P3',0)}")
        print(f"   主题: {dict(topic_counts)}")

    if args.dry_run:
        print("🔍 Dry-run 模式，不写入文件")
        return

    write_json(Path(args.out), pool)
    print(f"💾 写入: {args.out}")

    if args.update_last_ingest:
        with open(args.update_last_ingest, "w") as f:
            f.write(args.today + "\n")
        print(f"📅 last_ingest.txt → {args.today}")


if __name__ == "__main__":
    main()
