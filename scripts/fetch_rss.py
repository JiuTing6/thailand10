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

# 正文最大保留长度（content:encoded / description 去 HTML 后截断）
MAX_DESC = 1200

RSS_SOURCES = [
    # 方案A精简 (2026-04-21): 保留核心3源 + 加 Pattaya Mail
    # Bangkok Post 三源 (2026-05-31 扩覆盖)：各栏目最新 10 条，互相几乎不重叠
    # （实测重合 0-1），合并约 28 条独立全高相关。RSS 无图，统一 og:image 补图。
    # 跳过 news.xml —— 实测是国际/体育/旧闻 wire feed，泰国相关性极低。
    {
        "id": "bangkokpost_top",
        "name": "Bangkok Post",
        "url": "https://www.bangkokpost.com/rss/data/topstories.xml",
        "og_fallback": True  # RSS 无图，抓文章页 og:image 补图
    },
    {
        "id": "bangkokpost_thailand",
        "name": "Bangkok Post",
        "url": "https://www.bangkokpost.com/rss/data/thailand.xml",
        "og_fallback": True
    },
    {
        "id": "bangkokpost_business",
        "name": "Bangkok Post",
        "url": "https://www.bangkokpost.com/rss/data/business.xml",
        "og_fallback": True
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
    # Thairath 泰文大众媒体 (2026-05-31 加入)：分类滚动 feed，每个 20 条。
    # business/money/scoop 慢速高价值低噪音；news 高速噪音多但补最近热点。
    # 多 feed 间同 URL 文章由 main() 的 id 去重自动合并。
    {
        "id": "thairath_news",
        "name": "Thairath",
        "url": "https://www.thairath.co.th/rss/news",
        "lang": "th"
    },
    {
        "id": "thairath_business",
        "name": "Thairath",
        "url": "https://www.thairath.co.th/rss/business",
        "lang": "th"
    },
    {
        "id": "thairath_money",
        "name": "Thairath",
        "url": "https://www.thairath.co.th/rss/money",
        "lang": "th"
    },
    {
        "id": "thairath_scoop",
        "name": "Thairath",
        "url": "https://www.thairath.co.th/rss/scoop",
        "lang": "th"
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
    return text.strip()[:MAX_DESC]


# Media RSS 命名空间（部分源用 media:content / media:thumbnail 给图）
MEDIA_NS = "{http://search.yahoo.com/mrss/}"


def extract_image(item, desc_raw, content_raw):
    """从 RSS item 提取一张配图 URL（不下载，只取 URL）。
    优先级：enclosure(image) → media:content/thumbnail → 正文首个 <img src>。
    """
    # 1. <enclosure type="image/*">（Thairath 用这个）
    for enc in item.findall("enclosure"):
        if (enc.get("type") or "").startswith("image") and enc.get("url"):
            return enc.get("url")
    # 2. media:content / media:thumbnail
    for tag in (f"{MEDIA_NS}content", f"{MEDIA_NS}thumbnail"):
        el = item.find(tag)
        if el is not None and el.get("url"):
            return el.get("url")
    # 3. content:encoded / description 里的首个 <img src>（Thaiger/Pattaya Mail/头条）
    for blob in (content_raw, desc_raw):
        if blob:
            m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', blob)
            if m:
                return m.group(1)
    return ""


# Bangkok Post RSS 不带任何图片字段（全站极简 feed），但文章页有标准
# og:image。对 BKK 条目额外抓一次原文页补图。失败静默返回 ""，不影响主流程。
_OG_IMAGE_RE = re.compile(
    r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)', re.I)
_OG_IMAGE_RE2 = re.compile(
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image', re.I)


def fetch_og_image(url):
    """抓文章页的 og:image。仅用于 RSS 本身无图的源（如 Bangkok Post）。"""
    try:
        r = requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/126.0.0.0 Safari/537.36",
            },
            timeout=10,
        )
        if r.status_code != 200:
            return ""
        m = _OG_IMAGE_RE.search(r.text) or _OG_IMAGE_RE2.search(r.text)
        return m.group(1) if m else ""
    except Exception:
        return ""

def fetch_rss(source):
    items = []
    try:
        # 使用 requests，自动处理 SSL 验证 + certifi 管理
        response = requests.get(
            source["url"],
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                              "AppleWebKit/537.36 (KHTML, like Gecko) "
                              "Chrome/126.0.0.0 Safari/537.36",
                "Accept": "application/rss+xml, application/xml, text/xml, */*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            },
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

            desc_raw = desc_el.text if (desc_el is not None and desc_el.text) else ""
            content_el = item.find("content:encoded", ns)
            content_raw = content_el.text if (content_el is not None and content_el.text) else ""

            # 正文：优先 content:encoded（全文），退到 description（摘要）
            desc = strip_html(content_raw) if content_raw else strip_html(desc_raw)

            image = extract_image(item, desc_raw, content_raw)
            # RSS 无图的源（Bangkok Post）回退到抓原文页 og:image
            if not image and source.get("og_fallback"):
                image = fetch_og_image(link)

            items.append({
                "id":      make_hash(title, link),
                "source":  source["name"],
                "source_id": source["id"],
                "lang":    source.get("lang", "en"),
                "title":   title,
                "url":     link,
                "date":    pub_date.isoformat() if pub_date else "",
                "desc":    desc,
                "image":   image,
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
