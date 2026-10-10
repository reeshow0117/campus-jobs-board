"""Obsidian 简历资料库加载器

直接读取 简历资料库/ 目录（零搬运），把每篇笔记解析成素材条目：
  - frontmatter：类型 / 强度 / tags（方向/xxx）/ 时间 / 公司
  - 正文三级粒度：完整版、精简版（一句话）、可拆 bullet
  - 「使用说明」段单独保留，作为选材与写作的指导（不进正文素材）

目录 → 编号前缀：02-教育=E 03-实习=S 04-项目=P 05-技能=J 06-奖项=A 07-实践=V
01-基本信息 不进入素材库，单独解析为个人信息字典。
"""
import os
import re

FOLDER_PREFIX = {
    "02": "E", "03": "S", "04": "P", "05": "J", "06": "A", "07": "V",
}
SKIP_FOLDERS = ("00", "08")  # 索引与模板不进素材库

# 方向判定信号词（来自 08-JD简历组合器/组合规则.md）
DIRECTION_SIGNALS = {
    "AI算法": ["大模型", "llm", "rag", "agent", "微调", "算法", "深度学习", "机器学习", "nlp", "多模态"],
    "AI产品": ["产品经理", "产品", "需求", "用户", "商业化", "落地", "策划", "运营"],
    "国企银行": ["金融科技", "管培", "轮岗", "银行", "国企", "央企", "数字化"],
    "硬件": ["嵌入式", "硬件", "pcb", "通信", "信号"],
}

FM_LINE_RE = re.compile(r"^([\w一-鿿]+)\s*:\s*(.*)$")
H1_RE = re.compile(r"^#\s+(.+)$", re.M)
SECTION_RE = re.compile(r"^##\s+(.+)$", re.M)


def parse_frontmatter(text):
    """解析 YAML frontmatter 的扁平子集（key: value 与 [a, b] 列表）。"""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    fm = {}
    for line in text[3:end].splitlines():
        m = FM_LINE_RE.match(line.strip())
        if not m:
            continue
        k, v = m.group(1), m.group(2).strip()
        if v.startswith("[") and v.endswith("]"):
            fm[k] = [x.strip() for x in v[1:-1].split(",") if x.strip()]
        else:
            fm[k] = v
    return fm, text[end + 4:]


def split_sections(body):
    """按 ## 标题切段，返回 {标题: 内容}。"""
    parts = list(SECTION_RE.finditer(body))
    sections = {}
    for i, m in enumerate(parts):
        end = parts[i + 1].start() if i + 1 < len(parts) else len(body)
        sections[m.group(1).strip()] = body[m.end():end].strip()
    return sections


def detect_directions(text):
    """按信号词判定 JD 方向，返回方向集合。"""
    t = text.lower()
    return {d for d, kws in DIRECTION_SIGNALS.items()
            if any(k.lower() in t for k in kws)}


def load_vault(vault_dir):
    """加载整个资料库，返回 (basic_info, materials)。

    materials: {id: {org, role, period, body, usage, strength, directions, kind}}
    """
    basic_info, materials = {}, {}
    counters = {}

    for entry in sorted(os.listdir(vault_dir)):
        folder = os.path.join(vault_dir, entry)
        if not os.path.isdir(folder) or entry.startswith("."):
            continue
        prefix2 = entry[:2]
        if prefix2 in SKIP_FOLDERS:
            continue

        for fn in sorted(os.listdir(folder)):
            if not fn.endswith(".md"):
                continue
            path = os.path.join(folder, fn)
            with open(path, encoding="utf-8") as f:
                fm, body = parse_frontmatter(f.read())

            if prefix2 == "01":  # 基本信息：表格解析为 profile 字段
                for m in re.finditer(r"\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|", body):
                    k, v = m.group(1).strip(), m.group(2).strip()
                    if k not in ("字段", "---") and not k.startswith("-"):
                        basic_info[k] = v
                continue

            prefix = FOLDER_PREFIX.get(prefix2)
            if not prefix:
                continue
            counters[prefix] = counters.get(prefix, 0) + 1
            mid = f"{prefix}{counters[prefix]}"

            sections = split_sections(body)
            full = sections.get("完整版", "")
            brief = next((v for k, v in sections.items() if k.startswith("精简版")), "")
            bullets = next((v for k, v in sections.items() if k.startswith("可拆")), "")
            usage = next((v for k, v in sections.items() if k.startswith("使用说明")), "")
            # 无三级结构的笔记（如技能栈）：正文去掉使用说明后整体作为素材
            if not full and not bullets:
                full = "\n".join(v for k, v in sections.items()
                                 if not k.startswith("使用说明")).strip() or body.strip()

            h1 = H1_RE.search(body)
            org = fm.get("公司") or fm.get("学校") or fm.get("名称") or os.path.splitext(fn)[0]
            tags = fm.get("tags", []) if isinstance(fm.get("tags"), list) else []
            materials[mid] = {
                "org": org,
                "role": h1.group(1).strip() if h1 else os.path.splitext(fn)[0],
                "period": fm.get("时间", ""),
                "body": full + ("\n" + bullets if bullets else ""),
                "brief": brief,
                "usage": usage,
                "strength": fm.get("强度", "补充"),
                "directions": [t.split("/", 1)[1] for t in tags
                               if isinstance(t, str) and t.startswith("方向/")],
                "kind": prefix,
            }
    return basic_info, materials


def preselect(materials, jd_text):
    """组合规则第二步的代码化：核心必留 + 方向标签匹配的补充素材。

    返回 (预筛后的 materials dict, 判定出的方向集合)。
    """
    directions = detect_directions(jd_text)
    picked = {}
    for mid, m in materials.items():
        if m["strength"] in ("核心", "必备"):
            picked[mid] = m
        elif directions and any(d in directions for d in m["directions"]):
            picked[mid] = m
    return picked, directions
