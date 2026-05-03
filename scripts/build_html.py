#!/usr/bin/env python3
"""
Thailand10 HTML 生成器
用法：python3 build_html.py data/issues/YYYY-MM-DD.json
输出：HTML文件写入 thailand10/YYYY-MM-DD.html
      同时更新 thailand10/index.html 归档列表
注意：issue JSON 永久保存于 data/issues/，raw RSS 保存于 data/issues/YYYY-MM-DD-raw.json
"""

import json
import sys
import os
import subprocess
from datetime import datetime

WEEKDAYS_ZH = ["周一","周二","周三","周四","周五","周六","周日"]

SECTIONS = [
    {"id":"thailand",  "icon":"📡", "cn":"政经动态",    "en":"Politics & Economy","cls":"thai"},
    {"id":"property",  "icon":"🏠", "cn":"房地产",      "en":"Property",          "cls":"property"},
    {"id":"bangkok",   "icon":"🛺", "cn":"曼谷",        "en":"Bangkok",           "cls":"bkk"},
    {"id":"pattaya",   "icon":"🌅", "cn":"芭提雅",      "en":"Pattaya",           "cls":"pattaya"},
    {"id":"samui",     "icon":"🏝️", "cn":"苏梅岛",      "en":"Koh Samui",         "cls":"samui"},
    {"id":"cn_thai",   "icon":"🚅", "cn":"中泰",        "en":"China-Thailand",    "cls":"cn"},
]

def tag_html(tag_text, tag_type="normal"):
    cls = {"tracking":"tracking","urgent":"urgent","china":"china"}.get(tag_type,"")
    return f'<span class="tag {cls}">{tag_text}</span>'

def article_html(a, idx):
    inline_tags = ""
    for t in a.get("tags", []):
        ttype = "normal"
        if "🔄" in t: ttype = "tracking"
        if "⚠️" in t: ttype = "urgent"
        inline_tags += tag_html(t, ttype)

    # 编辑点评已禁用（2026-03-16）：token浪费，读者用处不大
    # comment_html = ""
    # if a.get("comment"):
    #     comment_html = f'<div class="article-comment">{a["comment"]}</div>'
    comment_html = ""  # 始终为空，comment 字段保留在 JSON 中但不渲染

    date_str = a.get("date","")
    source   = a.get("source","")
    url      = a.get("url","#")

    article_id = f"a{idx}"
    return f'''
    <div class="article-item" id="{article_id}">
      <div class="article-title">{a["title"]}</div>
      <div class="article-body">{a["body"]}</div>
      {comment_html}
      <div class="article-source">
        <span class="source-left"><span>📅 {date_str}</span><span class="source-dot">·</span>{inline_tags}</span>
        <span class="source-right"><span>来源：{source}</span><span class="source-dot">·</span><a href="{url}" target="_blank" rel="noopener">→ 阅读原文</a></span>
      </div>
      <!-- feedback disabled
      <div class="article-feedback" data-id="{article_id}">
        <button class="fb-btn fb-up" onclick="handleFeedback(this, '{article_id}', 'up')">👍🏻</button>
        <button class="fb-btn fb-down" onclick="handleFeedback(this, '{article_id}', 'down')">👎🏻</button>
      </div>
      -->
    </div>'''

def section_html(section, articles, start_idx=0):
    if not articles:
        return ""
    items_html = "\n".join(article_html(a, start_idx + i) for i, a in enumerate(articles))
    count = len(articles)
    return f'''
  <div class="section">
    <div class="section-header {section['cls']}">
      <span class="section-icon">{section['icon']}</span>
      <span class="section-title-cn">{section['cn']}</span>
      <span class="section-count">({count}条)</span>
      <span class="section-title-en">{section['en']}</span>
    </div>
    <div class="article-list">
      {items_html}
    </div>
  </div>'''

def highlights_html(all_articles, selected_indices=None, n=5):
    """
    生成本期要闻高亮。
    selected_indices: sub-agent 在 JSON 的 highlights 字段指定的全局文章序号列表
    fallback: 若未指定，取前 n 条
    """
    if selected_indices:
        idx_set = {i for i in selected_indices}
        top = [(idx, a) for idx, a in all_articles if idx in idx_set]
        top = sorted(top, key=lambda x: x[0])[:n]  # 按文章顺序升序排
    else:
        top = all_articles[:n]
    if not top:
        return ""
    items = "\n".join(
        f'<a class="hl-item" href="#a{idx}">'
        f'<span class="hl-num">▸</span>'
        f'<span class="hl-title">{a["title"]}</span>'
        f'</a>'
        for idx, a in top
    )
    return f'''
  <div class="highlights">
    <div class="hl-label">本期要闻 | Highlights</div>
    {items}
  </div>'''

def build_issue(issue_data, output_dir):
    date_str  = issue_data["date"]
    issue_num = issue_data.get("issue", "")
    dt        = datetime.strptime(date_str, "%Y-%m-%d")
    weekday   = WEEKDAYS_ZH[dt.weekday()]
    total     = sum(len(issue_data["sections"].get(s["id"],[]))
                    for s in SECTIONS)

    # CSS 版本号（git hash 前8位，每次 CSS 变更自动 busting 缓存）
    try:
        css_ver = subprocess.check_output(
            ["git", "log", "-1", "--format=%h", "--", "assets/style-thailand10.css"],
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            text=True
        ).strip() or date_str
    except Exception:
        css_ver = date_str

    # 全局文章列表（带全局idx），用于高亮区和唯一 anchor
    all_articles = []
    for sec in SECTIONS:
        for a in issue_data["sections"].get(sec["id"], []):
            all_articles.append((len(all_articles), a))

    sections_html = ""
    global_idx = 0
    for sec in SECTIONS:
        arts = issue_data["sections"].get(sec["id"], [])
        sections_html += section_html(sec, arts, start_idx=global_idx)
        global_idx += len(arts)

    selected = issue_data.get("highlights", None)  # sub-agent 指定的全局序号列表
    hl_html = highlights_html(all_articles, selected_indices=selected, n=5)

    # 上下期导航（简单，由归档index处理）
    html = f'''<!DOCTYPE html>
<html lang="zh">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>泰兰德10:00 | {date_str} {weekday}</title>
  <link rel="stylesheet" href="../assets/style-thailand10.css?v={css_ver}">
</head>
<body>

<header class="site-header">
  <div class="header-inner">
    <div class="header-kicker">Thailand 10:00 &nbsp;·&nbsp; 第 {issue_num} 期</div>
    <div class="header-title">🇹🇭 泰兰德<span class="red">10:00</span></div>
    <div class="header-meta">
      <strong>{date_str} &nbsp;{weekday}</strong>
      <span>共 {total} 条精选新闻</span>
    </div>
  </div>
</header>

{hl_html}

<main class="main-content">
  {sections_html}
</main>

<footer class="site-footer">
  <div class="footer-nav">
    <a href="index.html">← 归档列表</a>
    <a href="../index.html">首页</a>
    <a href="../moments/index.html">素坤逸拾光</a>
  </div>
  <div>Bangkok News Hub · 泰兰德10:00 · {date_str}</div>
</footer>

<script>
(function() {{
  const KEY = 'thailand10_feedback';
  function loadFeedback() {{
    try {{ return JSON.parse(localStorage.getItem(KEY) || '{{}}'); }} catch(e) {{ return {{}}; }}
  }}
  function saveFeedback(data) {{
    localStorage.setItem(KEY, JSON.stringify(data));
  }}
  function applyState(id, vote) {{
    const item = document.getElementById(id);
    if (!item) return;
    const upBtn   = item.querySelector('.fb-up');
    const downBtn = item.querySelector('.fb-down');
    upBtn.classList.toggle('active', vote === 'up');
    downBtn.classList.toggle('active', vote === 'down');
  }}
  // 页面加载时恢复状态
  const fb = loadFeedback();
  document.querySelectorAll('.article-feedback').forEach(function(el) {{
    const id = el.dataset.id;
    if (fb[id]) applyState(id, fb[id]);
  }});
  // 全局点击处理
  window.handleFeedback = function(btn, id, vote) {{
    const fb = loadFeedback();
    if (fb[id] === vote) {{
      delete fb[id];  // 再次点击取消
    }} else {{
      fb[id] = vote;
    }}
    saveFeedback(fb);
    applyState(id, fb[id] || null);
  }};
}})();
</script>

</body>
</html>'''

    filename = f"{date_str}-{issue_num:03d}.html" if isinstance(issue_num, int) else f"{date_str}-{issue_num}.html"
    filepath = os.path.join(output_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[OK] 生成: {filepath} ({total}条)")
    return filename, date_str, total, weekday

def update_archive(output_dir, filename, date_str, total, weekday):
    index_path = os.path.join(output_dir, "index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 去重：同一文件名已存在则跳过
    if f'href="{filename}"' in content:
        print(f"[SKIP] 归档已存在: {filename}")
        return

    new_entry = f'''    <div class="archive-item">
      <a href="{filename}">🇹🇭 {date_str} {weekday}</a>
      <span class="archive-date">{date_str}</span>
      <span class="archive-count">{total}条</span>
    </div>'''

    marker = "<!-- 归档条目由脚本自动插入 -->\n  <div id=\"archive-entries\">"
    replacement = f'{marker}\n{new_entry}'
    content = content.replace(marker, replacement)

    # 移除"即将发布"占位符
    content = content.replace(
        '\n    <div style="color:#bbb; font-family:var(--font-ui); font-size:14px; padding:40px 0; text-align:center;">\n      第一期即将发布...\n    </div>', ''
    )

    with open(index_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[OK] 归档更新: {filename}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 build_html.py <issue.json>")
        sys.exit(1)

    with open(sys.argv[1], "r", encoding="utf-8") as f:
        issue_data = json.load(f)

    base_dir   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    output_dir = os.path.join(base_dir, "thailand10")

    filename, date_str, total, weekday = build_issue(issue_data, output_dir)
    update_archive(output_dir, filename, date_str, total, weekday)
