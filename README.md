# 秋招岗位看板 · 27届

基于两份公开校招表格（27届校招秋招实习内推表 + 毕业帮校招表格）构建的秋招助手：**岗位看板 + 投递追踪 + 半自动填表投递**。

**在线版：<https://campus-jobs-board.pages.dev>**（Cloudflare Pages 托管，推送到 main 分支自动更新）

## 功能

- **岗位看板**（`秋招岗位看板.html`，单文件、离线可用）：14450+ 条岗位，多选筛选（方向/企业性质/类型/城市）、全文搜索、截止倒计时、内推码一键复制、投递状态追踪（未投/已投/笔试/面试/offer，存本机浏览器）、收藏、导出投递清单
- **半自动填表**（`auto_apply.py`）：打开投递页 → 扫描表单 → 按你的资料卡自动填姓名/手机/邮箱/教育经历/实习经历等 → 自动上传简历 PDF → 截图确认，**不自动提交**

## 快速开始（看板）

直接用浏览器打开 `秋招岗位看板.html` 即可，无需安装任何东西。数据为抓取时点的快照。

## 使用自动填表脚本

需要 Python 3.9+ 和 Node.js 18+。

```bash
# 1. 安装浏览器自动化工具
npm install -g agent-browser
agent-browser install

# 2. 填写你的资料卡
cp data/profile.example.json data/profile.json
# 编辑 data/profile.json，填入你的姓名、手机、邮箱、教育/实习经历、简历PDF路径等

# 3. 对某个投递链接运行
python3 auto_apply.py "https://投递链接" --refcode 内推码
```

脚本会打开浏览器窗口并完成填写，**最后一步提交永远由你手动完成**。

## 自己抓取最新数据（可选）

```bash
./refresh_data.sh    # 一条命令：重抓两张表 → 合并 → 重建看板 → 提交推送（自动部署）
```

或手动分步执行：

```bash
python3 data/fetch_smartsheet.py   # 抓内推表
python3 data/fetch_sheet2.py       # 抓毕业帮表
python3 data/merge_jobs.py         # 合并清洗
python3 data/build_dashboard.py    # 重新生成看板 HTML
cp 秋招岗位看板.html dist/index.html
```

## 部署（Cloudflare Pages · Git 联动）

本仓库通过 Cloudflare Pages 的 Git 集成部署：推送到 `main` 分支即自动构建发布，无需本地装 wrangler。

- 构建配置：Framework preset = None，Build command 留空，Build output directory = `dist`
- `dist/index.html` 即看板完整单文件（数据已内嵌，无需后端）
- 修改 `dashboard_template.html` 后运行 `python3 data/build_dashboard.py && cp 秋招岗位看板.html dist/index.html`，提交推送即可上线

## 自动更新（GitHub Actions）

`.github/workflows/daily-refresh.yml` 每天北京时间 22:00 自动抓取两张源表、重建看板并推送，Cloudflare Pages 随 push 自动部署——全程无人值守。也可在仓库 Actions 页面手动触发（workflow_dispatch）。数据无变化时自动跳过提交。

## 数据来源

- [27届校招秋招实习内推表](https://docs.qq.com/smartsheet/DWnBUVm9OVFhuSEJ4?tab=twLpD9&viewId=vPmpSf)
- [毕业帮校招表格](https://docs.qq.com/sheet/DTENzbmppUGd2Smxk?tab=000001)

截止时间等字段为源表格原文，未经核实，投递前请以官网公告为准。

## 隐私说明

- 投递状态、收藏、资料卡均保存在**你自己浏览器/本机**，不上传任何服务器
- `data/profile.json` 已在 .gitignore 中排除，不会被提交
