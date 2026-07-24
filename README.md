# FLORIS · EdgeOne Makers 版

FLORIS 是一个运行在腾讯云 EdgeOne Makers 上的多能力主动式 Agent。生产主链使用 Python LangGraph Agent、Makers AI Gateway、LangGraph checkpointer/store、Conversation Store、Cloud Functions、Blob 与平台 Cron；旧 FastAPI 已退役，不再作为生产 Transport 或发布回归门槛。

Makers 项目：`ai-active-agent`（`makers-0oeuhire655w`）。项目使用 GitHub Provider，由 EdgeOne 控制台从目标分支创建 Preview/Production；不能对该项目执行本地目录直传。未绑定自定义域名时，默认 `edgeone.cool` 地址需要从控制台“预览”获取 3 小时访问链接。部署证据见 [CURRENT_RELEASE.md](docs/CURRENT_RELEASE.md)。

## 当前生产能力

| 能力 | 实现与边界 |
| --- | --- |
| 对话与会话恢复 | Makers LangGraph checkpointer；每个对话独立上下文 |
| 联网图文回答 | WSA SearchPro + 网页媒体抽取 + HY-Vision 视觉相关性筛选 |
| 地点与地图 | 腾讯位置服务优先，OSM 降级；真实地点 ID 才能进入地图 |
| 道路路线 | 腾讯路线优先，OSRM 降级；支持多点顺序与费用估算 |
| 日程 | 跨对话用户工作区；Agent 提案确认后写入，右栏支持直接 CRUD；删除只提交目标项，服务端拒绝完全相同的重复创建 |
| 腾讯会议 | 可选的官方个人 MCP Skill；只配置个人 Token 后才暴露工具，不需要企业开发者凭据 |
| AI 生图 | 混元 `hy-image-v3.0` 直接生成；现实主体可复用富搜索 + HY-Vision 审核图，支持版本轮播、绘制动画、Blob 归档与 ZIP 下载 |
| 论文与 PDF | 普通富搜索后桥接公开 PDF/arXiv 下载；PDF 自动分类、文件夹化“我的阅读”，论文支持选词、翻译、总结、全文助读和问答；翻译记录随阅读项目持久化并可跨主机恢复 |
| 界面与回答语言 | 设置中可切换简体中文、繁体中文、English、可爱喵喵语、冷酷喵喵语；固定界面文案、聊天回答和论文助读遵循同一语言偏好 |
| 主动运行时 | 回答完成后语义识别搜索/写作/翻译/生图/任务机会；外文 PDF 仅上传、不提问时也可主动建议当前界面语言版本，采纳后自动挂载原文档；EdgeOne cron 继续扫描日程/天气/路线/工作流；统一使用持久 Event/Run/Notification、冷却、过期、免打扰和每日上限 |
| 长期记忆与反馈 | 后台自动提取、过滤和清理非敏感稳定记忆；提醒接受/忽略/稍后反馈；连续忽略生成可确认规则提案；Token 日/月预算 |
| Skills 广场 | 现有能力默认全部开启；开关同时约束 Agent 工具与直接业务入口，支持硬依赖自动补齐和推荐依赖的上下文引导 |
| 持久工作流 | 主模型可创建多步骤工作流提案；用户确认后后台按依赖和到期时间推进，步骤需显式完成/跳过 |
| 安全副作用 | Action 冻结快照、SHA-256、幂等键、Provider 调用账本、执行租约和未知结果人工核对 |

当前产品固定为个人单所有者演示，不包含注册、登录、JWT、租户或用户数据库。线上业务状态完全使用 Makers Conversation Store、LangGraph Store 和 Blob；不需要 SQLite、Neon 或其他应用数据库。完整架构见 [ARCHITECTURE.md](docs/ARCHITECTURE.md)，旧 SQLite 数据迁移见 [DATA_MIGRATION.md](docs/DATA_MIGRATION.md)。

### Header 主动提醒

提醒不会再写入新对话，避免和用户发送消息产生竞态。有效提醒会在标题右侧以一行文字轮播，淡入淡出并可点击展开左侧面板；左侧面板仍保留完整操作入口（按建议处理、稍后 1 小时、忽略）。

- 日程在未来 24 小时内开始：提示即将开始。
- 两个日程时间重叠：提示发现日程冲突。
- 不同地点间隔不足 30 分钟：提示行程衔接较紧。
- 已核实的日程地点遇到雨雪、雷暴、台风、大风、沙尘、雾、冰雹或严寒：提示关注天气。
- 用户已经明确授予浏览器定位权限后：只用约 1 公里的临时粗粒度坐标查询城市级天气；遇到上述风险时提示当前所在地天气，原始坐标不写入 Event/Notification。
- 未来相邻日程的真实路线耗时加 15 分钟仍超过空档：提示通勤时间可能不足。
- 回答、文档上传、生图完成后，只有独立语义模型判断确有价值时，才提示搜索更新、写作/翻译优化、图片迭代、文档下一步或任务下一步；低置信度、重复、敏感或一次性问题不会提醒。

日程地点使用已核实的地点服务数据；浏览器定位只在用户已授权后触发，后端不保存坐标。安全长期记忆和近期问题只作为后台语义判断上下文，不会在界面展示。

## 目录

```text
agents/
├── chat/                 # LangGraph 主对话、能力规划和生产工具
├── proactive/            # 定时 Collector、Event/Run、通知和持久工作流
├── intelligence/         # 记忆提案、反馈、规则和预算
├── system/               # 主动运行时健康与可观测性
├── messages/             # 从检查点恢复消息与工作区
├── reader/               # 论文翻译、总结、全文助读与问答
├── places/               # 真实地点查询
├── routes/               # 道路路线查询
├── workspace/            # 地图、日程、会议和生图操作
└── stop/                 # 停止当前 Agent 运行
cloud-functions/
├── files/                # Makers Blob 签名、读取和删除
├── library/              # 跨会话“我的阅读”资产索引
├── papers/               # arXiv 搜索、下载和论文归档
└── conversations/        # Makers 会话列表、标题和消息追加
frontend/                 # React + Vite 双模式前端
tools/                    # SQLite 只读导出和 Makers 一次性导入工具；不进入运行时
docs/                     # Makers 当前事实、迁移计划和部署验收
frontend/public/test-cases/ # 静态全功能验收站（访问 /test-cases/）
edgeone.json              # Makers 构建与 Agent 配置
```

## 状态所有权

- 对话历史与短期记忆：按 `conversation_id` 存在 LangGraph checkpointer。
- 会话列表与标题：Makers conversation store。
- 日程、地图、Action、Event/Run/Notification、工作流、记忆、反馈和预算：单用户 LangGraph store，跨对话共享。
- PDF、论文和生成图片字节：Makers Blob；阅读索引同样持久化在 Blob。
- 旧 SQLite 数据：只读迁移来源；不属于生产状态所有权。

## 环境变量

将 `.env.example` 中需要的变量配置到 Makers 项目环境，不要提交真实值。

| 变量 | 用途 |
| --- | --- |
| `AI_GATEWAY_API_KEY` / `AI_GATEWAY_BASE_URL` | Makers AI Gateway，CLI 通常自动注入 |
| `AI_GATEWAY_MODEL` | 主对话模型，默认 `@makers/deepseek-v4-flash` |
| `WSA_API_KEY` / `WSA_BASE_URL` | 联网富搜索 |
| `HUNYUAN_IMAGE_API_KEY` | TokenHub 多模态图片筛选与混元生图（Hy3 是纯文本模型，不用于看图） |
| `HUNYUAN_VISION_API_KEY` / `HUNYUAN_VISION_MODEL` | 可选的独立视觉密钥与模型覆盖，默认复用上项并调用 `hy-vision-2.0-instruct` |
| `CLOUDFLARE_ACCOUNT_ID` / `CLOUDFLARE_WORKERS_AI_TOKEN` | 可选的每日免费额度视觉理解、文生图和图生图降级 |
| `DASHSCOPE_API_KEY` / `GEMINI_API_KEY` | 可选的视觉理解后备；不作为当前免费生图链 |
| `RICH_SEARCH_*_TIMEOUT_SECONDS` | 搜索、媒体提取和视觉审核硬预算；默认 10/5/7 秒 |
| `TENCENT_MAP_SERVER_KEY` | 腾讯地点与路线服务 |
| `TENCENT_MEETING_TOKEN` | 可选的腾讯会议个人 AI Skill Token；未配置时安全隐藏会议工具 |

视觉免费额度、Provider 顺序和无破坏 Preview 验收见 [VISUAL_PROVIDER_FALLBACK.md](docs/VISUAL_PROVIDER_FALLBACK.md)；当前混元接口、Apple 风格微交互与 Cloudflare 最小配置见 [MOTION_AND_VISUAL_FALLBACK.md](docs/MOTION_AND_VISUAL_FALLBACK.md)。

## Makers 本地开发

要求 EdgeOne CLI `>= 1.6.7`：

```bash
npm install -g edgeone@latest
edgeone -v
edgeone whoami
edgeone makers link
edgeone makers env pull
edgeone makers dev
```

使用 CLI 输出的 Makers 代理地址（通常为 `http://127.0.0.1:8088/`）；它同时提供静态前端、Agent 路由和 Cloud Functions。

## 质量检查

```bash
. .venv/bin/activate
python3 -m compileall agents
python3 -m unittest discover -s agents/_tests -v
python3 -m unittest discover -s tools/tests -v
npm test

cd frontend
npm ci
npm test -- --run
npm run lint
npm run build -- --mode edgeone
```

完整测试命令、测试站的两种本地启动方式和跨主机共享说明见 [TESTING.md](docs/TESTING.md)。比赛主动服务闭环见 [CONTEST_SOLUTION.md](docs/CONTEST_SOLUTION.md)。

## 测试 Case 启动

需要测试结果、备注、编辑记录和图片/视频证据跨主机持久化时，必须启动完整 Makers 本地代理：

```bash
npm ci
npm --prefix frontend ci
edgeone makers link
edgeone makers env pull
edgeone makers dev
```

访问 CLI 输出地址下的 `/test-cases/`，通常是 `http://127.0.0.1:8088/test-cases/`。只检查静态页面时可执行 `npm --prefix frontend run dev` 并访问 `http://127.0.0.1:5173/test-cases/index.html`；Vite 不应用 EdgeOne rewrite，不能省略 `index.html`。此模式没有 `/acceptance` Cloud Function，只使用当前浏览器 `localStorage`，不能验证跨主机持久化或证据上传。

线上验收时，从 EdgeOne 控制台为目标 Git 分支创建 Preview，再打开其 3 小时签名链接的 `/test-cases/`。具体步骤见 [ACCEPTANCE_SITE.md](docs/ACCEPTANCE_SITE.md)。

当前数据代际、AI 自主富媒体排版、全局微交互、日程就地编辑和 Skills 依赖均已纳入 [`BASELINE.md`](docs/BASELINE.md) 与 [`ARCHITECTURE.md`](docs/ARCHITECTURE.md)，不再维护单次版本改造日志。

## GitHub Provider 发布

```bash
git push -u origin <当前分支>
```

随后进入 EdgeOne 控制台 → Makers → `ai-active-agent` → 构建部署 → 新建部署，选择刚推送的分支并创建 Preview。该项目不是 Upload Provider，`edgeone makers deploy` 会被平台拒绝；生产发布必须在 Preview 自动化与人工验收通过后单独授权。

不要提交 `.env`、`.edgeone/`、`frontend/dist/`、本地数据库和上传文件。

## 旧代码边界

旧 FastAPI/SQLite 运行时代码已从仓库删除。历史数据迁移只保留独立的只读导出器和 Makers 导入器；FastAPI `/api`、`/ws`、SQLite Scheduler、Supervisor 与本地 `tmeet` 不再存在，也不能作为 Makers 故障回退。

部署步骤见 [DEPLOYMENT.md](docs/DEPLOYMENT.md)，测试与测试站启动见 [TESTING.md](docs/TESTING.md)，最近发布记录见 [CURRENT_RELEASE.md](docs/CURRENT_RELEASE.md)。
