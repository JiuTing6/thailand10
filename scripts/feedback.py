#!/usr/bin/env python3
"""
feedback.py — Thailand10 用户反馈（👍/👎）消费逻辑

newsroom 卡片上的 👍/👎 投票经 Hostinger 端点回流，由 ingest_runner 在 filter 前
拉取写入 data/user_feedback.json。本模块把这些投票转成两个对 filter 的影响：

  ① build_feedback_examples(votes) — 软信号：拼一段「用户偏好」few-shot prompt 块，
     注入 filter 的 LLM prompt，引导对同类 👎 新闻压低评分、👍 新闻正常/优先保留。
  ② adjusted_thresholds(votes, ...) — 阈值微调：某 topic 净 👎（👎数−👍数）达阈值后，
     在该 topic 的入库门槛上叠加一个 bump（复用 filter 现有 TOPIC_THRESHOLDS 机制）。

两个函数都是纯函数（无 LLM、无 IO），便于单元测试。

user_feedback.json 形如：
  {"updated_at": "...", "votes": [
     {"id": "095e1130b1e4", "vote": "down", "title_cn": "...",
      "topic_tag": "#社会", "source": "Thairath", "ts": "2026-06-18T10:00:00Z"},
     ...
  ]}
端点已按 id 聚合「最新一票」，但本模块仍做防御性去重，乱序/重复输入也安全。
"""

import json
from pathlib import Path

# data/user_feedback.json（相对 repo 根）
DEFAULT_FEEDBACK_PATH = Path(__file__).resolve().parent.parent / "data" / "user_feedback.json"

# 每种态度最多注入多少条 few-shot 示例（控 token）
MAX_EXAMPLES_EACH = 8

# 阈值微调参数
NET_DOWN_K = 3        # 某 topic 净 👎 ≥ K 才触发抬高门槛
THRESHOLD_BUMP = 0.15  # 每触发抬高多少
THRESHOLD_CAP = 0.8    # 门槛封顶（避免某 topic 被彻底锁死）


def load_votes(path=DEFAULT_FEEDBACK_PATH) -> list:
    """读 user_feedback.json，返回 votes 列表；文件缺失/损坏则返回 []（零影响）。"""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []
    if isinstance(data, dict):
        votes = data.get("votes", [])
    elif isinstance(data, list):
        votes = data
    else:
        votes = []
    return [v for v in votes if isinstance(v, dict) and v.get("id")]


def _dedup_latest(votes: list) -> list:
    """按 id 保留 ts 最新的一票（防御端点已聚合的前提失效）。"""
    latest = {}
    for v in votes:
        vid = v.get("id")
        if not vid:
            continue
        prev = latest.get(vid)
        if prev is None or str(v.get("ts", "")) >= str(prev.get("ts", "")):
            latest[vid] = v
    return list(latest.values())


def build_feedback_examples(votes: list, max_each: int = MAX_EXAMPLES_EACH) -> str:
    """把 👍/👎 投票拼成一段「用户偏好」few-shot prompt 块。无有效投票返回 ""。

    选取策略：每种态度取最近 max_each 条（按 ts 倒序）。不按 topic 去重——同一被 👎
    主题下的多条不同子类型示例正是教 LLM 认「这一类」的关键，max_each 控 token 即可。
    """
    votes = _dedup_latest(votes)
    if not votes:
        return ""

    ordered = sorted(votes, key=lambda v: str(v.get("ts", "")), reverse=True)

    def pick(target_vote):
        picked = []
        for v in ordered:
            if v.get("vote") != target_vote:
                continue
            title = (v.get("title_cn") or "").strip()
            if not title:
                continue
            picked.append((v.get("topic_tag") or "", title))
            if len(picked) >= max_each:
                break
        return picked

    downs = pick("down")
    ups = pick("up")
    if not downs and not ups:
        return ""

    lines = ["## 用户反馈偏好（基于历史 👍/👎，据此微调评分）"]
    if downs:
        lines.append("用户**不关心**以下这类新闻，遇到**同类（同主题/同角度）**请压低 relevance_score（可低于入库门槛使其被过滤）：")
        for topic, title in downs:
            lines.append(f"- 👎 [{topic or '无标签'}] {title}")
    if ups:
        lines.append("用户**关心**以下这类新闻，遇到同类请正常评分或优先保留：")
        for topic, title in ups:
            lines.append(f"- 👍 [{topic or '无标签'}] {title}")
    lines.append(
        "注意：以上仅为偏好微调，**不得推翻**「纯全球新闻/非新闻一律丢弃」等硬规则；"
        "发展中的重要新闻（有新进展/数据/伤亡/重大政策/涉外国人）即便属被 👎 的主题也应保留。"
    )
    return "\n".join(lines)


def topic_net_down(votes: list) -> dict:
    """按 topic 统计净 👎 数（👎数 − 👍数）。"""
    votes = _dedup_latest(votes)
    net = {}
    for v in votes:
        topic = v.get("topic_tag")
        if not topic:
            continue
        vote = v.get("vote")
        if vote == "down":
            net[topic] = net.get(topic, 0) + 1
        elif vote == "up":
            net[topic] = net.get(topic, 0) - 1
    return net


def adjusted_thresholds(votes: list, base_thresholds: dict, default_threshold: float,
                        net_down_k: int = NET_DOWN_K, bump: float = THRESHOLD_BUMP,
                        cap: float = THRESHOLD_CAP) -> dict:
    """返回叠加了反馈微调后的 topic→门槛 字典。

    某 topic 净 👎 ≥ net_down_k → 在其基准门槛（base_thresholds 或 default）上 +bump，
    封顶 cap。只返回发生变化的 topic（filter 用 .get(topic, default) 兜底其余）。
    """
    result = dict(base_thresholds)
    net = topic_net_down(votes)
    for topic, n in net.items():
        if n >= net_down_k:
            current = base_thresholds.get(topic, default_threshold)
            result[topic] = round(min(cap, current + bump), 4)
    return result
