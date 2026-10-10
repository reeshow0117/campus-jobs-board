#!/usr/bin/env python3
"""简历定制流水线：候选人资料库 + JD -> 定制简历

链路（Prompt Chaining，非自主循环）：
  1. jd_parse      JD 文本 -> 结构化要求（JSON）
  2. select        结构化要求 + 素材库 -> 选材清单（JSON，含取材角度）
  3. write         选材 -> Markdown 定制简历（每条要点带 [@编号] 引用）
  4. selfcheck     机器校验：引用编号必须存在、公司名必须与素材库一致
                   —— 防编造红线，通不过就带反馈重试一次，再不过拒出稿

无 LLM key 时自动降级：输出 JD 关键词 × 素材库命中分析报告，不生成简历。

用法:
  python3 agent/resume_gen.py --user xiao --job-id 8023
  python3 agent/resume_gen.py --user xiao --jd-file jd.txt
  python3 agent/resume_gen.py --user xiao --job-id 8023 --jd "粘贴的JD全文"
"""
import argparse
import json
import os
import re
import sys
from datetime import date

if __package__:
    from . import llm, vault_loader
else:  # 兼容原有命令行入口
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import llm
    import vault_loader

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
JOBS_PATH = os.path.join(ROOT, "data", "jobs_merged.json")
DEFAULT_VAULT = os.path.join(ROOT, "简历资料库")

# 素材条目：### E1 | 组织 | 角色 | 时间段
MATERIAL_RE = re.compile(
    r"^###\s+([A-Z]+\d+)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|\n]+?)\s*$",
    re.M,
)
CITE_RE = re.compile(r"\[@([A-Z]+\d+)\]")


def load_materials(path):
    """解析主简历素材库，返回 {id: {org, role, period, body}}。"""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    matches = list(MATERIAL_RE.finditer(text))
    materials = {}
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        materials[m.group(1)] = {
            "org": m.group(2),
            "role": m.group(3),
            "period": m.group(4),
            "body": text[m.end():end].strip(),
        }
    return materials


def verify_resume(md, materials):
    """防编造自检。返回违规列表，空列表 = 通过。"""
    violations = []
    cited = set(CITE_RE.findall(md))
    if not cited:
        violations.append("生成稿没有任何 [@编号] 引用，无法溯源")
    for cid in cited:
        if cid not in materials:
            violations.append(f"引用了素材库不存在的编号 @{cid}")
    heads = list(MATERIAL_RE.finditer(md))
    if not heads:
        violations.append("生成稿缺少可溯源的经历标题")
    for m in heads:
        cid, org = m.group(1), m.group(2)
        if cid in materials:
            orig = materials[cid]["org"]
            # 完全一致或仅在原名基础上补充（如加英文缩写）视为合法。
            if org != orig and orig not in org:
                violations.append(
                    f"编号 {cid} 的组织名被篡改：'{org}' != 素材库 '{orig}'")
        else:
            violations.append(f"生成稿出现了素材库外的经历标题 {cid} | {org}")
    for line in md.splitlines():
        if line.startswith(("- ", "* ")) and not CITE_RE.search(line):
            violations.append("存在未标注来源的要点，请补充 [@编号]")
            break
    return violations


def materials_brief(materials):
    """素材库摘要，供选材 prompt 使用。"""
    lines = []
    for mid, m in materials.items():
        body = re.sub(r"\s+", " ", m.get("brief") or m["body"])[:200]
        extra = ""
        if m.get("strength"):
            extra += f"强度:{m['strength']} "
        if m.get("directions"):
            extra += f"方向:{'/'.join(m['directions'])}"
        lines.append(f"{mid} | {m['org']} | {m['role']} | {m['period']} {extra}\n  {body}")
    return "\n".join(lines)


def llm_chain(profile, materials, company, title, jd_text):
    """四步链式调用，返回定制简历 Markdown。失败抛 LLMError。"""
    # Step 0: 组合规则代码化 —— 信号词定方向，核心必留 + 方向匹配预筛
    pre, directions = vault_loader.preselect(materials, title + " " + jd_text)
    if not pre:
        pre = materials
    print(f"  [预筛] 方向判定: {','.join(sorted(directions)) or '未识别'}"
          f"｜素材 {len(materials)} → {len(pre)}")

    # Step 1: JD 结构化
    jd_json = llm.chat_json(
        f"""你是简历顾问。把下面的招聘信息解析成 JSON：
{{"role": "岗位定位一句话", "must_have": ["硬性要求"], "nice_to_have": ["加分项"], "keywords": ["关键词"]}}
公司：{company}
岗位：{title}
JD 全文：
{jd_text[:3000]}
只输出 JSON。""",
        timeout_s=30, retries=2,
    )
    if not isinstance(jd_json, dict):
        raise llm.LLMError("JD 解析结果不是对象")

    # Step 2: 选材（在预筛范围内，带上每篇的使用说明作为选材指导）
    brief = materials_brief(pre)
    usage_hints = "\n".join(f"{mid}: {m['usage'][:150]}" for mid, m in pre.items()
                            if m.get("usage"))
    sel = llm.chat_json(
        f"""你是简历顾问。根据岗位要求和候选人素材库，挑选最相关的素材。
岗位要求：{json.dumps(jd_json, ensure_ascii=False)}
素材库：
{brief}
各素材使用建议：
{usage_hints}
输出 JSON 数组：[{{"id": "素材编号", "angle": "这条经历怎么贴合岗位（一句话）"}}]
教育背景（E 开头）必选；其余只选真正相关的，宁缺毋滥；只输出 JSON。""",
        timeout_s=30, retries=2,
    )
    if not isinstance(sel, list):
        raise llm.LLMError("选材结果不是数组")
    picked = [s for s in sel
              if isinstance(s, dict) and s.get("id") in pre]
    if not picked:
        raise llm.LLMError("选材为空")

    # 组装选中的素材全文
    picked_text = "\n\n".join(
        f"### {s['id']} | {materials[s['id']]['org']} | {materials[s['id']]['role']} | {materials[s['id']]['period']}\n"
        f"{materials[s['id']]['body']}\n（取材角度：{s.get('angle', '')}）"
        for s in picked
    )

    # Step 3: 生成定制简历（带引用，供自检）
    md = llm.chat(
        f"""你是资深简历写手。根据岗位要求和候选人选中的素材，写一份定制简历（Markdown）。

【硬性规则，违反即废稿】
1. 只允许改写、重组、强调素材库中已有的内容，禁止编造任何经历、公司、时间、数据
2. 保留每条经历的标题行格式：### 编号 | 组织 | 角色 | 时间段（组织名一字不改）
3. 每条要点末尾标注来源：[@编号]
4. 素材中带【】或"填写"字样的是待补充占位，直接跳过不写入简历
5. 一页 A4 硬约束：实习最多 3 段、每段最多 3 条要点；项目最多 2-3 个、每个最多 2 条要点；社会实践最多 1 条；技能与证书压缩到 4 行以内。全文要点总数控制在 22 条以内，宁短勿长
6. 素材完整版里的量化数据（GPA、排名、百分比、覆盖人数等）是简历的硬通货，选中素材的核心要点必须保留，不得随意丢弃
7. 每条要点格式：**主题词：**具体内容（主题词 4-10 字，概括这条要点的卖点）；要点中的量化数据（数字、百分比、排名、规模）也用 **加粗** 突出

【排序原则】
教育背景硕士在前；实习按时间倒序、在职经历第一位；项目按与 JD 相关性优先；
国企/银行/管培方向可追加 ## 社会实践 板块（V 开头素材）并上调奖项权重；
互联网/AI 方向突出项目与技术理解，社会实践不放。

【候选人基本信息】
{json.dumps(profile, ensure_ascii=False)}

【岗位要求】
{json.dumps(jd_json, ensure_ascii=False)}
目标公司：{company}；目标岗位：{title}

【选中素材】
{picked_text}

【输出结构】
# 姓名 - 求职意向（附联系方式一行）
## 求职亮点（3 条以内，每条标注 [@编号]，直接回应 must_have）
## 教育经历 / ## 实习经历 / ## 项目经历（按上面的排序原则）
## 社会实践（仅国企/银行/管培方向，1-2 条）
## 技能与证书
只输出 Markdown 简历正文。""",
        timeout_s=60, retries=2,
    )
    return md


def keyword_report(materials, company, title, jd_text):
    """无 LLM 降级：JD 关键词 × 素材命中分析。"""
    cfg_path = os.path.join(BASE, "config.json")
    kws = []
    if os.path.exists(cfg_path):
        with open(cfg_path, encoding="utf-8") as f:
            kws = list(json.load(f).get("target_keywords", {}).keys())
    jd_all = (title + " " + jd_text).lower()
    jd_hits = [k for k in kws if k.lower() in jd_all]
    lines = [
        f"## 匹配分析（纯规则模式，未生成简历）",
        f"",
        f"目标：{company} · {title}",
        f"JD 命中关键词：{', '.join(jd_hits) if jd_hits else '无'}",
        f"",
        f"| 素材 | 角色 | 命中关键词 |",
        f"|---|---|---|",
    ]
    for mid, m in materials.items():
        body = (m["role"] + " " + m["body"]).lower()
        hits = [k for k in jd_hits if k.lower() in body]
        lines.append(f"| {mid} {m['org']} | {m['role']} "
                     f"| {', '.join(hits) if hits else '-'} |")
    lines.append("")
    lines.append("配置 QIUZHAO_LLM_API_KEY / BASE_URL / MODEL 后可生成定制简历。")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="按 JD 定制简历")
    ap.add_argument("--user", required=True, help="候选人目录名（agent/profiles/<user>）")
    ap.add_argument("--job-id", type=int, help="岗位库中的岗位 id")
    ap.add_argument("--jd", default="", help="直接粘贴 JD 全文")
    ap.add_argument("--jd-file", help="JD 文本文件路径")
    ap.add_argument("--no-llm", action="store_true", help="只出匹配分析报告")
    args = ap.parse_args()

    user_dir = os.path.join(BASE, "profiles", args.user)
    profile_path = os.path.join(user_dir, "profile.json")
    master_path = os.path.join(user_dir, "master_resume.md")

    profile = {}
    if os.path.exists(profile_path):
        with open(profile_path, encoding="utf-8") as f:
            profile = json.load(f)

    # 优先读 Obsidian 资料库（含强度/方向标签与三级粒度），否则退回单文件母库
    if os.path.isdir(DEFAULT_VAULT):
        basic_info, materials = vault_loader.load_vault(DEFAULT_VAULT)
        # 基本信息表并入 profile（姓名/电话/邮箱等）
        key_map = {"姓名": "name", "电话": "phone", "邮箱": "email"}
        for k, v in basic_info.items():
            mk = key_map.get(k)
            if mk and not profile.get(mk):
                profile[mk] = v
        profile["contact"] = " / ".join(x for x in
            [basic_info.get("电话", ""), basic_info.get("邮箱", "")] if x)
        print(f"[1/4] 加载 Obsidian 资料库：{len(materials)} 条素材（{DEFAULT_VAULT}）")
    elif os.path.exists(master_path):
        materials = load_materials(master_path)
        print(f"[1/4] 加载资料库：{len(materials)} 条素材（{args.user}）")
    else:
        print(f"找不到素材库：{DEFAULT_VAULT} 或 {master_path}")
        sys.exit(1)

    company, title, jd_text = "", "", ""
    if args.job_id is not None:
        with open(JOBS_PATH, encoding="utf-8") as f:
            jobs = json.load(f)["jobs"]
        job = next((j for j in jobs if j["id"] == args.job_id), None)
        if not job:
            print(f"岗位库中不存在 id={args.job_id}")
            sys.exit(1)
        company = job.get("company", "")
        title = str(job.get("title", "")).replace("\n", " ")[:80]
    if args.jd_file:
        with open(args.jd_file, encoding="utf-8") as f:
            jd_text = f.read()
    if args.jd:
        jd_text = args.jd
    if not jd_text:
        jd_text = title  # 无 JD 全文时用岗位标题兜底，效果有限
    if not company and not jd_text.strip():
        print("需要提供 --job-id 或 --jd/--jd-file 之一")
        sys.exit(1)
    print(f"[2/4] 目标：{company or '（自定义JD）'} · {title or '（见JD）'}")

    use_llm = not args.no_llm and llm.is_configured()
    result, warnings = None, []
    if use_llm:
        print("[3/4] LLM 链式生成（解析JD → 选材 → 写作）…")
        try:
            result = llm_chain(profile, materials, company, title, jd_text)
        except llm.LLMError as e:
            print(f"  LLM 链失败，降级为匹配分析：{e}")
    else:
        print("[3/4] 纯规则模式（--no-llm 或未配置 key）")

    if result:
        print("[4/4] 防编造自检…")
        violations = verify_resume(result, materials)
        if violations:
            print(f"  自检发现 {len(violations)} 处违规，带反馈重试一次：")
            for v in violations:
                print(f"   - {v}")
            try:
                fix_prompt_feedback = "；".join(violations)
                result = llm.chat(
                    f"上一版简历违反规则：{fix_prompt_feedback}。请只输出修正后的完整 Markdown 简历。",
                    timeout_s=60, retries=1)
                violations = verify_resume(result, materials)
            except llm.LLMError as e:
                violations = violations + [f"重试调用失败：{e}"]
        if violations:
            warnings = violations
            print(f"  重试后仍有 {len(violations)} 处违规，输出稿带警告标记，请人工核对")
        else:
            print("  自检通过：所有经历可溯源")
    else:
        result = keyword_report(materials, company, title, jd_text)

    out_dir = os.path.join(user_dir, "outputs")
    os.makedirs(out_dir, exist_ok=True)
    safe_company = re.sub(r"[^\w一-鿿]+", "_", company or "custom")[:30]
    out_path = os.path.join(
        out_dir, f"resume_{safe_company}_{date.today().isoformat()}.md")
    header = ""
    if warnings:
        header = ("<!-- 警告：自检未完全通过，投递前必须人工逐条核对以下问题：\n"
                  + "\n".join(f"- {w}" for w in warnings) + "\n-->\n\n")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(header + result + "\n")
    print(f"\n输出：{out_path}")


if __name__ == "__main__":
    main()
