#!/usr/bin/env python3
"""
Thailand10 RSS 抓取工具
用法：
  python3 fetch_rss.py 4                              # 抓过去4天
  python3 fetch_rss.py --start 2026-03-05            # 从指定日期抓到今天
  python3 fetch_rss.py --start 2026-03-05 --end 2026-03-08  # 指定日期范围
输出：JSON格式的原始新闻条目
"""

import json
import sys
import argparse
import requests
import xml.etree.ElementTree as ET
import hashlib
import re
from datetime import datetime, timezone, timedelta

# 命令行参数解析
parser = argparse.ArgumentParser(description='Thailand10 RSS 抓取工具')
parser.add_argument('days', nargs='?', type=int, default=None, help='抓取过去N天')
parser.add_argument('--start', type=str, help='开始日期 (YYYY-MM-DD)')
parser.add_argument('--end', type=str, help='结束日期 (YYYY-MM-DD)，默认今天')
parser.add_argument('-o', '--output', type=str, default=None, help='输出文件路径')
args = parser.parse_args()

OUTPUT_FILE = args.output

# 如果同时指定了 days 和 --start，优先 --start
if args.start:
    # 指定了开始日期
    start_date = datetime.strptime(args.start, "%Y-%m-%d").date()
    end_str = args.end if args.end else datetime.now(timezone.utc).strftime("%Y-%m-%d")
    end_date = datetime.strptime(end_str, "%Y-%m-%d").date()
    DAYS_BACK = (end_date - start_date).days + 1
else:
    # 没有指定开始日期
    DAYS_BACK = args.days if args.days else 4
    end_date = None

RSS_SOURCES = [
    # 方案A精简 (2026-04-21): 保留核心3源 + 加 Pattaya Mail
    {
        "id": "bangkokpost_top",
        "name": "Bangkok Post",
        "url": "https://www.bangkokpost.com/rss/data/topstories.xml"
    },
    {
        "id": "thaiger",
        "name": "The Thaiger",
        "url": "https://thethaiger.com/feed"
    },
    {
        "id": "thaiheadlines",
        "name": "泰国头条新闻",
        "url": "https://www.thaiheadlines.com/feed/",
        "lang": "zh"
    },
    {
        "id": "pattayamail",
        "name": "Pattaya Mail",
        "url": "https://www.pattayamail.com/feed"
    },
]

def make_hash(title, url):
    s = f"{title.strip().lower()}|{url.strip()}"
    return hashlib.md5(s.encode()).hexdigest()[:12]

def parse_rss_date(date_str):
    """解析 RSS pubDate 格式"""
    if not date_str:
        return None
    date_str = date_str.strip()
    formats = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
        "%d %b %Y %H:%M:%S %z",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except:
            continue
    return None

def strip_html(text):
    """简单去除HTML标签"""
    if not text:
        return ""
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()[:600]

def fetch_rss(source):
    items = []
    try:
        # 使用 requests，自动处理 SSL 验证 + certifi 管理
        response = requests.get(
            source["url"],
            headers={"User-Agent": "Bangkok-News-Bot/1.0"},
            timeout=10
        )
        response.raise_for_status()  # 抛出 HTTP 错误
        root = ET.fromstring(response.content)
        ns = {"content": "http://purl.org/rss/1.0/modules/content/"}

        # 计算截止日期
        if end_date:
            # 指定了日期范围：只抓 start_date 到 end_date 之间的
            # cutoff 设为 start_date（保留 start_date 当天及之后的）
            cutoff = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
        else:
            cutoff = datetime.now(timezone.utc) - timedelta(days=DAYS_BACK)

        for item in root.findall(".//item"):
            title_el  = item.find("title")
            link_el   = item.find("link")
            date_el   = item.find("pubDate")
            desc_el   = item.find("description")
            cats      = [c.text for c in item.findall("category") if c.text]

            title = title_el.text.strip() if title_el is not None and title_el.text else ""
            link  = link_el.text.strip()  if link_el  is not None and link_el.text  else ""
            if not title or not link:
                continue

            # 跳过德文内容（Pattaya Blatt）
            if "Pattaya Blatt" in str(cats) or "Deutsch" in str(cats):
                continue

            pub_date = parse_rss_date(date_el.text if date_el is not None else "")
            if pub_date and pub_date < cutoff:
                continue

            desc = ""
            if desc_el is not None and desc_el.text:
                desc = strip_html(desc_el.text)
            content_el = item.find("content:encoded", ns)
            if content_el is not None and content_el.text:
                desc = strip_html(content_el.text)[:600]

            items.append({
                "id":      make_hash(title, link),
                "source":  source["name"],
                "source_id": source["id"],
                "lang":    source.get("lang", "en"),
                "title":   title,
                "url":     link,
                "date":    pub_date.isoformat() if pub_date else "",
                "desc":    desc,
                "tags":    cats[:5]
            })

    except requests.exceptions.RequestException as e:
        print(f"[WARN] {source['name']}: {e}", file=sys.stderr)
    except ET.ParseError as e:
        print(f"[WARN] {source['name']}: XML Parse Error - {e}", file=sys.stderr)
    except Exception as e:
        print(f"[WARN] {source['name']}: {e}", file=sys.stderr)

    return items

def main():
    today = datetime.now(timezone.utc).date()
    all_items = []
    seen_ids = set()

    for source in RSS_SOURCES:
        items = fetch_rss(source)
        for item in items:
            if item["id"] not in seen_ids:
                seen_ids.add(item["id"])
                all_items.append(item)

    # 按日期排序（新→旧）
    all_items.sort(key=lambda x: x["date"], reverse=True)

    output = json.dumps({
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "days_back": DAYS_BACK,
        "start_date": args.start if args.start else None,
        "end_date": args.end if args.end else today.strftime("%Y-%m-%d"),
        "total": len(all_items),
        "items": all_items
    }, ensure_ascii=False, indent=2)

    if OUTPUT_FILE:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"[OK] {len(all_items)} items → {OUTPUT_FILE}", file=sys.stderr)
    else:
        print(output)

if __name__ == "__main__":
    main()
