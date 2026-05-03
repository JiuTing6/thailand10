#!/usr/bin/env python3
"""
build_issue.py
根据 Sonnet 输出的选题 JSON，从 news_pool.json 取完整条目，
用 summary_cn 作为正文，拼装 issue JSON。

Usage:
    python3 scripts/build_issue.py data/selected_YYYY-MM-DD.json

Input (selected_YYYY-MM-DD.json) 格式：
{
  "date": "2026-03-26",
  "issue": 10,
  "highlights": [2, 0, 8, 13, 5],
  "sections": {
    "thailand": ["id1", "id2", ...],
    "property": ["id3"],
    "bangkok":  ["id4"],
    "pattaya":  ["id5"],
    "cn_thai":  []
  }
}

Output: data/issues/YYYY-MM-DD.json（符合 build_html.py 期望格式）
"""

import json
import sys
from pathlib import Path
from datetime import date

WORKSPACE = Path(__file__).parent.parent
POOL_FILE = WORKSPACE / "data" / "news_pool.json"
ISSUES_DIR = WORKSPACE / "data" / "issues"

SECTION_ORDER = ["thailand", "property", "bangkok", "pattaya", "cn_thai"]


def load_pool_index(pool_file: Path) -> dict:
    """构建 id → item 索引"""
    raw = json.loads(pool_file.read_text(encoding="utf-8"))
    items = raw if isinstance(raw, list) else raw.get("items", [])
    return {item["id"]: item for item in items}


def build_article(item: dict) -> dict:
    """从 pool 条目组装 issue 文章（body = summary_cn）"""
    # 日期：取 date 字段前10位
    pub_date = (item.get("date") or "")[:10] or item.get("added_date", "")
    return {
        "title":     item.get("title_cn") or item.get("title", ""),
        "city_tag":  item.get("city_tag", "#泰国"),
        "topic_tag": item.get("topic_tag", ""),
        "body":      item.get("summary_cn") or item.get("desc", ""),
        "date":      pub_date,
        "source":    item.get("source", ""),
        "url":       item.get("url", ""),
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/build_issue.py data/selected_YYYY-MM-DD.json")
        sys.exit(1)

    selected_path = Path(sys.argv[1])
    if not selected_path.is_absolute():
        selected_path = WORKSPACE / selected_path

    if not selected_path.exists():
        print(f"❌ 找不到选题文件: {selected_path}")
        sys.exit(1)

    selected = json.loads(selected_path.read_text(encoding="utf-8"))
    issue_date = selected["date"]
    issue_num  = selected["issue"]
    highlights = selected.get("highlights", [])
    sections_ids = selected["sections"]

    print(f"📋 第{issue_num}期 {issue_date}，共 {sum(len(v) for v in sections_ids.values())} 条")

    # 加载 pool 索引
    print("📦 加载 news_pool.json ...")
    pool = load_pool_index(POOL_FILE)

    # 组装各板块
    sections = {}
    missing = []
    total = 0
    for section in SECTION_ORDER:
        ids = sections_ids.get(section, [])
        articles = []
        for aid in ids:
            item = pool.get(aid)
            if item:
                articles.append(build_article(item))
                total += 1
            else:
                missing.append(aid)
                print(f"  ⚠️ 找不到 id: {aid}（section: {section}）")
        if articles:
            sections[section] = articles

    if missing:
        print(f"⚠️ {len(missing)} 条 id 在 pool 中未找到")

    # 组装 issue JSON
    issue = {
        "date":       issue_date,
        "issue":      issue_num,
        "highlights": highlights,
        "sections":   sections,
    }

    # 输出
    ISSUES_DIR.mkdir(parents=True, exist_ok=True)
    out_path = ISSUES_DIR / f"{issue_date}.json"
    out_path.write_text(json.dumps(issue, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"✅ issue JSON 写入：{out_path}（{total} 条）")
    return str(out_path)


if __name__ == "__main__":
    main()
