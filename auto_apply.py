#!/usr/bin/env python3
"""秋招半自动投递助手

用法:
  python3 auto_apply.py <投递链接> [--refcode 内推码]

流程:
  1. 用 agent-browser 打开投递页（复用浏览器登录态）
  2. 快照页面表单，按关键词把资料卡信息填入输入框
  3. 截图给你确认 —— 绝不自动点提交，最终提交由你手动完成

资料卡: data/profile.json（可从看板「投递资料卡」导出）
"""
import json, subprocess, sys, os, re, time

BASE = os.path.dirname(os.path.abspath(__file__))
PROFILE_PATH = os.path.join(BASE, "data", "profile.json")

DEFAULT_PROFILE = {
    "name": "常瑞潇",
    "gender": "",
    "birth": "",
    "hometown": "",
    "political": "",
    "phone": "",
    "email": "",
    "year": "2027届",
    "cet": "",
    "edu": "硕士",
    "school": "",
    "major": "",
    "education": "",
    "internship": "",
    "projects": "",
    "selfeval": "",
    "resume_path": "",
    "expect_job": "",
    "expect_city": "",
}

# 字段关键词映射：资料卡字段 -> 表单 label/placeholder/name 关键词（小写匹配）
# 注意顺序：长文本字段放前面优先匹配 textarea，避免「姓名」误匹配到「姓名拼音」之类
FIELD_KEYWORDS = {
    "selfeval":   ["自我评价", "自我介绍", "个人简介", "自荐", "self evaluation", "about yourself"],
    "internship": ["实习经历", "实习经验", "internship"],
    "projects":   ["项目经历", "项目经验", "project"],
    "education":  ["教育经历", "教育背景", "education experience"],
    "expect_job": ["期望岗位", "意向岗位", "应聘岗位", "期望职位", "意向职位"],
    "expect_city":["期望城市", "意向城市", "期望工作地点", "意向工作地", "期望工作城市"],
    "name":       ["姓名", "真实姓名", "your name", "fullname", "full name", "name"],
    "gender":     ["性别", "gender"],
    "birth":      ["出生年月", "出生日期", "生日", "birth"],
    "hometown":   ["籍贯", "户籍"],
    "political":  ["政治面貌"],
    "cet":        ["英语等级", "英语水平", "cet", "四六级", "六级", "四级", "雅思", "托福"],
    "school":     ["毕业院校", "学校", "院校", "university", "school", "college"],
    "edu":        ["最高学历", "学历", "education", "degree"],
    "major":      ["专业", "major"],
    "phone":      ["手机", "手机号", "联系电话", "联系方式", "mobile", "phone", "tel"],
    "email":      ["电子邮箱", "邮箱", "电子邮件", "email", "e-mail", "mail"],
    "year":       ["毕业时间", "毕业年份", "届", "graduation"],
    "refcode":    ["内推码", "推荐码", "referral", "内推"],
}

RESUME_KW = ["简历", "resume", "cv", "附件"]

def run(cmd, timeout=60):
    r = subprocess.run(["agent-browser"] + cmd, capture_output=True, text=True, timeout=timeout)
    return (r.stdout or "") + (r.stderr or "")

def load_profile():
    if os.path.exists(PROFILE_PATH):
        p = dict(DEFAULT_PROFILE)
        p.update(json.load(open(PROFILE_PATH, encoding="utf-8")))
        return p
    return DEFAULT_PROFILE

def js_escape(s):
    return s.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n")

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    url = sys.argv[1]
    refcode = ""
    if "--refcode" in sys.argv:
        refcode = sys.argv[sys.argv.index("--refcode") + 1]

    profile = load_profile()
    if refcode:
        profile["refcode"] = refcode

    print(f"[1/4] 打开投递页: {url}")
    print(run(["open", url]))
    time.sleep(4)

    print("[2/4] 扫描页面输入框…")
    # 在页面内枚举可见输入框，返回 label/placeholder/name/id
    scan_js = """
    (function(){
      const els = [...document.querySelectorAll('input, textarea')].filter(e => {
        const t = (e.type||'').toLowerCase();
        if (['hidden','submit','button','checkbox','radio','file','password'].includes(t)) return false;
        const r = e.getBoundingClientRect();
        return r.width > 0 && r.height > 0;
      });
      return JSON.stringify(els.map((e, i) => {
        // 找关联 label 文本
        let label = '';
        if (e.id) {
          const l = document.querySelector(`label[for="${e.id}"]`);
          if (l) label = l.textContent.trim();
        }
        const pl = e.closest('label');
        if (!label && pl) label = pl.textContent.trim().slice(0, 30);
        if (!label && e.parentElement) {
          const prev = e.parentElement.querySelector('.label, .form-label, [class*="label"]');
          if (prev) label = prev.textContent.trim().slice(0, 30);
        }
        if (!e.id) e.id = '__ab_fill_' + i;
        return {id: e.id, label, placeholder: e.placeholder || '', name: e.name || '', type: e.type || 'text', value: e.value || ''};
      }));
    })()
    """
    out = run(["eval", scan_js])
    m = re.search(r'"(\[.*\])"', out, re.S)
    if not m:
        print("未能扫描到输入框，页面可能还在加载或有登录墙。请检查浏览器窗口。")
        print(run(["screenshot"]))
        sys.exit(1)
    fields = json.loads(json.loads('"' + m.group(1) + '"'))  # 双重转义还原
    print(f"  发现 {len(fields)} 个输入框")

    print("[3/4] 按资料卡匹配填充…")
    filled, skipped = [], []
    for f in fields:
        if f["value"]:
            continue  # 已有值的不动
        hay = " ".join([f["label"], f["placeholder"], f["name"]]).lower()
        for pkey, keywords in FIELD_KEYWORDS.items():
            val = profile.get(pkey, "")
            if not val:
                continue
            if any(kw.lower() in hay for kw in keywords):
                r = run(["fill", "#" + f["id"], val])
                if "✓" in r or "Done" in r or "filled" in r.lower() or not r.strip().startswith("✗"):
                    filled.append(f"{f['label'] or f['placeholder'] or f['name']} <- {val[:30]}")
                else:
                    skipped.append(f"{f['label']} (fill 失败)")
                break
    for x in filled:
        print("  已填:", x)
    if skipped:
        for x in skipped:
            print("  跳过:", x)

    # 简历 PDF 自动上传
    resume = profile.get("resume_path", "")
    if resume and os.path.exists(resume):
        up_js = """
        (function(){
          const els = [...document.querySelectorAll('input[type=file]')];
          return JSON.stringify(els.map((e, i) => {
            if (!e.id) e.id = '__ab_file_' + i;
            let label = '';
            const pl = e.closest('label');
            if (pl) label = pl.textContent.trim().slice(0, 30);
            if (!label && e.parentElement) label = e.parentElement.textContent.trim().slice(0, 30);
            return {id: e.id, label, accept: e.accept || ''};
          }));
        })()
        """
        out = run(["eval", up_js])
        m = re.search(r'"(\[.*\])"', out, re.S)
        if m:
            file_inputs = json.loads(json.loads('"' + m.group(1) + '"'))
            for fi in file_inputs:
                if any(kw in fi["label"].lower() for kw in RESUME_KW):
                    r = run(["upload", "#" + fi["id"], resume])
                    print(f"  简历已上传 -> {fi['label'] or fi['id']}")
                    break
    elif resume:
        print(f"  简历路径无效（{resume}），跳过自动上传")

    print("[4/4] 截图供你确认（截图路径见下）。检查无误后请手动提交！")
    print(run(["screenshot"]))
    print("\\n提示：浏览器保持打开状态，你可以直接在窗口里继续操作。结束后运行 agent-browser close")

if __name__ == "__main__":
    main()
