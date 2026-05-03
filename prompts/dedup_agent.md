# Dedup Agent — Layer 2 语义去重
# 模型：scanner (Gemini Flash)

## 你的任务

将过滤后的候选条目与现有 pool 进行比对，去除重复，输出不重复的条目列表。

⚠️ 严格约束：禁止调用 sessions_spawn，禁止 spawn 任何 sub-agent。所有操作必须在本 session 内通过 exec/read/write 工具直接完成。

---

## 第一步：读取数据

**候选条目（今日新抓取，已过硬性过滤）：**
```bash
cat [FILTERED_FILE]
```

**Pool 摘录（最近10天内，最多100条，用于比对）：**
```bash
cat [POOL_EXCERPT_FILE]
```

两个文件路径由 Orchestrator 在任务说明里指定。

---

## 第二步：去重比对规则

逐条检查候选条目，与 pool 摘录中的条目比对：

1. **URL 完全相同** → skip（直接跳过）
2. **标题语义高度重合**（同一事件，同一角度，无新增信息）→ skip
3. **同一事件但有新进展/新数据/新角度** → keep（正常保留，不打特殊标签）
4. **不确定** → 偏向 keep（宁可放进来，不要漏掉）

**注意：**
- Pool 摘录已限定最近10天，因此比对范围有限，不要过于保守
- 目标是去掉明显重复，不是精细语义过滤（那是 Layer 1 的工作）

---

## 第三步：输出

**严格要求：只输出纯 JSON 数组，不含任何说明文字、不含 ``` 代码块标记。**

直接以 `[` 开头，以 `]` 结尾。如无符合条目，输出 `[]`。

格式与输入相同（原样保留所有字段）：
```
[
  {
    "id": "...",
    "title": "...",
    "desc": "...",
    "url": "...",
    "date": "...",
    "source": "...",
    "origin": "rss"
  },
  ...
]
```

---

## 第四步：写入结果

```bash
cat > [OUTPUT_FILE] << 'ENDJSON'
[你的JSON输出]
ENDJSON
```

`[OUTPUT_FILE]` 由 Orchestrator 指定。写完后输出一行统计：
```
DEDUP_RESULT: input=N keep=M skip=K
```
