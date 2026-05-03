#!/usr/bin/env python3
"""
generate_newsroom.py — Thailand10 News Room
读取 data/news_pool.json，生成 newsroom.html
"""

import json
import os
from datetime import datetime

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POOL = os.path.join(REPO, "data", "news_pool.json")
OUT  = os.path.join(REPO, "newsroom.html")

def main():
    with open(POOL, encoding="utf-8") as f:
        items = json.load(f)

    # 时间倒排
    def sort_key(x):
        return x.get("date", "") or x.get("added_date", "")
    items.sort(key=sort_key, reverse=True)

    # 统计 sections 和 tags
    from collections import Counter
    section_counts = Counter()
    tag_counts = Counter()
    for item in items:
        s = item.get("section_hint", "") or "other"
        section_counts[s] += 1
        for t in item.get("tags", []):
            tag_counts[t] += 1

    # Section 显示名
    SECTION_LABELS = {
        "thailand": "泰国",
        "bangkok": "曼谷",
        "pattaya": "芭提雅",
        "samui":   "苏梅岛",
        "property": "房产",
        "politics": "政治",
        "energy": "能源",
        "finance": "金融",
        "expat": "外籍",
        "cn_thai": "中泰",
        "other": "其他",
    }

    sections_json = json.dumps(
        [{"id": s, "label": SECTION_LABELS.get(s, s), "count": c}
         for s, c in section_counts.most_common()],
        ensure_ascii=False
    )
    tags_json = json.dumps(
        [{"tag": t, "count": c} for t, c in tag_counts.most_common(40)],
        ensure_ascii=False
    )
    items_json = json.dumps(items, ensure_ascii=False)

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    total = len(items)

    html = f"""<!DOCTYPE html>
<html lang="zh">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Thailand10 News Room | 新闻看板</title>
  <link rel="stylesheet" href="assets/style-thailand10.css">
  <style>
    /* ── News Room 专属样式 ── */
    .nr-header {{
      background: var(--primary);
      color: #fff;
      border-bottom: 3px solid var(--accent);
    }}
    .nr-header-inner {{
      max-width: 1100px;
      margin: 0 auto;
      padding: 24px 20px 20px;
      display: flex;
      align-items: flex-end;
      justify-content: space-between;
      gap: 12px;
      flex-wrap: wrap;
    }}
    .nr-title-block .kicker {{
      font-family: var(--font-ui);
      font-size: 11px;
      letter-spacing: 3px;
      text-transform: uppercase;
      color: #aaa;
      margin-bottom: 4px;
    }}
    .nr-title-block h1 {{
      font-size: 22px;
      font-family: var(--font-ui);
      font-weight: 700;
      letter-spacing: 1px;
    }}
    .nr-meta {{
      font-family: var(--font-ui);
      font-size: 12px;
      color: #999;
      text-align: right;
    }}
    .nr-meta strong {{ color: #ccc; }}

    /* ── 控制栏 ── */
    .nr-controls {{
      background: #fff;
      border-bottom: 1px solid var(--border);
      position: sticky;
      top: 0;
      z-index: 100;
      box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    }}
    .nr-controls-inner {{
      max-width: 1100px;
      margin: 0 auto;
      padding: 12px 20px;
    }}
    .nr-search-row {{
      display: flex;
      gap: 10px;
      align-items: center;
      margin-bottom: 10px;
    }}
    .nr-search {{
      flex: 1;
      padding: 8px 14px;
      border: 1px solid var(--border);
      border-radius: 6px;
      font-size: 14px;
      font-family: var(--font-ui);
      background: var(--bg);
      outline: none;
      transition: border-color .2s;
    }}
    .nr-search:focus {{ border-color: var(--primary); background: #fff; }}
    .nr-count {{
      font-family: var(--font-ui);
      font-size: 13px;
      color: var(--text-muted);
      white-space: nowrap;
    }}
    .nr-count strong {{ color: var(--accent); }}

    /* ── Section 筛选 ── */
    .nr-sections {{
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      margin-bottom: 8px;
    }}
    .sec-btn {{
      padding: 4px 12px;
      border-radius: 20px;
      border: 1px solid var(--border);
      background: var(--tag-bg);
      font-size: 12px;
      font-family: var(--font-ui);
      cursor: pointer;
      color: var(--text-muted);
      transition: all .15s;
    }}
    .sec-btn:hover {{ border-color: var(--primary); color: var(--primary); }}
    .sec-btn.active {{
      background: var(--primary);
      color: #fff;
      border-color: var(--primary);
    }}

    /* ── Tag 筛选 ── */
    .nr-tags-wrap {{
      display: flex;
      align-items: flex-start;
      gap: 8px;
    }}
    .nr-tags {{
      display: flex;
      flex-wrap: wrap;
      gap: 5px;
      flex: 1;
    }}
    .tag-btn {{
      padding: 3px 10px;
      border-radius: 12px;
      border: 1px solid var(--border);
      background: #fff;
      font-size: 11px;
      font-family: var(--font-ui);
      cursor: pointer;
      color: var(--text-muted);
      transition: all .15s;
    }}
    .tag-btn:hover {{ border-color: var(--accent-light); color: var(--accent); }}
    .tag-btn.active {{
      background: var(--accent);
      color: #fff;
      border-color: var(--accent);
    }}
    .clear-btn {{
      padding: 3px 10px;
      border-radius: 12px;
      border: 1px solid #ccc;
      background: #fff;
      font-size: 11px;
      font-family: var(--font-ui);
      cursor: pointer;
      color: #999;
      white-space: nowrap;
    }}
    .clear-btn:hover {{ color: var(--accent); border-color: var(--accent); }}

    /* ── 新闻卡片网格 ── */
    .nr-grid {{
      max-width: 1100px;
      margin: 0 auto;
      padding: 20px 20px 60px;
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
      gap: 16px;
    }}
    .nr-card {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 16px;
      cursor: pointer;
      transition: box-shadow .2s, border-color .2s;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }}
    .nr-card:hover {{
      box-shadow: 0 4px 16px rgba(0,0,0,0.1);
      border-color: #ccc;
    }}
    .nr-card-meta {{
      display: flex;
      align-items: center;
      gap: 8px;
      font-family: var(--font-ui);
      font-size: 11px;
      color: var(--text-muted);
    }}
    .nr-card-source {{
      font-weight: 600;
      color: var(--primary);
    }}
    .nr-card-importance {{
      padding: 1px 6px;
      border-radius: 4px;
      font-size: 10px;
      font-weight: 700;
    }}
    .imp-P1 {{ background: #fee; color: var(--accent); }}
    .imp-P2 {{ background: #fef5e7; color: #e67e22; }}
    .imp-P3 {{ background: #f0f8f0; color: #27ae60; }}
    .nr-card-title {{
      font-size: 15px;
      font-weight: 700;
      font-family: var(--font-ui);
      line-height: 1.4;
      color: var(--text);
    }}
    .nr-card-summary {{
      font-size: 13px;
      color: var(--text-muted);
      line-height: 1.6;
      font-family: var(--font-ui);
      display: -webkit-box;
      -webkit-line-clamp: 4;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }}
    .nr-card-tags {{
      display: flex;
      flex-wrap: wrap;
      gap: 4px;
      margin-top: 2px;
    }}
    .nr-card-tag {{
      font-size: 10px;
      font-family: var(--font-ui);
      color: var(--text-muted);
      background: var(--tag-bg);
      padding: 1px 7px;
      border-radius: 10px;
      border: 1px solid var(--border);
    }}

    /* ── 空状态 ── */
    .nr-empty {{
      max-width: 1100px;
      margin: 60px auto;
      text-align: center;
      font-family: var(--font-ui);
      color: var(--text-muted);
      display: none;
    }}
    .nr-empty.show {{ display: block; }}

    /* ── Modal ── */
    .modal-overlay {{
      display: none;
      position: fixed;
      inset: 0;
      background: rgba(0,0,0,0.55);
      z-index: 1000;
      align-items: center;
      justify-content: center;
      padding: 20px;
    }}
    .modal-overlay.open {{ display: flex; }}
    .modal-box {{
      background: #fff;
      border-radius: 10px;
      max-width: 680px;
      width: 100%;
      max-height: 85vh;
      overflow-y: auto;
      box-shadow: 0 20px 60px rgba(0,0,0,0.3);
    }}
    .modal-header {{
      padding: 20px 24px 16px;
      border-bottom: 1px solid var(--border);
      position: sticky;
      top: 0;
      background: #fff;
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 12px;
    }}
    .modal-title {{
      font-size: 17px;
      font-weight: 700;
      font-family: var(--font-ui);
      line-height: 1.4;
      color: var(--text);
    }}
    .modal-close {{
      background: none;
      border: none;
      font-size: 22px;
      cursor: pointer;
      color: #999;
      line-height: 1;
      flex-shrink: 0;
      padding: 0;
    }}
    .modal-close:hover {{ color: var(--accent); }}
    .modal-body {{
      padding: 20px 24px 24px;
    }}
    .modal-meta {{
      font-family: var(--font-ui);
      font-size: 12px;
      color: var(--text-muted);
      margin-bottom: 14px;
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
    }}
    .modal-summary {{
      font-size: 15px;
      line-height: 1.75;
      font-family: var(--font-ui);
      color: var(--text);
      margin-bottom: 16px;
    }}
    .modal-desc {{
      font-size: 13px;
      line-height: 1.65;
      color: var(--text-muted);
      font-family: var(--font-ui);
      border-top: 1px solid var(--border);
      padding-top: 14px;
      margin-bottom: 16px;
    }}
    .modal-tags {{
      display: flex;
      flex-wrap: wrap;
      gap: 5px;
      margin-bottom: 18px;
    }}
    .modal-tag {{
      font-size: 11px;
      font-family: var(--font-ui);
      color: var(--text-muted);
      background: var(--tag-bg);
      padding: 2px 9px;
      border-radius: 12px;
      border: 1px solid var(--border);
    }}
    .modal-link {{
      display: inline-block;
      padding: 9px 20px;
      background: var(--primary);
      color: #fff;
      text-decoration: none;
      border-radius: 6px;
      font-family: var(--font-ui);
      font-size: 13px;
      font-weight: 600;
      transition: background .2s;
    }}
    .modal-link:hover {{ background: #003d9e; }}

    @media (max-width: 600px) {{
      .nr-grid {{ grid-template-columns: 1fr; padding: 12px 12px 40px; }}
      .nr-header-inner {{ flex-direction: column; align-items: flex-start; }}
      .nr-meta {{ text-align: left; }}
    }}
  </style>
</head>
<body>

<div class="nr-header">
  <div class="nr-header-inner">
    <div class="nr-title-block">
      <div class="kicker">Thailand10 · 泰兰德10:00</div>
      <h1>📋 News Room — 新闻看板</h1>
    </div>
    <div class="nr-meta">
      共 <strong id="total-count">{total}</strong> 条新闻<br>
      更新于 {generated_at} BKK
    </div>
  </div>
</div>

<div class="nr-controls">
  <div class="nr-controls-inner">
    <div class="nr-search-row">
      <input class="nr-search" id="search-input" type="text" placeholder="搜索标题、摘要...（支持中英文）">
      <span class="nr-count">显示 <strong id="visible-count">{total}</strong> 条</span>
    </div>
    <div class="nr-sections" id="section-bar">
      <button class="sec-btn active" data-section="">全部</button>
    </div>
    <div class="nr-tags-wrap">
      <div class="nr-tags" id="tag-bar"></div>
      <button class="clear-btn" id="clear-tags" style="display:none">清除筛选</button>
    </div>
  </div>
</div>

<div class="nr-grid" id="news-grid"></div>
<div class="nr-empty" id="empty-msg">😶 没有符合条件的新闻</div>

<!-- Modal -->
<div class="modal-overlay" id="modal-overlay">
  <div class="modal-box">
    <div class="modal-header">
      <div class="modal-title" id="modal-title"></div>
      <button class="modal-close" id="modal-close">✕</button>
    </div>
    <div class="modal-body">
      <div class="modal-meta" id="modal-meta"></div>
      <div class="modal-summary" id="modal-summary"></div>
      <div class="modal-desc" id="modal-desc"></div>
      <div class="modal-tags" id="modal-tags"></div>
      <a class="modal-link" id="modal-link" href="#" target="_blank" rel="noopener">阅读原文 →</a>
    </div>
  </div>
</div>

<script>
const ALL_ITEMS = {items_json};
const SECTIONS  = {sections_json};
const TOP_TAGS  = {tags_json};

// ── 状态 ──
let activeSection = "";
let activeTags = new Set();
let searchQ = "";

// ── 初始化 Section 按钮 ──
const sectionBar = document.getElementById("section-bar");
SECTIONS.forEach(s => {{
  const btn = document.createElement("button");
  btn.className = "sec-btn";
  btn.dataset.section = s.id;
  btn.textContent = `${{s.label}} (${{s.count}})`;
  btn.onclick = () => {{
    activeSection = s.id;
    sectionBar.querySelectorAll(".sec-btn").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    render();
  }};
  sectionBar.appendChild(btn);
}});

// ── 初始化 Tag 按钮 ──
const tagBar = document.getElementById("tag-bar");
const clearTagsBtn = document.getElementById("clear-tags");
TOP_TAGS.forEach(t => {{
  const btn = document.createElement("button");
  btn.className = "tag-btn";
  btn.textContent = `${{t.tag}} ${{t.count}}`;
  btn.dataset.tag = t.tag;
  btn.onclick = () => {{
    if (activeTags.has(t.tag)) activeTags.delete(t.tag);
    else activeTags.add(t.tag);
    btn.classList.toggle("active", activeTags.has(t.tag));
    clearTagsBtn.style.display = activeTags.size ? "inline-block" : "none";
    render();
  }};
  tagBar.appendChild(btn);
}});
clearTagsBtn.onclick = () => {{
  activeTags.clear();
  tagBar.querySelectorAll(".tag-btn").forEach(b => b.classList.remove("active"));
  clearTagsBtn.style.display = "none";
  render();
}};

// ── 搜索 ──
document.getElementById("search-input").addEventListener("input", e => {{
  searchQ = e.target.value.trim().toLowerCase();
  render();
}});

// ── 过滤 ──
function filterItems() {{
  return ALL_ITEMS.filter(item => {{
    if (activeSection && (item.section_hint || "other") !== activeSection) return false;
    if (activeTags.size > 0) {{
      const itemTags = item.tags || [];
      if (![...activeTags].every(t => itemTags.includes(t))) return false;
    }}
    if (searchQ) {{
      const haystack = (item.title + " " + (item.summary_cn || "") + " " + (item.desc || "")).toLowerCase();
      if (!haystack.includes(searchQ)) return false;
    }}
    return true;
  }});
}}

// ── 格式化日期 ──
// 优先用能解析的标准日期，非标准格式（如 "4 days ago"）fallback 到 added_date 或原字符串
function fmtDate(d, fallback) {{
  if (!d) return fallback ? fmtDate(fallback) : "";
  try {{
    const dt = new Date(d);
    if (isNaN(dt.getTime())) {{
      // 非标准格式：尝试 fallback
      return fallback ? fmtDate(fallback) : d.slice(0, 10);
    }}
    return dt.toLocaleDateString("zh-CN", {{ month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }});
  }} catch(e) {{ return fallback ? fmtDate(fallback) : d.slice(0, 10); }}
}}

// ── 渲染 ──
function render() {{
  const items = filterItems();
  const grid = document.getElementById("news-grid");
  const emptyMsg = document.getElementById("empty-msg");
  document.getElementById("visible-count").textContent = items.length;

  grid.innerHTML = "";
  if (items.length === 0) {{
    emptyMsg.classList.add("show");
    return;
  }}
  emptyMsg.classList.remove("show");

  items.forEach(item => {{
    const card = document.createElement("div");
    card.className = "nr-card";
    const imp = item.importance || "";
    const tags = (item.tags || []).slice(0, 4).map(t =>
      `<span class="nr-card-tag">${{t}}</span>`).join("");
    card.innerHTML = `
      <div class="nr-card-meta">
        <span class="nr-card-source">${{item.source || ""}}</span>
        <span>${{fmtDate(item.date, item.added_date)}}</span>
        ${{imp ? `<span class="nr-card-importance imp-${{imp}}">${{imp}}</span>` : ""}}
      </div>
      <div class="nr-card-title">${{item.title || ""}}</div>
      <div class="nr-card-summary">${{item.summary_cn || item.desc || ""}}</div>
      ${{tags ? `<div class="nr-card-tags">${{tags}}</div>` : ""}}
    `;
    card.onclick = () => openModal(item);
    grid.appendChild(card);
  }});
}}

// ── Modal ──
function openModal(item) {{
  document.getElementById("modal-title").textContent = item.title || "";
  document.getElementById("modal-meta").innerHTML = `
    <span><strong>${{item.source || ""}}</strong></span>
    <span>${{fmtDate(item.date, item.added_date)}}</span>
    ${{item.section_hint ? `<span>板块：${{item.section_hint}}</span>` : ""}}
    ${{item.importance ? `<span>优先级：${{item.importance}}</span>` : ""}}
  `;
  document.getElementById("modal-summary").textContent = item.summary_cn || "";
  const descEl = document.getElementById("modal-desc");
  if (item.desc && item.desc !== item.desc_original) {{
    descEl.textContent = item.desc;
    descEl.style.display = "block";
  }} else if (item.desc_original) {{
    descEl.textContent = item.desc_original;
    descEl.style.display = "block";
  }} else {{
    descEl.style.display = "none";
  }}
  const tagsEl = document.getElementById("modal-tags");
  tagsEl.innerHTML = (item.tags || []).map(t =>
    `<span class="modal-tag">${{t}}</span>`).join("");
  const link = document.getElementById("modal-link");
  link.href = item.url || "#";
  link.style.display = item.url ? "inline-block" : "none";
  document.getElementById("modal-overlay").classList.add("open");
  document.body.style.overflow = "hidden";
}}

function closeModal() {{
  document.getElementById("modal-overlay").classList.remove("open");
  document.body.style.overflow = "";
}}

document.getElementById("modal-close").onclick = closeModal;
document.getElementById("modal-overlay").onclick = e => {{
  if (e.target === document.getElementById("modal-overlay")) closeModal();
}};
document.addEventListener("keydown", e => {{ if (e.key === "Escape") closeModal(); }});

// ── 启动 ──
render();
</script>
</body>
</html>"""

    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"✅ 生成完成：{OUT}（共 {total} 条新闻）")

if __name__ == "__main__":
    main()
