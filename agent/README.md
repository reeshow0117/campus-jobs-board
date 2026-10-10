# 秋招智能体（agent/）

在岗位看板之上加一层"每日推荐 + 投递追踪"的自动化流水线。

**架构说明**：这是固定流水线 + 一个 LLM 精排节点（Prompt Chaining），不是自主循环 Agent。
抓取、打分、追踪都是确定性逻辑；LLM 只负责规则算不准的语义匹配，且失败自动降级，
无 LLM key 时整个系统照常可用（纯规则模式）。

## 用法

```bash
# 每日推荐（报告写入 outputs/daily_YYYY-MM-DD.md）
python3 agent/run_daily.py

# 强制纯规则模式（不调用 LLM）
python3 agent/run_daily.py --no-llm

# 投递状态追踪
python3 agent/tracker.py add 1234 --status 已投 --note "官网投递"
python3 agent/tracker.py list --status 面试
python3 agent/tracker.py stats

# 规则打分器自检（改 config.json 权重后跑一遍）
python3 agent/selfcheck.py
```

## 启用 LLM 精排（可选）

规则初筛 Top 50 交由 LLM 按你的简历语义重排（0.4×规则分 + 0.6×LLM 分）：

```bash
export QIUZHAO_LLM_API_KEY=你的key
export QIUZHAO_LLM_BASE_URL=https://api.openai.com/v1   # 任意 OpenAI 兼容接口
export QIUZHAO_LLM_MODEL=模型名
python3 agent/run_daily.py
```

调用带 30s 超时、2 次重试（指数退避+抖动），任何失败自动降级为纯规则分。

## 文件说明

| 文件 | 职责 |
|---|---|
| `config.json` | 匹配偏好：目标/负面关键词权重、城市、行业权重、Top N、LLM 参数 |
| `matcher.py` | 规则打分（方向关键词/城市/行业/内推码/免笔试/截止紧迫度），过期淘汰 |
| `llm.py` | OpenAI 兼容客户端（标准库实现，超时/重试/降级，凭据只走环境变量） |
| `run_daily.py` | 主编排：增量检测 → 规则初筛 → LLM 精排 → Markdown 报告 |
| `tracker.py` | 投递状态机：未投→已投→笔试→面试→offer/已挂，原子写入 |
| `selfcheck.py` | 11 条断言评测：正常/边界/对抗用例 + 排序断言 |
| `state/` | 运行状态：seen_jobs.json（增量指纹）、tracker.json（投递记录） |

## 候选人资料库 + 简历定制（多用户）

每个候选人一个目录：`profiles/<用户名>/`

- `profile.json`：资料卡（基本信息、求职意向）
- `master_resume.md`：**经历母库**——所有简历只能从这里取材，格式 `### 编号 | 组织 | 角色 | 时间段`
- `outputs/`：生成的定制简历

```bash
# 按岗位库 id 定制（岗位标题兜底当 JD，效果有限）
python3 agent/resume_gen.py --user xiao --job-id 8023

# 粘贴 JD 全文效果最好
python3 agent/resume_gen.py --user xiao --job-id 8023 --jd "JD全文..."

# 无 LLM：只出 JD×素材命中分析
python3 agent/resume_gen.py --user xiao --job-id 8023 --no-llm
```

链路：解析 JD → 素材库选材 → 生成 Markdown 简历 → **防编造自检**（每条要点必须带 `[@编号]` 引用；
编号不存在、组织名与素材库不符或要点无引用均违规；生成稿留作人工核对，PDF 导出拒绝不合规内容）。
**AI 只能改写和强调已有经历，绝不编造——这是红线。**

### Obsidian 资料库模式（推荐，xiao 自用）

默认直接读取项目根目录的 `简历资料库/`（Obsidian vault），无需搬运数据：

- 每篇笔记的 frontmatter `强度: 核心/补充` 和 `tags: [方向/xxx]` 用于**预筛**：
  组合规则的"信号词定方向"已代码化（`vault_loader.py`），核心素材必留、方向匹配的补充素材入选
- 「完整版 + 可拆 bullet」进选材上下文，「使用说明」作为选材指导
- `01-基本信息` 的表格自动并入候选人信息（姓名/电话/邮箱）

```bash
# 配置一次（建议写入 ~/.zshrc）：用 DeepSeek 的 OpenAI 兼容接口
export QIUZHAO_LLM_API_KEY=$DEEPSEEK_API_KEY
export QIUZHAO_LLM_BASE_URL=https://api.deepseek.com/v1
export QIUZHAO_LLM_MODEL=deepseek-chat

# 日常用法：给岗位 id 或直接粘 JD
python3 agent/resume_gen.py --user xiao --job-id 8023
python3 agent/resume_gen.py --user xiao --jd "粘贴的JD全文"
```

已实跑验证：job-id 8023（虾皮全球管培）方向判定"AI产品"，素材 18→10 预筛，生成稿自检全过、每条经历可溯源。

## 看板内的简历生成（本地可用；公开上线前还需加固）

看板右上角「定制简历」打开 `resume.html`：

1. **其他候选人**先在「我的资料库」填姓名、教育、实习和项目，选证件照（JPG/PNG，≤2MB），可导入/导出 JSON；资料在自己的浏览器 localStorage，照片只在本次页面会话保留。
2. 在「定制简历」填公司、岗位、**粘贴完整 JD**；生成时浏览器把资料和 JD 当次发给同域的 `agent/server.py`，后端不落库。选材、写作、溯源自检后预览 Markdown；校验通过才可预览/下载 PDF。
3. PDF 固定复用 `agent/resume_pdf.py`：宋体优先（Linux 为 Noto Serif CJK 衬线体）、适当加粗、矢量 ➢ 左对齐（无需分发第三方字体）、照片避开分隔线。超过单页则明确报错，**不会把多页文件伪装成单页**。

**xiao 的本地专用入口**：设置 `QIUZHAO_PRIVATE_VAULT=1`，仅 `--host 127.0.0.1` 启动，并在简历页勾选「使用本机私人 Obsidian 资料库」；前端不上传、不展示本人的资料库。生产服务器**不要启用该变量，不要公网反代这个单人模式**。

```bash
# 在本机已经配置好 QIUZHAO_LLM_API_KEY / QIUZHAO_LLM_BASE_URL / QIUZHAO_LLM_MODEL 后
QIUZHAO_PRIVATE_VAULT=1 python3 agent/server.py --host 127.0.0.1 --port 8000
# 打开 http://127.0.0.1:8000/resume.html；看板入口也已接入
```

平台模式 API：`GET /api/capabilities`、`POST /api/resume`、`POST /api/resume_pdf`。公开模式只处理请求内的 profile/materials，不读取磁盘里的私人库。页面在同域时服务器地址留空；静态看板如果未连接后端，会明确提示「简历服务尚未连接」，不假装生成成功。

**公开上线前必须完成**：
- 在腾讯云服务器配置 HTTPS/同域反代、中文字体、LLM 密钥（环境变量，不能进前端）；不要上传 xiao 的私人库或照片。
- 增加候选人登录或可信的身份网关、按用户限流和用量限制，再开放 LLM 接口；目前匿名接口可被滥用，**不要直接把现有 FastAPI 端口暴露到公网**。CORS 白名单并不等于身份认证。
- 处理资料库跨设备同步和私密存储前，浏览器版本仅能在当前设备使用；模板照片须各自上传。BYOK 浏览器直连 LLM 仅作高级备用，不支持服务器 PDF 且受服务商 CORS 约束。

`简历资料库/`、`agent/profiles/`、`outputs/` 都被 .gitignore 排除，严禁提交公开仓库。当前只完成本地代码集成，未公开部署。

## 配合现有工具

- 看板（`秋招岗位看板.html`）负责浏览筛选；本模块负责"每天该投什么"
- 报告中挑好岗位后，用 `auto_apply.py <链接> --refcode 内推码` 半自动填表
- `./refresh_data.sh` 刷新岗位数据后再跑 `run_daily.py` 即可看到"今日新增"
