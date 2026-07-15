# 元宝 Agent · EdgeOne Makers 版

当前分支将原本需要本地常驻 FastAPI、WebSocket、SQLite 和自建模型/搜索连接的应用，改造成可由腾讯云 EdgeOne Makers 托管的 LangGraph Agent。前端仍保留本地模式，便于继续维护旧的日程、论文和旅行能力；Makers 构建则启用云端 Agent、平台会话存储、平台工具、模型网关、追踪和 Blob 文件存储。

生产环境：[https://ai-active-agent-tndu0xxa.edgeone.cool](https://ai-active-agent-tndu0xxa.edgeone.cool)

## Makers 版能力

| 能力 | EdgeOne Makers 实现 |
| --- | --- |
| Agent 运行时 | `agents/chat/index.py`，Python LangGraph |
| 模型 | Makers AI Gateway，不直连模型厂商 |
| 联网搜索 | `ctx.tools` 注入的 `web_search` |
| 短期记忆 | `ctx.store.langgraph_checkpointer` |
| 长期状态 | `ctx.store.langgraph_store` |
| 对话恢复 | `agents/messages/index.py` 读取 LangGraph 检查点 |
| 流式输出 | Makers SSE，含 5 秒心跳、工具事件、Usage 和取消 |
| 文件存储 | Makers Blob 预签名直传，文件字节不经过应用函数 |
| 前端托管 | Vite 静态产物由 EdgeOne 托管 |
| 可观测性 | Makers Agent Runtime 内置追踪 |
| 工作区 | 左、中、右连续分栏；左右宽度可拖拽并持久化，右栏可收起 |
| 搜索体验 | 搜索状态使用稳定尺寸和滚动锚定，流式切换搜索词时避免中栏抖动 |
| 地图与日程 | 右侧地图联动、路线查询、日程确认后写入及视觉反馈 |

## 目录

```text
agents/
├── chat/                 # LangGraph 主对话端点：POST /chat
├── messages/             # 检查点恢复端点：POST /messages
├── places/               # 地点搜索与地图数据
├── routes/               # 路线查询
├── workspace/            # 地图、日程、会议等工作区操作
└── stop/                 # 中止运行：POST /stop
cloud-functions/
├── files/                # Makers Blob 签名、读取、删除：/files
└── conversations/        # 会话列表及会话管理
frontend/                 # React + Vite
backend/                  # 旧本地模式，Makers 生产链路不启动它
edgeone.json              # Makers 构建和 Agent 框架配置
requirements.txt          # Python Agent 依赖
```

## 环境变量

复制 `.env.example` 的变量名到 Makers 项目环境。不要提交真实值。

| 变量 | 来源 | 是否必需 |
| --- | --- | --- |
| `AI_GATEWAY_API_KEY` | Makers CLI 自动注入 | 是 |
| `AI_GATEWAY_BASE_URL` | Makers CLI 自动注入 | 是 |
| `AI_GATEWAY_MODEL` | 可选，默认 `@makers/deepseek-v4-flash` | 否 |
| `WSA_API_KEY` | 腾讯云 Web Search API | 使用联网搜索时是 |

## 本地 Makers 开发

要求 EdgeOne CLI `>= 1.6.7`。所有本地联调都通过 Makers dev server，不能使用普通静态服务器替代。

```bash
npm install -g edgeone@latest
edgeone -v
edgeone whoami
edgeone makers link
edgeone makers env pull
edgeone makers dev
```

默认访问 CLI 输出的 Makers 代理地址，通常为 `http://127.0.0.1:8088/`。该地址同时提供静态前端、Agent 路由和 Cloud Functions。

## 质量检查

```bash
python -m compileall agents

cd backend
python -m unittest discover -s tests -p "test_*.py"

cd frontend
npm ci
npm test -- --run
npm run lint
npm run build
npm run build -- --mode edgeone
```

部署前还应执行：

```bash
edgeone makers env ls
edgeone makers deploy --json
```

部署命令会根据 `edgeone.json` 重新构建并发布静态前端、Cloud Functions 和 Agents。不要提交 `.env`、`.edgeone/` 或 `frontend/dist/`；它们分别包含本地环境变量、部署生成文件和构建产物。

当前生产部署与验证记录见 [docs/CURRENT_RELEASE.md](docs/CURRENT_RELEASE.md)。

完整的迁移范围、平台映射、边界与验收项见 [docs/EDGEONE_MAKERS_MIGRATION.md](docs/EDGEONE_MAKERS_MIGRATION.md)。

## 本地兼容模式

直接在 `frontend/` 执行 `npm run dev` 时仍使用原 FastAPI `/api` 能力，适合维护日程、旅行、论文、本地备份等旧功能。Makers 构建通过 `frontend/.env.edgeone` 自动切换到云端界面，不会探测域名来猜运行环境，因此自定义域名同样可用。

本地前端使用 `/ws/{conversation_id}` WebSocket，不能请求 Makers 的 `/chat`。无真实模型密钥时可显式开启 Mock 模式完成令牌、WebSocket、流式回复和持久化测试：

```powershell
cd backend
$env:MOCK_MODE='true'
python -m uvicorn main:app --host 127.0.0.1 --port 8000

# 另开终端
cd frontend
npm run dev -- --host 127.0.0.1 --port 5173
```

打开 `http://127.0.0.1:5173/`。Mock 模式只影响旧本地后端；EdgeOne 模式仍使用 Makers AI Gateway。
