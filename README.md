# 元宝 Agent · EdgeOne Makers 版

元宝是一个运行在腾讯云 EdgeOne Makers 上的多能力主动式 Agent。生产主链使用 Python LangGraph Agent、Makers AI Gateway、LangGraph checkpointer/store、Conversation Store、Cloud Functions、Blob 与平台 Cron；旧 FastAPI 已退役，不再作为生产 Transport 或发布回归门槛。

Makers 项目生产域名：[https://ai-active-agent-tndu0xxa.edgeone.cool](https://ai-active-agent-tndu0xxa.edgeone.cool)。当前改造版本尚未覆盖生产；Preview 动态路由问题和每次部署证据见 [CURRENT_RELEASE.md](docs/CURRENT_RELEASE.md)。

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
| 主动运行时 | EdgeOne cron 每小时触发；持久 Event/Run/Observation、日程/天气/路线 Collector、去重 Notification Inbox、免打扰和每日上限 |
| 长期记忆与反馈 | 记忆先提案后确认；提醒接受/忽略/稍后反馈；连续忽略生成可确认规则提案；Token 日/月预算 |
| 持久工作流 | 主模型可创建多步骤工作流提案；用户确认后后台按依赖和到期时间推进，步骤需显式完成/跳过 |
| 安全副作用 | Action 冻结快照、SHA-256、幂等键、Provider 调用账本、执行租约和未知结果人工核对 |

代码支持单用户和多用户两种模式。个人部署推荐 `single_user`，不需要数据库；多用户采用腾讯官方 Makers 认证参考架构（Neon、bcrypt、HttpOnly JWT），并在每个 Cloud Function 与 Agent 入口执行身份校验、隔离 Conversation、Store、Blob 和连接器 Secret。完整架构见 [ARCHITECTURE.md](docs/ARCHITECTURE.md)，数据迁移见 [DATA_MIGRATION.md](docs/DATA_MIGRATION.md)。

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
| `AUTH_MODE` | 个人部署使用 `single_user`；开放多用户时才切换并配置 Neon/JWT |
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
python -m compileall agents
python -m unittest discover -s agents/_tests -v
python -m unittest discover -s tools/tests -v
node --test cloud-functions/_jwt.test.js cloud-functions/platform-reuse.test.js

cd frontend
npm ci
npm test -- --run
npm run lint
npm run build -- --mode edgeone
```

部署：

```bash
edgeone makers env ls
edgeone makers deploy --json
```

不要提交 `.env`、`.edgeone/`、`frontend/dist/`、本地数据库和上传文件。

## 旧代码边界

`backend/` 仅保留为旧能力和离线迁移参考。FastAPI `/api`、`/ws`、SQLite Scheduler、Supervisor 与本地 `tmeet` 不进入生产构建，也不能作为 Makers 故障回退。

部署步骤见 [DEPLOYMENT.md](docs/DEPLOYMENT.md)，最近发布记录见 [CURRENT_RELEASE.md](docs/CURRENT_RELEASE.md)。
