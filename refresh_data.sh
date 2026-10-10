#!/bin/bash
# 一键刷新秋招数据：重抓两张腾讯文档表 → 合并去重 → 重建看板 → 提交推送（Git 联动自动部署）
# 用法: ./refresh_data.sh
set -e
cd "$(dirname "$0")"

PY="${PY:-python3}"
echo "==> [1/4] 抓取 27届内推表（smartsheet）"
"$PY" data/fetch_smartsheet.py

echo "==> [2/4] 抓取 毕业帮校招表格（内嵌智能表格）"
"$PY" data/fetch_sheet2.py

echo "==> [3/4] 合并去重 + 生成看板"
"$PY" data/merge_jobs.py
"$PY" scripts/build_site.py

echo "==> [4/4] 提交并推送（Cloudflare Pages 会自动部署）"
git add data/jobs_merged.json data/sheet1_jobs.json data/sheet2_jobs.json 秋招岗位看板.html dist/index.html dist/resume.html dist/jobs_slim.json
if git diff --cached --quiet; then
  echo "数据无变化，跳过提交"
else
  git commit -m "data: refresh jobs $(date +%Y-%m-%d)"
  git push
  echo "已推送，Cloudflare Pages 构建中，约 1 分钟后生效"
fi
