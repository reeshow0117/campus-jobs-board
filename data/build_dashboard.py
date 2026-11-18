#!/usr/bin/env python3
"""把 jobs_merged.json 注入模板，生成单文件看板 HTML"""
import json, os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
tpl = open(os.path.join(BASE, "dashboard_template.html"), encoding="utf-8").read()
data = open(os.path.join(BASE, "data", "jobs_merged.json"), encoding="utf-8").read()

# 防止 JSON 中的 </script> 提前闭合标签
data_safe = data.replace("</", "<\\/")

catalog = open(os.path.join(BASE, "company_catalog.js"), encoding="utf-8").read()
ui = open(os.path.join(BASE, "company_browser.js"), encoding="utf-8").read()
out = tpl.replace("__JOBS_DATA__", data_safe).replace("__COMPANY_CATALOG_JS__", catalog.replace("</", "<\\/")).replace("__COMPANY_BROWSER_JS__", ui.replace("</", "<\\/"))
out_path = os.path.join(BASE, "秋招岗位看板.html")
with open(out_path, "w", encoding="utf-8") as f:
    f.write(out)
print("built:", out_path, os.path.getsize(out_path) // 1024, "KB")
