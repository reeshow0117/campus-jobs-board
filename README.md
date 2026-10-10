# 秋招岗位看板 · 27届

基于两份公开校招表格（27届校招秋招实习内推表 + 毕业帮校招表格）构建的秋招助手：**岗位看板 + 投递追踪 + 半自动填表投递**。

**在线版：<https://campus-jobs-board.pages.dev>**（Cloudflare Pages 托管，推送到 main 分支自动更新）

## 功能

- **岗位看板**（`秋招岗位看板.html`，单文件、离线可用）：14450+ 条岗位，多选筛选（方向/企业性质/类型/城市）、全文搜索、截止倒计时、内推码一键复制、投递状态追踪（未投/已投/笔试/面试/offer，存本机浏览器）、收藏、导出投递清单
- **半自动填表**（`auto_apply.py`）：打开投递页 → 扫描表单 → 按你的资料卡自动填姓名/手机/邮箱/教育经历/实习经历等 → 自动上传简历 PDF → 截图确认，**不自动提交**

## 项目结构与开发

- `web/`：看板模板和简历定制前端（源码）；`dist/`：可部署的静态产物。
- `data/`：抓取、合并与岗位快照；`scripts/build_site.py`：统一构建入口。
- `agent/`：规则推荐、简历生成、PDF 排版和 FastAPI 接口；`tests/`：无真实密钥、无私人简历的回归测试。
- `.github/workflows/`：质量检查与每日数据刷新；`outputs/`、`简历资料库/`、`agent/profiles/`、`agent/state/` 均不进入公开仓库。

```bash
# 静态构建无需第三方依赖
python3 scripts/build_site.py

# 本地后端 / 自动测试（使用隔离虚拟环境）
python3 -m venv .venv
.venv/bin/pip install -e '.[test]'
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python agent/selfcheck.py

# 仅本机个人库模式可读取私库；绝不将此模式接入反向代理
QIUZHAO_PRIVATE_VAULT=1 .venv/bin/python agent/server.py --host 127.0.0.1 --port 8000

# 邀请制模式：状态目录必须在仓库外，权限仅服务账号可读写；命令仅示例，未执行部署
QIUZHAO_ACCESS_DB=/path/outside/repo/access.sqlite3 .venv/bin/python -m agent.access init
QIUZHAO_ACCESS_DB=/path/outside/repo/access.sqlite3 .venv/bin/python -m agent.access invite --label test-user
QIUZHAO_ACCESS_DB=/path/outside/repo/access.sqlite3 QIUZHAO_PLATFORM_MODEL_DAILY_LIMIT=120 .venv/bin/python agent/server.py --host 127.0.0.1 --port 8000
```

`秋招岗位看板.html` 可离线打开；简历页需后端支持，当前**并未开放公网简历生成 API**。服务端使用 `QIUZHAO_LLM_API_KEY`、`QIUZHAO_LLM_BASE_URL`、`QIUZHAO_LLM_MODEL` 环境变量，不要写入仓库。邀请制默认拒绝匿名请求；邀请码一次性兑换、会话有效 30 天，服务端仅保存随机凭据摘要。每位受邀者的生成/PDF 请求合计限 6 次/60 秒；模型的**每次 HTTP 尝试（含失败与重试）**计入北京时间自然日额度，默认 30 次/日，可用 `QIUZHAO_MODEL_DAILY_LIMIT` 设置新用户额度，使用 `python -m agent.access --db <仓库外路径> quota <用户ID> <次数>` 调整某用户额度，使用 `revoke <用户ID>` 即时撤销会话。三步链每次生成通常消耗至少 3 次额度；**全站额度必须显式配置 `QIUZHAO_PLATFORM_MODEL_DAILY_LIMIT`（如本机预发示例的 120 次/日；实际值需按预算确定），缺失/无效时拒绝启动与模型调用**。跨用户全站限额与用户限额在同一 SQLite 写事务中原子校验；额满返回 429，不再调用模型。网页会话仅存标签页 sessionStorage，且绑定已设置的 API 地址；旧版浏览器 BYOK 设置升级时会移除，模型 Key 仅在服务端。浏览器资料和照片不会存入服务器数据库，**但用户自行上传的照片会随 PDF 请求暂时进入后端内存/临时文件并在响应后清理**，不等于端到端无需传输。xiao 的私人 Obsidian 库和照片不部署到服务器；不要将本地单人模式接入反向代理，也不要在未经确认前开放公网接口。

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
python3 scripts/build_site.py       # 同时更新看板、简历页及轻量岗位索引
```

## 部署（Cloudflare Pages · Git 联动）

本仓库通过 Cloudflare Pages 的 Git 集成部署：推送到 `main` 分支即自动构建发布，无需本地装 wrangler。

- 构建配置：Framework preset = None，Build command 留空，Build output directory = `dist`
- `dist/index.html` 即看板完整单文件（数据已内嵌，无需后端）
- 修改 `web/dashboard_template.html` 或 `web/resume.html` 后运行 `python3 scripts/build_site.py`，经 CI 检查后提交。推送 `main` 会触发 Pages 的静态站点更新，**不会部署简历后端**

## 自动更新（GitHub Actions）

`.github/workflows/daily-refresh.yml` 每天北京时间 22:00 自动抓取两张源表、重建看板并推送，Cloudflare Pages 随 push 自动部署——全程无人值守。也可在仓库 Actions 页面手动触发（workflow_dispatch）。数据无变化时自动跳过提交。

## 数据来源

- [27届校招秋招实习内推表](https://docs.qq.com/smartsheet/DWnBUVm9OVFhuSEJ4?tab=twLpD9&viewId=vPmpSf)
- [毕业帮校招表格](https://docs.qq.com/sheet/DTENzbmppUGd2Smxk?tab=000001)

截止时间等字段为源表格原文，未经核实，投递前请以官网公告为准。

## 隐私说明

- 看板投递状态、收藏和个人资料默认只留本机；点击「生成简历」后，你选择的候选人素材和 JD 会当次发往所连接的后端/模型服务处理，尚未承诺端到端不上传
- `data/profile.json`、私人资料库、照片、生成简历、环境变量和本地追踪状态均被 `.gitignore` 排除；静态岗位快照属于公开数据
- 邀请制与用量限制已在功能分支实现，但尚未经公网 HTTPS 预发验证和上线审批；目前仍不对外提供简历 API
