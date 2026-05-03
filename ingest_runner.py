#!/usr/bin/env python3
"""Thailand10 Ingest Pipeline v2 Runner"""

import subprocess
import sys
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

os.chdir(Path(__file__).resolve().parent)

# Step 1: Determine TODAY
TODAY = datetime.now().strftime('%Y-%m-%d')
print(f"[Step 1] TODAY = {TODAY}")

# Step 2: Determine LAST_DATE
try:
    with open('data/last_ingest.txt', 'r') as f:
        LAST_DATE = f.read().strip()
except:
    LAST_DATE = (datetime.now() - timedelta(days=4)).strftime('%Y-%m-%d')

print(f"[Step 2] LAST_DATE = {LAST_DATE}")

# Step 3: Fetch RSS
print(f"[Step 3] Fetching RSS from {LAST_DATE} to {TODAY}...")
result = subprocess.run(
    [sys.executable, 'scripts/fetch_rss.py', '--start', LAST_DATE, '--end', TODAY, 
     '-o', f'data/issues/{TODAY}-raw.json'],
    capture_output=True,
    text=True
)
print(result.stdout)
if result.returncode != 0:
    print(f"Error: {result.stderr}", file=sys.stderr)
    sys.exit(1)

# Step 4: Flatten
print(f"[Step 4] Flattening raw data...")
exec(f"""
import json
today = '{TODAY}'
with open(f'data/issues/{{today}}-raw.json') as f:
    raw = json.load(f)
items = []
for item in raw.get('items', []):
    item.setdefault('origin', 'rss')
    items.append(item)
with open(f'data/issues/{{today}}-flat.json', 'w') as f:
    json.dump(items, f, ensure_ascii=False, indent=2)
print(f'展平完成: {{len(items)}} 条')
""")

# Step 5: Prepare Pool Excerpt
print(f"[Step 5] Preparing pool excerpt...")
exec(f"""
import json
from datetime import datetime, timedelta
today = datetime.strptime('{TODAY}', '%Y-%m-%d').date()
cutoff = (today - timedelta(days=10)).isoformat()
with open('data/news_pool.json') as f:
    pool = json.load(f)
recent = [item for item in pool if item.get('added_date','') >= cutoff]
recent.sort(key=lambda x: x.get('added_date',''), reverse=True)
excerpt = recent[:100]
with open(f'data/issues/{TODAY}-pool-excerpt.json', 'w') as f:
    json.dump(excerpt, f, ensure_ascii=False, indent=2)
print(f'Pool 摘录: {{len(excerpt)}} 条（10天内）')
""")

# Step 6a: Filter
print(f"[Step 6a] Running Filter (Layer 1)...")
result = subprocess.run(
    [sys.executable, 'scripts/filter.py',
     '--input', f'data/issues/{TODAY}-flat.json',
     '--output', f'data/issues/{TODAY}-filtered.json'],
    capture_output=True,
    text=True,
    timeout=600
)
print(result.stdout)
if result.returncode != 0:
    print(f"Filter Error: {result.stderr}", file=sys.stderr)
    sys.exit(1)

# Step 6b: Dedup
print(f"[Step 6b] Running Dedup (Layer 2)...")
result = subprocess.run(
    [sys.executable, 'scripts/dedup.py',
     '--input', f'data/issues/{TODAY}-filtered.json',
     '--pool', f'data/issues/{TODAY}-pool-excerpt.json',
     '--output', f'data/issues/{TODAY}-deduped.json'],
    capture_output=True,
    text=True,
    timeout=600
)
print(result.stdout)
if result.returncode != 0:
    print(f"Dedup Error: {result.stderr}", file=sys.stderr)
    sys.exit(1)

# Step 7: Translation
print(f"[Step 7] Running Translation (Layer 3)...")
result = subprocess.run(
    [sys.executable, 'scripts/translate.py',
     '--input', f'data/issues/{TODAY}-deduped.json',
     '--output', f'data/issues/{TODAY}-translated.json',
     '--batch', '5',
     '--date', TODAY],
    capture_output=True,
    text=True,
    timeout=600
)
print(result.stdout)
if result.returncode != 0:
    print(f"Translation Error: {result.stderr}", file=sys.stderr)
    sys.exit(1)

# Step 8: Pool Merge
print(f"[Step 8] Backing up pool...")
subprocess.run(['cp', 'data/news_pool.json', 'data/news_pool.bak.json'])

print(f"[Step 8] Merging pool...")
result = subprocess.run(
    [sys.executable, 'scripts/pool_merge.py',
     '--new-items', f'data/issues/{TODAY}-translated.json',
     '--pool', 'data/news_pool.json',
     '--out', 'data/news_pool.json',
     '--today', TODAY,
     '--update-last-ingest', 'data/last_ingest.txt'],
    capture_output=True,
    text=True
)
print(result.stdout)
if result.returncode != 0:
    print(f"Pool Merge Error: {result.stderr}", file=sys.stderr)
    sys.exit(1)

# Step 8.5: Push to GitHub
print(f"[Step 8.5] Pushing to GitHub...")
result = subprocess.run(
    ['git', 'add', 'data/news_pool.json'],
    capture_output=True,
    text=True
)
result = subprocess.run(
    ['git', 'commit', '-m', f'data: ingest {TODAY}'],
    capture_output=True,
    text=True
)
result = subprocess.run(
    ['git', 'push'],
    capture_output=True,
    text=True
)
print(result.stdout)
if result.returncode != 0:
    print(f"Git Warning: {result.stderr}")

print(f"\n✅ Pipeline completed successfully!")
