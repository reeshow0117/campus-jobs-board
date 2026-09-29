#!/usr/bin/env python3
"""合并两张校招表为统一数据集 jobs_merged.json，供看板网页使用"""
import json, re, os

OUT_DIR = os.path.dirname(os.path.abspath(__file__))

s1 = json.load(open(os.path.join(OUT_DIR, "sheet1_jobs.json"), encoding="utf-8"))
s2 = json.load(open(os.path.join(OUT_DIR, "sheet2_jobs.json"), encoding="utf-8"))

URL_RE = re.compile(r"https?://[^\s]+")
DATE_RE = re.compile(r"(20\d{2})[年/.-]\s?(\d{1,2})[月/.-]\s?(\d{1,2})")

def extract_url(text):
    if not text:
        return ""
    m = URL_RE.search(text)
    if not m:
        return ""
    u = m.group(0).rstrip("，。；、)）】]")
    # 排除明显无效的假链接
    host = re.sub(r"^https?://", "", u)
    if "." not in host or host.startswith("尽快"):
        return ""
    return u

def clean_deadline(text):
    """返回 (标准日期 or '', 原始文本, 是否推断年份)"""
    if not text:
        return "", "", False
    t = text.strip()
    m = DATE_RE.search(t)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= mo <= 12 and 1 <= d <= 31:
            return f"{y:04d}-{mo:02d}-{d:02d}", t, False
    # 无年份的「X月X日」：秋招季规则 6-12月=2026, 1-6月=2027
    m2 = re.search(r"(\d{1,2})\s?月\s?(\d{1,2})\s?[日号]", t)
    if m2:
        mo, d = int(m2.group(1)), int(m2.group(2))
        if 1 <= mo <= 12 and 1 <= d <= 31:
            y = 2026 if mo >= 6 else 2027
            return f"{y:04d}-{mo:02d}-{d:02d}", t, True
    return "", t, False

# ===== 城市分类 =====
CITY_LIST = ["深圳", "北京", "上海", "广州", "杭州", "成都", "武汉", "西安", "南京", "苏州",
             "天津", "重庆", "长沙", "合肥", "青岛", "厦门", "珠海", "东莞", "佛山", "宁波",
             "无锡", "郑州", "福州", "济南", "大连", "沈阳", "南昌", "昆明", "贵阳", "太原",
             "哈尔滨", "长春", "石家庄", "兰州", "乌鲁木齐", "呼和浩特", "海口", "银川", "西宁"]
OVERSEAS_KW = ["海外", "国外", "俄罗斯", "东南亚", "非洲", "欧洲", "美国", "日本", "韩国",
               "新加坡", "迪拜", "中东", "泰国", "越南", "印尼", "马来西亚", "印度"]

def city_tags(city_str):
    """把自由文本城市拆成分类标签"""
    if not city_str:
        return []
    tags = [c for c in CITY_LIST if c in city_str]
    if "全国" in city_str or "多地" in city_str or "不限" in city_str:
        tags.append("全国多地")
    if "远程" in city_str or "线上" in city_str or "居家" in city_str:
        tags.append("远程/线上")
    if any(k in city_str for k in OVERSEAS_KW):
        tags.append("海外")
    # 去重保序
    seen = set()
    return [t for t in tags if not (t in seen or seen.add(t))]

def norm_company(name):
    n = re.sub(r"[（(].*?[)）]", "", name or "").strip()
    n = re.sub(r"\s+", "", n)
    return n

jobs = []
resources = []

def add_job(source, tab, company, title, city="", industry="", ctype="", jtype="",
            edu="", deadline_raw="", apply_url="", refcode="", notice_url="",
            note="", date="", free_exam="", contact=""):
    company = (company or "").strip()
    if not company or len(company) < 2:
        return
    dl, dl_text, dl_inferred = clean_deadline(deadline_raw)
    city_clean = (city or "").strip().replace("、", " ")
    jobs.append({
        "id": f"{source[:2]}-{tab[:2]}-{len(jobs)}",
        "source": source,
        "tab": tab,
        "company": company,
        "company_key": norm_company(company),
        "title": (title or "").strip(),
        "city": city_clean,
        "city_tags": city_tags(city_clean),
        "industry": (industry or "").strip(),
        "company_type": (ctype or "").strip(),
        "job_type": (jtype or "").strip(),
        "edu": (edu or "").strip(),
        "deadline": dl,
        "deadline_inferred": dl_inferred,
        "deadline_text": dl_text,
        "apply_url": extract_url(apply_url),
        "ref_code": (refcode or "").strip(),
        "notice_url": extract_url(notice_url),
        "note": (note or "").strip(),
        "date": (date or "").strip(),
        "free_exam": (free_exam or "").strip(),
        "contact": (contact or "").strip(),
    })

# ===== sheet1 =====
for r in s1:
    tab = r["_tab"]
    if tab == "国央企求职资料库":
        if r.get("资料名称"):
            resources.append({"type": "国央企资料", "name": r["资料名称"],
                              "url": extract_url(r.get("获取链接", "")) or r.get("获取链接", "")})
        continue
    if tab == "官方招聘平台汇总":
        name = r.get("平台名称") or r.get("名称") or ""
        url = extract_url(r.get("链接", "") or r.get("平台链接", ""))
        if name or url:
            resources.append({"type": "官方招聘平台", "name": name, "url": url})
        continue
    if tab == "华为部门直推":
        add_job("内推表", tab, "华为", r.get("需求岗位", ""), note=r.get("宣传文案", ""),
                contact=r.get("对接人", ""), jtype="实习/校招直推")
        continue
    if tab == "每日更新":
        add_job("内推表", tab, r.get("企业名称", ""), r.get("岗位", ""),
                city=r.get("工作地点", ""), industry=r.get("所在行业", ""),
                jtype=r.get("招聘类型", ""), apply_url=r.get("投递链接", ""),
                date=r.get("更新日期", ""))
        continue
    # 秋招内推表 / 互联网类 / 科技类 / 游戏类 / 金融&教育类 / 实习内推表
    note_text = "\n".join(x for x in [r.get("投递须知", ""), r.get("笔面试信息", ""), r.get("备注", "")] if x)
    # 从须知文字里捞截止日期（如「网申截止12月30日」）
    dl_from_note = ""
    m_dl = re.search(r"截止[^。\n]{0,20}", note_text)
    if m_dl:
        dl_from_note = m_dl.group(0)
    add_job("内推表", tab, r.get("公司名称", ""), r.get("招聘岗位", ""),
            city=r.get("工作地点", ""), industry=r.get("行业大类", ""),
            jtype=r.get("招聘类型", ""), apply_url=r.get("内推链接", ""),
            refcode=r.get("内推码", ""), note=note_text,
            deadline_raw=dl_from_note,
            contact=r.get("联系人", ""))

# ===== sheet2 =====
for r in s2:
    add_job("毕业帮", r["_tab"], r.get("公司名称", ""), r.get("招聘岗位", ""),
            city=r.get("工作地点", ""), industry=r.get("所属行业", ""),
            ctype=r.get("企业性质", ""), jtype=r.get("招聘类型", "") or r.get("届次", ""),
            edu=r.get("学历要求", ""), deadline_raw=r.get("截止时间", "") or r.get("/", ""),
            apply_url=r.get("投递渠道", ""), notice_url=r.get("企业招聘公告", ""),
            note=r.get("备注", ""), date=r.get("日期", ""), free_exam=r.get("免笔试", ""))

# ===== 去重：同公司+岗位前15字相同，保留信息更全的 =====
def score(j):
    return sum(1 for k in ("title", "city", "apply_url", "deadline", "note", "ref_code", "edu") if j[k])

seen = {}
for j in jobs:
    key = (j["company_key"], j["title"][:15])
    if key in seen:
        if score(j) > score(seen[key]):
            seen[key] = j
    else:
        seen[key] = j
jobs = list(seen.values())

# ===== 匹配方向标注（基于用户偏好：民营/大厂 AI产品、解决方案架构师；央国企研发）=====
BIG_TECH = ["腾讯", "阿里", "字节", "美团", "京东", "百度", "华为", "小米", "网易", "快手", "拼多多",
            "滴滴", "蚂蚁", "携程", "哔哩哔哩", "小红书", "得物", "蔚来", "理想", "小鹏", "大疆",
            "OPPO", "vivo", "荣耀", "联想", "海尔", "美的", "格力", "比亚迪", "宁德时代", "商汤",
            "科大讯飞", "旷视", "寒武纪", "地平线", "Momenta", "momenta", "智驾", "百度", "亚马逊",
            "微软", "谷歌", "Apple", "苹果", "英伟达", "NVIDIA", "BIGO", "SHEIN", "虾皮", "Shopee"]
AI_PRODUCT_KW = ["AI产品", "人工智能产品", "大模型产品", "智能体产品", "AIGC产品", "算法产品",
                 "AI 产品", "产品经理", "产品经理", "解决方案", "售前", "架构师", "产品运营",
                 "AI应用", "AI应用工程师", "产品专员"]
RD_KW = ["研发", "算法", "工程师", "开发", "技术", "研究员", "软件", "硬件", "嵌入式", "测试",
         "后端", "前端", "客户端", "服务端", "数据开发", "大数据", "芯片", "IC", "FPGA"]
SOE_KW = ["央国企", "国企", "央企", "事业单位", "政府机关"]

def match_tags(j):
    tags = []
    t = j["title"] or ""
    ct = j["company_type"] or ""
    ind = j["industry"] or ""
    is_soe = any(k in ct or k in ind for k in SOE_KW)
    is_rd = any(k in t for k in RD_KW)
    is_ai_pm = any(k in t for k in AI_PRODUCT_KW)
    is_big = any(k in j["company"] for k in BIG_TECH)
    ai_related = bool(re.search(r"AI|人工智能|大模型|算法|智能|AIGC|LLM", t, re.I))
    if is_ai_pm and not is_soe:
        tags.append("AI产品/解决方案")
    if is_soe and is_rd:
        tags.append("央国企研发")
    if is_big:
        tags.append("大厂")
    if ai_related:
        tags.append("AI相关")
    if "实习" in j["job_type"]:
        tags.append("实习")
    return tags

for j in jobs:
    j["tags"] = match_tags(j)

# 重新分配 id + 瘦身：截断长备注、删空字段、去掉冗余 key
for i, j in enumerate(jobs):
    j["id"] = i
    if len(j["note"]) > 400:
        j["note"] = j["note"][:400] + "…"
    j.pop("company_key", None)
    for k in list(j.keys()):
        if j[k] == "" or j[k] == [] or j[k] is False:
            del j[k]

out = {
    "updated": "2026-09-29",
    "count": len(jobs),
    "jobs": jobs,
    "resources": resources,
}
with open(os.path.join(OUT_DIR, "jobs_merged.json"), "w", encoding="utf-8") as fp:
    json.dump(out, fp, ensure_ascii=False, separators=(",", ":"))

# 统计
from collections import Counter
print("total jobs:", len(jobs))
print("by source:", Counter(j["source"] for j in jobs))
print("by tab:", Counter(j["tab"] for j in jobs).most_common())
print("tags:", Counter(t for j in jobs for t in j.get("tags", [])).most_common())
print("with url:", sum(1 for j in jobs if j.get("apply_url")))
print("with deadline:", sum(1 for j in jobs if j.get("deadline")))
print("27届秋招:", sum(1 for j in jobs if "27" in j.get("job_type","") and "秋招" in j.get("job_type","")))
print("resources:", len(resources))
print("file size:", os.path.getsize(os.path.join(OUT_DIR, 'jobs_merged.json'))//1024, "KB")
