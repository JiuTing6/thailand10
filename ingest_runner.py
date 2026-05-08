#!/usr/bin/env python3
"""Thailand10 Ingest Pipeline v2 Runner"""

import subprocess
import sys
import json
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

os.chdir(Path(__file__).resolve().parent)

sys.path.insert(0, str(Path(__file__).resolve().parent / 'scripts'))
from notify import notify  # noqa: E402


def run_step(name: str, argv, timeout=None):
    """Run a subprocess step; raise RuntimeError on non-zero exit."""
    result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    if result.returncode != 0:
        raise RuntimeError(f"{name} exit={result.returncode}: {result.stderr.strip()[:200]}")
    return result


def main():
    t0 = time.monotonic()

    # Step 1: Determine TODAY
    TODAY = datetime.now().strftime('%Y-%m-%d')
    print(f"[Step 1] TODAY = {TODAY}")

    # Step 2: Determine LAST_DATE
    try:
        with open('data/last_ingest.txt', 'r') as f:
            LAST_DATE = f.read().strip()
    except Exception:
        LAST_DATE = (datetime.now() - timedelta(days=4)).strftime('%Y-%m-%d')
    print(f"[Step 2] LAST_DATE = {LAST_DATE}")

    # Step 3: Fetch RSS
    print(f"[Step 3] Fetching RSS from {LAST_DATE} to {TODAY}...")
    run_step('fetch_rss', [
        sys.executable, 'scripts/fetch_rss.py',
        '--start', LAST_DATE, '--end', TODAY,
        '-o', f'data/issues/{TODAY}-raw.json',
    ])

    # fetch_rss 即便 4 源全失败也 exit 0，必须自己校验 items 数
    with open(f'data/issues/{TODAY}-raw.json') as f:
        raw_total = json.load(f).get('total', 0)
    print(f"[Step 3] Raw items fetched: {raw_total}")
    if raw_total == 0:
        raise RuntimeError(
            "fetch_rss returned 0 items — likely network/firewall blocked all RSS sources"
        )

    # Step 4: Flatten
    print(f"[Step 4] Flattening raw data...")
    with open(f'data/issues/{TODAY}-raw.json') as f:
        raw = json.load(f)
    items = []
    for item in raw.get('items', []):
        item.setdefault('origin', 'rss')
        items.append(item)
    with open(f'data/issues/{TODAY}-flat.json', 'w') as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    print(f'展平完成: {len(items)} 条')

    # Step 5: Prepare Pool Excerpt
    print(f"[Step 5] Preparing pool excerpt...")
    today_d = datetime.strptime(TODAY, '%Y-%m-%d').date()
    cutoff = (today_d - timedelta(days=10)).isoformat()
    with open('data/news_pool.json') as f:
        pool = json.load(f)
    recent = [item for item in pool if item.get('added_date', '') >= cutoff]
    recent.sort(key=lambda x: x.get('added_date', ''), reverse=True)
    excerpt = recent[:100]
    with open(f'data/issues/{TODAY}-pool-excerpt.json', 'w') as f:
        json.dump(excerpt, f, ensure_ascii=False, indent=2)
    print(f'Pool 摘录: {len(excerpt)} 条（10天内）')

    # Step 6a: Filter
    print(f"[Step 6a] Running Filter (Layer 1)...")
    run_step('filter', [
        sys.executable, 'scripts/filter.py',
        '--input', f'data/issues/{TODAY}-flat.json',
        '--output', f'data/issues/{TODAY}-filtered.json',
    ], timeout=600)

    # Step 6b: Dedup
    print(f"[Step 6b] Running Dedup (Layer 2)...")
    run_step('dedup', [
        sys.executable, 'scripts/dedup.py',
        '--input', f'data/issues/{TODAY}-filtered.json',
        '--pool', f'data/issues/{TODAY}-pool-excerpt.json',
        '--output', f'data/issues/{TODAY}-deduped.json',
    ], timeout=600)

    # Step 7: Translation
    print(f"[Step 7] Running Translation (Layer 3)...")
    run_step('translate', [
        sys.executable, 'scripts/translate.py',
        '--input', f'data/issues/{TODAY}-deduped.json',
        '--output', f'data/issues/{TODAY}-translated.json',
        '--batch', '5',
        '--date', TODAY,
    ], timeout=600)

    # Step 8: Pool Merge
    print(f"[Step 8] Backing up pool...")
    subprocess.run(['cp', 'data/news_pool.json', 'data/news_pool.bak.json'])

    print(f"[Step 8] Merging pool...")
    run_step('pool_merge', [
        sys.executable, 'scripts/pool_merge.py',
        '--new-items', f'data/issues/{TODAY}-translated.json',
        '--pool', 'data/news_pool.json',
        '--out', 'data/news_pool.json',
        '--today', TODAY,
        '--update-last-ingest', 'data/last_ingest.txt',
    ])

    # Step 8.5: Push to GitHub
    print(f"[Step 8.5] Pushing to GitHub...")

    def run_git(args, allow_empty_commit_skip=False):
        r = subprocess.run(['git', *args], capture_output=True, text=True)
        if r.stdout:
            print(r.stdout)
        if r.returncode != 0:
            if allow_empty_commit_skip and 'nothing to commit' in (r.stdout + r.stderr):
                print("[Step 8.5] Nothing to commit — skipping push.")
                return None
            raise RuntimeError(f"git {' '.join(args)}: {r.stderr.strip()[:200]}")
        return r

    run_git(['config', 'user.email', 'routine@thailand10.local'])
    run_git(['config', 'user.name', 'Thailand10 Routine'])
    run_git(['add',
             'data/news_pool.json',
             'data/last_ingest.txt',
             f'data/issues/{TODAY}-translated.json'])
    commit_result = run_git(['commit', '-m', f'data: ingest {TODAY}'],
                            allow_empty_commit_skip=True)
    if commit_result is not None:
        run_git(['push', 'origin', 'HEAD:main'])

    print(f"\n✅ Pipeline completed successfully!")

    try:
        with open(f'data/issues/{TODAY}-translated.json') as f:
            n_new = len(json.load(f))
    except Exception:
        n_new = -1
    try:
        with open('data/news_pool.json') as f:
            pool_size = len(json.load(f))
    except Exception:
        pool_size = -1
    elapsed = time.monotonic() - t0
    notify(
        f"✅ ingest done {TODAY}: +{n_new} 条，pool 共 {pool_size}，"
        f"耗时 {int(elapsed // 60)}m{int(elapsed % 60)}s"
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        today = datetime.now().strftime('%Y-%m-%d')
        msg = str(e).strip()[:300]
        notify(f"❌ ingest FAILED {today}: {type(e).__name__}: {msg}")
        raise
