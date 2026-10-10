#!/usr/bin/env python3
"""生成岗位轻量索引 dist/jobs_slim.json，供 resume.html 前端按需加载

只保留定制简历所需的字段，体积约为全量的 1/10。
"""
import json
import os

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)

with open(os.path.join(ROOT, "data", "jobs_merged.json"), encoding="utf-8") as f:
    jobs = json.load(f)["jobs"]

slim = [{
    "id": j["id"],
    "company": j.get("company", "")[:40],
    "title": str(j.get("title", ""))[:60],
    "city": str(j.get("city", ""))[:20],
    "deadline": str(j.get("deadline", "") or "")[:10],
} for j in jobs]

out = os.path.join(ROOT, "dist", "jobs_slim.json")
with open(out, "w", encoding="utf-8") as f:
    json.dump({"count": len(slim), "jobs": slim}, f, ensure_ascii=False, separators=(",", ":"))
print(f"slim index: {len(slim)} jobs -> {out} ({os.path.getsize(out) // 1024} KB)")
