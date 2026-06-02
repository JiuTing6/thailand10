#!/usr/bin/env python3
"""
dedup.py — Thailand10 Layer 2: 语义去重

Usage:
  python3 dedup.py --input <filtered.json> --pool <pool-excerpt.json> --output <deduped.json>

两阶段去重：
  阶段1（当天候选互比）：LLM 单次全量聚类"同事件+同角度+零新信息"的候选，
                        Python 按 SOURCE_PRIORITY 确定性地每组选 1 个幸存者。
  阶段2（幸存者 vs pool）：跨天去重，强化"发展中报道=keep"防错杀，pool 窗口放大。

All non-duplicate items pass through. Topic quota control is handled at publish time.
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from claude_call import call_claude, ClaudeCallError


# ── Config ──────────────────────────────────────────────────────────────────

MODEL = "claude-haiku-4-5"
BATCH_SIZE = 10  # 阶段2 vs-pool 的切批大小

# 源优先级 tie-break（确定性，可复现，零额外 token）。
# 撞车留谁：LLM 只负责聚类"同事件"，留谁由这张表 + 正文长度/有图兜底决定。
# 默认顺序：中文原生无翻译损耗者优先。
DEFAULT_PRIORITY = ["泰国头条新闻", "The Thaiger", "Bangkok Post", "Thairath", "Pattaya Mail"]

# 按主题翻转优先级（贴近各源在该领域的报道强项）。
TOPIC_PRIORITY = {
    "#中泰": ["泰国头条新闻", "Bangkok Post", "The Thaiger", "Thairath", "Pattaya Mail"],
    "#治安": ["Pattaya Mail", "The Thaiger", "Bangkok Post", "泰国头条新闻", "Thairath"],  # 芭提雅治安 Pattaya Mail 最强
    "#旅居": ["The Thaiger", "Pattaya Mail", "Bangkok Post", "泰国头条新闻", "Thairath"],
    "#经济": ["Bangkok Post", "泰国头条新闻", "Thairath", "The Thaiger", "Pattaya Mail"],
    "#时政": ["Bangkok Post", "泰国头条新闻", "Thairath", "The Thaiger", "Pattaya Mail"],
    "#社会": ["Thairath", "泰国头条新闻", "Bangkok Post", "The Thaiger", "Pattaya Mail"],
}


# ── 阶段1：当天候选互比（聚类 + 确定性选幸存者）─────────────────────────────

CLUSTER_SYSTEM_PROMPT = """你是新闻聚类器。给定当天一批候选新闻（多来源、可能跨中泰英语言），\
把"报道的是同一个具体事件、且角度相同、彼此之间没有新增信息"的条目归为同一组。

## 聚类标准（务必从严，宁可不归组也别错杀）
- 归为一组的条件：**同一具体事件** AND **同一报道角度** AND **互相之间零新增信息**
- 以下情况【不要】归组（视为不同条目，各自保留）：
  1. 同一话题但不同事件（如两起不同的命案、两个不同候选人的竞选）
  2. 同一事件但不同角度/侧重（如政策"正式启动" vs "使用指南" vs "首日效果" vs "覆盖人数"——这是四个角度，全部保留）
  3. 任一条带有别条没有的新进展、新数据、新表态、新涉事方
- 判断主要看 title + desc 描述的"是不是同一件事、同一个切入点"，不要被来源不同迷惑。

## 输出要求
只输出分组结果，**只用 id**。格式：
{"clusters": [["id1","id2"], ["id3","id4","id5"]]}
- clusters 里只放"确实重复、应只留一条"的组，每组 >=2 个 id。
- 不重复的条目（singleton）不要出现在输出里。
- 无代码块标记，无说明文字。
"""


def call_cluster(candidates: list) -> list:
    """单次全量调 Haiku，返回 cluster 列表（每个 cluster 是同事件 id 列表）。"""
    slim = [
        {
            "id": c.get("id", ""),
            "title": c.get("title", ""),
            "desc": (c.get("desc", "") or "")[:200],
            "topic": c.get("topic_tag", ""),
        }
        for c in candidates
    ]
    user_prompt = (
        f"## 当天候选条目（共 {len(slim)} 条，请聚类同事件同角度的重复项）\n"
        + json.dumps(slim, ensure_ascii=False)
        + '\n\n返回分组（JSON，字段名 clusters）：'
    )
    full_prompt = CLUSTER_SYSTEM_PROMPT + "\n\n" + user_prompt
    parsed = call_claude(full_prompt, model=MODEL, expect_json=True, timeout=180)

    if isinstance(parsed, dict):
        clusters = parsed.get("clusters", [])
    elif isinstance(parsed, list):
        clusters = parsed
    else:
        clusters = []

    # 只保留 >=2 且 id 合法的组
    valid_ids = {c.get("id") for c in candidates}
    out = []
    for cl in clusters:
        ids = [i for i in cl if i in valid_ids]
        if len(ids) >= 2:
            out.append(ids)
    return out


def pick_survivor(group: list) -> dict:
    """在一个同事件 cluster 里按确定性规则选 1 个幸存者。

    规则：SOURCE_PRIORITY[topic] 源优先级 → desc 长者胜 → 有 image 者胜 → id 字典序（保底确定性）。
    """
    topic = group[0].get("topic_tag", "")
    priority = TOPIC_PRIORITY.get(topic, DEFAULT_PRIORITY)

    def rank(item):
        src = item.get("source", "")
        src_rank = priority.index(src) if src in priority else len(priority)
        desc_len = len(item.get("desc", "") or "")
        has_img = 1 if item.get("image") else 0
        # 元组排序：源优先级升序(小=优先) → desc长降序 → 有图降序 → id 升序
        return (src_rank, -desc_len, -has_img, item.get("id", ""))

    return sorted(group, key=rank)[0]


def stage1_intraday(candidates: list) -> list:
    """阶段1：当天候选互比，返回去掉当天重复后的幸存者列表（保持原序）。"""
    if len(candidates) < 2:
        return candidates

    by_id = {c.get("id"): c for c in candidates}
    print(f"🔎 阶段1 当天互比：{len(candidates)} 条候选聚类中...", flush=True)
    clusters = call_cluster(candidates)

    dropped = set()
    for ids in clusters:
        group = [by_id[i] for i in ids if i in by_id]
        survivor = pick_survivor(group)
        for it in group:
            if it.get("id") != survivor.get("id"):
                dropped.add(it.get("id"))
        survivors_title = (survivor.get("title", "") or "")[:40]
        print(f"   • 同事件 {len(group)} 条 → 留 [{survivor.get('source')}] {survivors_title}")

    kept = [c for c in candidates if c.get("id") not in dropped]
    print(f"✅ 阶段1：{len(candidates)} → {len(kept)}（当天 collapse 掉 {len(dropped)} 条）")
    return kept


# ── 阶段2：幸存者 vs pool（跨天去重，防错杀）────────────────────────────────

POOL_SYSTEM_PROMPT = """你是新闻去重过滤器。给定一批候选新闻和现有 pool（最近若干天已收录），\
判断候选是否与 pool 里【已有的某条】重复，返回不重复的候选。

## 去重规则（按优先级）
1. URL 完全相同 → skip
2. 与 pool 某条是同一事件、同一角度、且无任何新信息 → skip
3. 其余一律 keep。特别地：
   - 多日反复报道是【重要信号】，说明事件在发展——只要候选带有新进展/新数据/新表态/新涉事方/新结果，一律 keep
   - 不确定 → keep（宁放勿漏）

## 注意
- 只做跨天明显重复的剔除，不是精细语义过滤，更不要因"话题相似"就误杀发展中的报道。

## 输出要求
**只输出每条 keep 候选的 id 字段**（不要回显 title/desc/url）。
格式：{"items": [{"id": "..."}, ...]}
只含 keep 的候选；丢弃的不出现。无代码块标记，无说明文字。
"""


def call_pool_dedup(candidates: list, pool_excerpt: list) -> list:
    """对一批候选 + pool 上下文调 Haiku，返回保留的 id 引用列表。"""
    user_prompt = (
        f"## 现有 Pool（最近若干天，共 {len(pool_excerpt)} 条）\n"
        + json.dumps(pool_excerpt, ensure_ascii=False)
        + f"\n\n## 候选条目（共 {len(candidates)} 条，请判断是否与 pool 重复）\n"
        + json.dumps(candidates, ensure_ascii=False)
        + "\n\n返回不重复的候选（JSON，字段名 items）："
    )
    full_prompt = POOL_SYSTEM_PROMPT + "\n\n" + user_prompt
    parsed = call_claude(full_prompt, model=MODEL, expect_json=True, timeout=180)

    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict):
        if "items" in parsed:
            return parsed["items"]
        for v in parsed.values():
            if isinstance(v, list):
                return v
    sys.exit(f"❌ Unexpected response shape: {type(parsed).__name__} {str(parsed)[:200]}")


def stage2_vs_pool(candidates: list, pool_slim: list, batch_size: int) -> list:
    """阶段2：幸存者 vs pool，按 batch 切批跨天去重。"""
    results = []
    batches = [candidates[i:i + batch_size] for i in range(0, len(candidates), batch_size)]
    for i, batch in enumerate(batches, 1):
        print(f"🔄 阶段2 Batch {i}/{len(batches)} ({len(batch)} 候选 vs {len(pool_slim)} pool)...",
              end=" ", flush=True)
        try:
            kept_refs = call_pool_dedup(batch, pool_slim)
        except ClaudeCallError as e:
            sys.exit(f"❌ Dedup API failed on batch {i}: {e}")
        batch_by_id = {it["id"]: it for it in batch}
        kept = []
        for ref in kept_refs:
            kid = ref.get("id") if isinstance(ref, dict) else None
            if kid and kid in batch_by_id:
                kept.append(batch_by_id[kid])
        print(f"✅ kept {len(kept)}/{len(batch)}")
        results.extend(kept)
        time.sleep(1)
    return results


# ── main ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Path to filtered JSON (candidates)")
    parser.add_argument("--pool", required=True, help="Path to pool excerpt JSON")
    parser.add_argument("--output", required=True, help="Path to write deduped JSON")
    parser.add_argument("--batch", type=int, default=BATCH_SIZE, help="阶段2 每批候选数")
    args = parser.parse_args()

    with open(args.input) as f:
        candidates = json.load(f)
    with open(args.pool) as f:
        pool_excerpt = json.load(f)

    total_input = len(candidates)
    print(f"📥 Loaded {total_input} candidates, {len(pool_excerpt)} pool items")

    # 阶段1：当天候选互比
    candidates = stage1_intraday(candidates)

    # 阶段2：幸存者 vs pool（只传 id/title/url 省 token）
    pool_slim = [
        {"id": x.get("id", ""), "title": x.get("title_cn") or x.get("title", ""), "url": x.get("url", "")}
        for x in pool_excerpt
    ]
    results = stage2_vs_pool(candidates, pool_slim, args.batch)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    kept_count = len(results)
    skip_count = total_input - kept_count
    print(f"✅ Written {kept_count} items to {args.output}")
    print(f"DEDUP_RESULT: input={total_input} keep={kept_count} skip={skip_count}")


if __name__ == "__main__":
    main()
