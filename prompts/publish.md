# Thailand10 Publish Cron 任务提示词
# 每周四 09:30 BKK 触发，负责从内容池选编并发布

## 你的任务
从候选新闻中做编辑选题，输出选题 JSON，然后由 Python 脚本完成正文拼装、HTML 生成和发布。
**不抓取新闻，不调用 web_search。**

## 工作目录
`/Users/Ade/Projects/Thailand10/`

---

## 执行步骤

### 第1步：确定期数和日期
- 读取 `thailand10/index.html`，数一下现有归档条目数，+1 即为本期期号
- 今天日期即为本期日期（格式：YYYY-MM-DD）

### 第2步：生成候选列表
运行筛选脚本，只取过去7天的条目（精简字段版，供选题使用）：
```bash
cd /Users/Ade/Projects/Thailand10
python3 scripts/7days_filter_pool.py
```
输出文件：`data/7days_news_MM-DD-YYYY.json`（注意文件名格式为 MM-DD-YYYY）
读取该文件作为选题原料。**不要直接读 news_pool.json。**

### 第3步：读取主编反馈
- `data/editorial_feedback.md` → **必读**，将历史教训内化为编辑判断

### 第4步：编辑选题（核心工作）

**可用原料 = 第2步输出的 7days_news 文件中的全部条目**

每条已有：`id`、`title_cn`、`summary_cn`、`importance`、`relevance_score`、`section_hint`、`topic_tag`、`city_tag`、`source`、`url`、`added_date`

**选题三原则（按优先级严格执行）：**
1. **重要性优先：** 以新闻本身的重要性、时效性和影响力为核心，编辑判断第一
2. **原料限定：** 只能从候选列表选，不得自行 web_search 补充
3. **板块关联度：** 重要性相近时，以板块相关性决定归属

**版块配额（全部动态，无硬性下限）：**
- 📡 政经动态（`thailand`）：无上限，兜底板块
- 🏠 房地产（`property`）：有则收，无则0
- 🛺 曼谷（`bangkok`）：**严格只收曼谷本地新闻**，section_hint=bangkok 的条目
- 🌅 芭提雅（`pattaya`）：有则收，聚焦北芭/Na Kluea/Wong Amat/Phra Tamnak
- 🏝️ 苏梅岛（`samui`）：有则收，聚焦 Koh Samui / Koh Phangan / Surat Thani 区域
- 🚅 中泰（`cn_thai`）：触发式，无重磅直接省略

**每期发布量：**
- **软性参考值：** 25条，新闻密集期可突破
- 窗口内原料不足时，有多少发多少，不强行凑数

**新闻重要性分级：**
- P1：影响外国人的政策/签证/安全、重大突发事件 → 必收
- P2：政治重大变化、AI泰国相关（#AI基建 #AI应用）、具体楼盘动态（#新楼盘）、本地有料奇闻（#本地奇闻）→ 优先
- P3：旅游促销、社会犯罪、品牌活动 → 版面宽裕时收录，作为节奏调剂

**每期频率控制（编辑节奏）：**
- `#经济数据`（GDP/泰铢汇率/通胀/利率）：每期最多 **1条**，除非数据异常或政策重大转向
- `#楼市大盘`（整体市场趋势报告）：每期最多 **1条**，优先选 `#新楼盘` 具体项目替代
- `#政治`（组阁/党派例行进展）：每期最多 **2条**，无实质变化不选
- `#AI基建` `#AI应用`：主动寻找，有则必收，读者关注度高
- `#本地奇闻`：每期 **1-2条** 作为节奏调剂，避免全篇都是硬新闻

### 第5步：输出选题 JSON

将选题结果写入 `data/selected_YYYY-MM-DD.json`（仅包含 id 列表，不含正文）：

```json
{
  "date": "YYYY-MM-DD",
  "issue": N,
  "highlights": [2, 0, 8, 13, 5],
  "sections": {
    "thailand": ["id1", "id2", "id3", ...],
    "property": ["id4"],
    "bangkok":  ["id5", "id6"],
    "pattaya":  ["id7"],
    "samui":    [],
    "cn_thai":  []
  }
}
```

**highlights 说明：** 从所有选中条目中，按全局编号顺序（thailand[0]=0, thailand[1]=1, ...），选5条最重要的，填入 highlights 列表。

**生成后验证 JSON：**
```bash
python3 -c "import json; json.load(open('data/selected_YYYY-MM-DD.json')); print('JSON OK')"
```

### 第6步：Python 拼装 + 构建 HTML

```bash
cd /Users/Ade/Projects/Thailand10

# 拼装 issue JSON（body = summary_cn，纯 Python，无 LLM）
python3 scripts/build_issue.py data/selected_YYYY-MM-DD.json

# 验证
python3 -c "import json; json.load(open('data/issues/YYYY-MM-DD.json')); print('issue JSON OK')"

# 生成 HTML
python3 scripts/build_html.py data/issues/YYYY-MM-DD.json
```

### 第7步：归档到发布历史

将本期所有发布条目追加写入 `data/published_history_thai10.json`：
```json
{"title": "...", "date": "YYYY-MM-DD", "issue": N}
```

### 第8步：推送到 GitHub
```bash
cd /Users/Ade/Projects/Thailand10
git add -A
git commit -m "🗞️ Thailand10 第N期 YYYY-MM-DD"
git push origin main
```

### 第9步：通知 Ade
使用 `message` 工具发送 Telegram 消息（**必须用 message 工具 + channel:telegram + to:"818033361"，不是 webchat**）：

```
🗞️ 泰兰德10:00 第N期已发布

📅 YYYY年MM月DD日 周X
📊 本期精选 XX 条新闻

🔗 https://jiuting6.github.io/thailand10/thailand10/YYYY-MM-DD-0NN.html

【速览】
· [最重要的1-2条标题]
· [第二重要的标题]
```

---

## 注意事项
- **⚠️ 不得调用 web_search**，所有选编原料只能来自 7days_news 文件
- **⚠️ 不要读 news_pool.json**，太大，用 7days_filter_pool.py 的输出
- 窗口内无条目则跳过本次发布，输出错误提示
- GitHub Pages URL格式：`https://jiuting6.github.io/thailand10/...`
- 空板块不显示，不为填充板块降低编辑标准
