"""规则匹配打分器：确定性、零成本、可解释

每条岗位输出 (score, reasons)，reasons 记录每个加分/扣分来源，
保证推荐结果可解释、可复现（同一份数据两次运行结果完全一致）。
LLM 精排只作用于这里产出的 Top 候选，不替代规则层。
"""
import json
import os
from datetime import date

BASE = os.path.dirname(os.path.abspath(__file__))


def load_config():
    with open(os.path.join(BASE, "config.json"), encoding="utf-8") as f:
        return json.load(f)


def _kw_score(text, keywords):
    """text 中命中关键词表，返回 (得分, 命中的词列表)。"""
    score, hits = 0, []
    for kw, w in keywords.items():
        if kw.lower() in text:
            score += w
            hits.append(kw)
    return score, hits


def score_job(job, cfg, today=None):
    """对单条岗位打分，返回 (score, reasons列表, 是否过期)。"""
    today = today or date.today()
    text = " ".join(str(job.get(k, "")) for k in ("title", "company", "note", "tab")).lower()
    score, reasons = 0, []

    # 1. 目标方向关键词（权重最高）
    s, hits = _kw_score(text, cfg["target_keywords"])
    if s:
        score += s
        reasons.append(f"方向匹配[{','.join(hits)}] +{s}")

    # 2. 负面关键词（不想去的岗位类型）
    s, hits = _kw_score(text, cfg["negative_keywords"])
    if s:
        score += s
        reasons.append(f"方向排除[{','.join(hits)}] {s}")

    # 3. 城市匹配（city_tags 优先，其次 city 原文）
    cities = [str(c) for c in job.get("city_tags", [])] or [str(job.get("city", ""))]
    city_text = " ".join(cities)
    if any(c in city_text for c in cfg["prefer_cities"]):
        score += 15
        reasons.append("首选城市 +15")
    elif any(c in city_text for c in cfg["ok_cities"]):
        score += 4
        reasons.append("可接受城市 +4")

    # 4. 行业权重
    ind = job.get("industry", "")
    w = cfg["industry_weights"].get(ind, 0)
    if w:
        score += w
        reasons.append(f"行业[{ind}] {'+' if w > 0 else ''}{w}")

    # 5. 加成项：内推码 / 免笔试 / 截止临近
    if str(job.get("ref_code", "")).strip():
        score += cfg["bonus"]["has_ref_code"]
        reasons.append(f"有内推码 +{cfg['bonus']['has_ref_code']}")
    if str(job.get("free_exam", "")).strip() == "是":
        score += cfg["bonus"]["free_exam"]
        reasons.append(f"免笔试 +{cfg['bonus']['free_exam']}")

    # 6. 截止时间：过期直接淘汰；7 天内截止加分提醒
    expired = False
    dl = str(job.get("deadline", "")).strip()
    if dl:
        try:
            d = date.fromisoformat(dl[:10])
            if d < today:
                expired = True
            elif (d - today).days <= 7:
                score += cfg["bonus"]["deadline_within_7d"]
                reasons.append(f"{(d - today).days}天后截止 +{cfg['bonus']['deadline_within_7d']}")
        except ValueError:
            pass  # 日期格式非法时按无截止时间处理，不臆断

    return score, reasons, expired


def rank_jobs(jobs, cfg, today=None):
    """全量打分排序，返回 [(job, score, reasons)]，已过滤过期岗位。"""
    scored = []
    for job in jobs:
        score, reasons, expired = score_job(job, cfg, today)
        if expired or score <= 0:
            continue
        scored.append((job, score, reasons))
    scored.sort(key=lambda x: -x[1])
    return scored
