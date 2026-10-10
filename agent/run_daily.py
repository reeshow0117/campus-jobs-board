#!/usr/bin/env python3
"""秋招智能体 · 每日主编排（固定流水线，非自主循环）

链路：加载数据 -> 增量检测 -> 规则初筛 -> LLM 精排（可选，失败降级）-> 生成报告

用法:
  python3 agent/run_daily.py              # 完整跑一遍，报告写入 outputs/
  python3 agent/run_daily.py --no-llm     # 强制纯规则模式

LLM 配置（不配则自动走纯规则模式）:
  export QIUZHAO_LLM_API_KEY=...
  export QIUZHAO_LLM_BASE_URL=https://api.openai.com/v1
  export QIUZHAO_LLM_MODEL=<模型名>
"""
import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import llm
from matcher import load_config, rank_jobs

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
JOBS_PATH = os.path.join(ROOT, "data", "jobs_merged.json")
PROFILE_PATH = os.path.join(ROOT, "data", "profile.json")
SEEN_PATH = os.path.join(BASE, "state", "seen_jobs.json")
TRACKER_PATH = os.path.join(BASE, "state", "tracker.json")
OUT_DIR = os.path.join(ROOT, "outputs")


def load_json(path, default):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    os.replace(tmp, path)


def detect_new(jobs):
    """对比历史快照找出新增岗位（按 公司+标题+链接 指纹）。"""
    seen = set(load_json(SEEN_PATH, []))
    new, fp_all = [], []
    for j in jobs:
        fp = f"{j.get('company', '')}|{j.get('title', '')}|{j.get('apply_url', '')}"
        fp_all.append(fp)
        if fp not in seen:
            new.append(j)
    save_json(SEEN_PATH, fp_all)
    return new


def llm_rerank(candidates, profile, cfg):
    """LLM 精排规则初筛的 Top 候选。任何失败都降级为规则分（C4）。

    返回 {job_id: {"score": 0-100, "reason": str}}，失败返回 None。
    """
    if not llm.is_configured():
        print("[llm] 未配置 API key，跳过精排（纯规则模式）")
        return None

    brief = [{
        "id": j["id"], "company": j.get("company", ""),
        "title": str(j.get("title", ""))[:80], "city": j.get("city", ""),
        "industry": j.get("industry", ""),
        "deadline": j.get("deadline", "") or j.get("deadline_text", ""),
    } for j, _, _ in candidates[:cfg["llm"]["max_candidates"]]]

    prompt = f"""你是秋招岗位匹配助手。以下是求职者画像和候选岗位列表，请逐一评估匹配度。

【求职者画像】
目标岗位：{profile.get("expect_job", "")}；期望城市：{profile.get("expect_city", "")}
学历：{profile.get("edu", "")}；专业：{profile.get("major", "")}
实习经历：{str(profile.get("internship", ""))[:300]}
项目经历：{str(profile.get("projects", ""))[:300]}

【候选岗位】
{json.dumps(brief, ensure_ascii=False)}

【要求】
1. 对每条岗位打 0-100 匹配分，并给一句不超过 30 字的中文理由
2. 只输出 JSON 数组，格式：[{{"id": 数字, "score": 数字, "reason": "理由"}}]
3. 不要输出任何其他内容"""

    try:
        result = llm.chat_json(
            prompt,
            timeout_s=cfg["llm"]["timeout_s"],
            retries=cfg["llm"]["retries"],
        )
        if not isinstance(result, list):
            raise llm.LLMError("LLM 返回不是数组")
        # 校验并过滤非法条目，不允许 LLM 结果直接生效
        valid = {}
        for item in result:
            if isinstance(item, dict) and isinstance(item.get("id"), int):
                valid[item["id"]] = {
                    "score": max(0, min(100, float(item.get("score", 0)))),
                    "reason": str(item.get("reason", ""))[:50],
                }
        print(f"[llm] 精排完成，{len(valid)}/{len(brief)} 条有效")
        return valid
    except llm.LLMError as e:
        print(f"[llm] 精排失败，降级为纯规则分：{e}")
        return None


def blend_scores(candidates, llm_scores, cfg):
    """规则分与 LLM 分加权融合；无 LLM 结果时直接用规则分。"""
    if not llm_scores:
        return [(j, s, r, "") for j, s, r in candidates]
    max_rule = max(s for _, s, _ in candidates) or 1
    rw = cfg["llm"]["rule_weight"]
    blended = []
    for j, s, r in candidates:
        ls = llm_scores.get(j["id"])
        if ls:
            final = rw * (s / max_rule * 100) + (1 - rw) * ls["score"]
            blended.append((j, final, r, ls["reason"]))
        else:
            blended.append((j, s / max_rule * 100 * rw, r, ""))
    blended.sort(key=lambda x: -x[1])
    return blended


def render_report(today, new_jobs, ranked, tracker, cfg, llm_used):
    """生成 Markdown 每日报告。"""
    top = ranked[:cfg["top_n"]]
    lines = [
        f"# 秋招日报 · {today.isoformat()}",
        "",
        f"- 岗位池：{len(load_json(JOBS_PATH, {'jobs': []})['jobs'])} 条"
        f"｜今日新增：{len(new_jobs)} 条"
        f"｜已投递：{len(tracker)} 条"
        f"｜排序模式：{'规则初筛 + LLM 精排' if llm_used else '纯规则'}",
        "",
        "## 今日 Top 推荐",
        "",
        "| # | 公司 | 岗位 | 城市 | 截止 | 分数 | 推荐理由 | 状态 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for i, (j, score, reasons, llm_reason) in enumerate(top, 1):
        t = tracker.get(str(j["id"]), {})
        dl = j.get("deadline", "") or j.get("deadline_text", "") or "-"
        reason = llm_reason or "；".join(reasons[:3])
        title = str(j.get("title", "-")).replace("\n", " ").replace("|", "｜")[:40]
        url = j.get("apply_url", "")
        company = f"[{j.get('company', '?')}]({url})" if url else j.get("company", "?")
        ref = j.get("ref_code", "")
        if ref:
            company += f"（内推码 `{ref.split()[0]}`）"
        lines.append(
            f"| {i} | {company} | {title} | {j.get('city', '-')} | {dl} "
            f"| {score:.0f} | {reason} | {t.get('status', '未投')} |"
        )

    urgent = [(j, s, r) for j, s, r, _ in ranked
              if any("截止" in x for x in r)]
    if urgent:
        lines += ["", "## 7 天内截止（抓紧）", ""]
        for j, s, r in urgent[:10]:
            lines.append(f"- **{j.get('company')}** {str(j.get('title', ''))[:40]}"
                         f" —— {j.get('deadline')} 截止，{j.get('apply_url', '')}")

    if new_jobs:
        lines += ["", "## 今日新增岗位（全量）", ""]
        for j in new_jobs[:50]:
            url = j.get("apply_url", "")
            lines.append(f"- [{j.get('company', '?')}]({url})"
                         f" {str(j.get('title', ''))[:50]}"
                         f"｜{j.get('city', '-')}")

    if tracker:
        lines += ["", "## 投递进度", ""]
        counts = {}
        for v in tracker.values():
            counts[v["status"]] = counts.get(v["status"], 0) + 1
        lines.append("｜".join(f"{k} {v}" for k, v in sorted(counts.items())))

    lines += ["", "---", "*规则打分理由见每条推荐；截止时间为源表原文，投递前以官网为准。*"]
    return "\n".join(lines)


def main():
    today = date.today()
    cfg = load_config()
    force_no_llm = "--no-llm" in sys.argv

    print(f"[1/5] 加载岗位数据…")
    jobs = load_json(JOBS_PATH, {"jobs": []})["jobs"]
    profile = load_json(PROFILE_PATH, {})
    tracker = load_json(TRACKER_PATH, {})
    print(f"  {len(jobs)} 条岗位")

    print("[2/5] 增量检测…")
    new_jobs = detect_new(jobs)
    print(f"  新增 {len(new_jobs)} 条")

    print("[3/5] 规则初筛…")
    ranked = rank_jobs(jobs, cfg, today)
    print(f"  {len(ranked)} 条通过初筛（已剔除过期与零分岗位）")

    print("[4/5] LLM 精排…")
    llm_scores = None if force_no_llm else llm_rerank(ranked, profile, cfg)
    ranked_final = blend_scores(ranked, llm_scores, cfg)

    print("[5/5] 生成报告…")
    os.makedirs(OUT_DIR, exist_ok=True)
    report = render_report(today, new_jobs, ranked_final, tracker, cfg,
                           llm_used=bool(llm_scores))
    out_path = os.path.join(OUT_DIR, f"daily_{today.isoformat()}.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"  报告已写入: {out_path}")
    print(f"\n完成。Top 1: {ranked_final[0][0].get('company')} "
          f"({ranked_final[0][1]:.0f} 分)" if ranked_final else "\n无推荐岗位")


if __name__ == "__main__":
    main()
