# 元宝 Agent · EdgeOne Makers 版

元宝是一个运行在腾讯云 EdgeOne Makers 上的多能力主动式 Agent。生产主链使用 Python LangGraph Agent、Makers AI Gateway、LangGraph checkpointer/store、Conversation Store、Cloud Functions、Blob 与平台 Cron；旧 FastAPI 已退役，不再作为生产 Transport 或发布回归门槛。

Makers 项目：`ai-active-agent`（`makers-0oeuhire655w`）。项目使用 GitHub Provider，由 EdgeOne 控制台从目标分支创建 Preview/Production；不能对该项目执行本地目录直传。未绑定自定义域名时，默认 `edgeone.cool` 地址需要从控制台“预览”获取 3 小时访问链接。部署证据见 [CURRENT_RELEASE.md](docs/CURRENT_RELEASE.md)。

## 当前生产能力

| 能力 | 实现与边界 |
| --- | --- |
| 对话与会话恢复 | Makers LangGraph checkpointer；每个对话独立上下文 |
| 联网图文回答 | WSA SearchPro + 网页媒体抽取 + HY-Vision 视觉相关性筛选 |
| 地点与地图 | 腾讯位置服务优先，OSM 降级；真实地点 ID 才能进入地图 |
| 道路路线 | 腾讯路线优先，OSRM 降级；支持多点顺序与费用估算 |
| 日程 | 跨对话用户工作区；Agent 提案确认后写入，右栏支持直接 CRUD |
| 腾讯会议 | 最后阶段可选连接器；凭据齐全才暴露工具，不影响个人部署 |
| AI 生图 | 混元 `hy-image-v3.0` 直接生成；现实主体可复用富搜索 + HY-Vision 审核图，支持版本轮播、绘制动画、Blob 归档与 ZIP 下载 |
| 论文与 PDF | 普通富搜索后桥接公开 PDF/arXiv 下载；PDF 自动分类、文件夹化“我的阅读”，论文支持选词、翻译、总结、全文助读和问答 |
| 主动运行时 | EdgeOne cron 每日触发（当前 Makers 平台最短间隔为 1 天）；持久 Event/Run/Observation、日程/天气/路线 Collector、去重 Notification Inbox、免打扰和每日上限 |
| 长期记忆与反馈 | 后台自动提取、过滤和清理非敏感稳定记忆；提醒接受/忽略/稍后反馈；连续忽略生成可确认规则提案；Token 日/月预算 |
| 持久工作流 | 主模型可创建多步骤工作流提案；用户确认后后台按依赖和到期时间推进，步骤需显式完成/跳过 |
| 安全副作用 | Action 冻结快照、SHA-256、幂等键、Provider 调用账本、执行租约和未知结果人工核对 |

当前产品固定为个人单所有者演示，不包含注册、登录、JWT、租户或用户数据库。线上业务状态完全使用 Makers Conversation Store、LangGraph Store 和 Blob；不需要 SQLite、Neon 或其他应用数据库。完整架构见 [ARCHITECTURE.md](docs/ARCHITECTURE.md)，旧 SQLite 数据迁移见 [DATA_MIGRATION.md](docs/DATA_MIGRATION.md)。

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
backend/                  # 已退役 FastAPI/SQLite 历史参考；不部署、不新增功能
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
| `TENCENT_MAP_SERVER_KEY` | 腾讯地点与路线服务 |
| `TENCENT_MEETING_*` | 最后阶段可选连接器；个人开发者当前可不配置 |

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

完整测试命令、测试站的两种本地启动方式和多主机共享说明见 [TESTING.md](docs/TESTING.md)。

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

## GitHub Provider 发布

```bash
git push -u origin <当前分支>
```

随后进入 EdgeOne 控制台 → Makers → `ai-active-agent` → 构建部署 → 新建部署，选择刚推送的分支并创建 Preview。该项目不是 Upload Provider，`edgeone makers deploy` 会被平台拒绝；生产发布必须在 Preview 自动化与人工验收通过后单独授权。

不要提交 `.env`、`.edgeone/`、`frontend/dist/`、本地数据库和上传文件。

## 旧代码边界

`backend/` 仅保留为旧能力和离线迁移参考。FastAPI `/api`、`/ws`、SQLite Scheduler、Supervisor 与本地 `tmeet` 不进入生产构建，也不能作为 Makers 故障回退。

部署步骤见 [DEPLOYMENT.md](docs/DEPLOYMENT.md)，测试与测试站启动见 [TESTING.md](docs/TESTING.md)，最近发布记录见 [CURRENT_RELEASE.md](docs/CURRENT_RELEASE.md)。
