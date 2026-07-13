# EdgeOne Makers 改造说明

## 目标与原则

本次改造的目标不是把本地 FastAPI 进程原样塞入 Serverless，而是优先采用 Makers 已提供的运行时和平台能力，减少自建服务、密钥转发、会话数据库、搜索代理、流式连接和文件中转。

原则：

1. AI 推理放在 `agents/`，数据函数放在 `cloud-functions/`。
2. 模型只通过 Makers AI Gateway 访问。
3. 框架状态使用 Makers 官方 LangGraph adapters，不再双写 SQLite 和平台存储。
4. 搜索使用 `ctx.tools`，不保留固定 IP 或自建搜索代理。
5. 文件使用 Makers Blob 预签名直传，不经过 Agent 进程。
6. `.edgeone/`、`.env` 和构建产物不进入版本库。

## 改造映射

| 原实现 | Makers 实现 | 代码位置 |
| --- | --- | --- |
| FastAPI WebSocket Chat | Python Agent + SSE | `agents/chat/index.py` |
| 直连 DeepSeek/混元 | AI Gateway | `agents/chat/_llm.py` |
| 自建搜索服务和固定公网 IP | 平台 `web_search` | `agents/chat/index.py` |
| SQLite 对话消息 + LangGraph 双写 | LangGraph Checkpointer 单一事实源 | `agents/chat/_graph.py` |
| 本地消息恢复 API | 从最新检查点恢复 | `agents/messages/index.py` |
| WebSocket ping/pong | SSE 5 秒 `ping` | `agents/chat/index.py` |
| 客户端断开即丢失取消语义 | AbortSignal + `/stop` | `useSSEChat.ts`, `agents/stop/index.py` |
| 后端接收整个 PDF | Blob 预签名直传 | `cloud-functions/files/index.js` |
| 域名字符串判断运行环境 | Vite EdgeOne build mode | `frontend/.env.edgeone`, `auth.ts` |
| 手工生成的 `.edgeone` 运行时 | CLI 构建时生成 | `.gitignore` |

## 运行链路

```text
React/Vite
   │ POST /chat + makers-conversation-id
   ▼
Makers Python Agent Runtime
   ├─ AI Gateway
   ├─ ctx.tools → web_search
   ├─ LangGraph checkpointer/store
   ├─ SSE + heartbeat + usage
   └─ built-in tracing

PDF ── request signed URL ──► Cloud Function ──► Makers Blob
 │
 └──────────── direct PUT to Blob ───────────────►
```

## 关键契约

- `/chat`、`/messages` 和 `/stop` 必须携带 `makers-conversation-id` header；这是当前 Makers Agent Runtime 在进入处理器前校验的统一契约。
- `/stop` 的目标会话同时放在 JSON body 的 `conversation_id`，供取消 API 明确选择正在运行的会话。
- Agent 和 Cloud Function 内不得读取 `os.environ` / `process.env`；Agent 使用 `ctx.env`。
- SSE 使用 `ai_response`、`tool_call`、`tool_result`、`usage`、`ping`、`error_message`，并以 `[DONE]` 结束。
- Agent 工具循环通过 LangGraph `recursion_limit` 限制，避免无界执行。
- `agents/messages` 位于 Agent 目录，是因为 Cloud Function 的 store 不包含 LangGraph adapters。

## 保留边界

原项目的日程、旅行路线、论文库、会议、生图、主动 Collector、备份恢复属于结构化业务数据或本地设备能力。Makers 的 conversation store 不是关系数据库，不应把这些表强行塞入会话存储。本次处理方式是：

- 本地模式继续由 `backend/` 提供这些能力；
- Makers 模式不启动旧 FastAPI，也不代理到固定服务器；
- Makers 前端隐藏依赖旧本地 API 的日历与调试面板；
- 后续若要把这些能力全部云化，应选择外部关系数据库，并把纯 CRUD 放入 Cloud Functions。文件本身已经迁移到 Makers Blob。

## 部署前检查

- [ ] EdgeOne CLI 版本不低于 `1.6.7`
- [ ] `edgeone.json` 的 `agents.framework` 为 `langgraph`
- [ ] `.env.example` 声明 AI Gateway 变量
- [ ] Makers 项目已配置 `WSA_API_KEY`
- [ ] 仓库中不存在 `.edgeone/`、根 `.env` 或真实密钥
- [ ] `python -m compileall agents` 通过
- [ ] 前端测试、ESLint 和 EdgeOne mode 构建通过
- [ ] `edgeone makers dev` 下验证 `/chat`、刷新恢复、联网搜索、停止和 PDF 上传
- [x] 本地兼容模式验证 access token、`/ws/default-conversation`、ping/pong、流式事件和刷新恢复
- [x] 前端本地构建与 `--mode edgeone` 构建均通过
- [x] 后端全量测试及本地 WebSocket 端到端测试通过
- [ ] 部署使用 `edgeone makers deploy --json`，保留完整预览 URL 查询参数

## 参考规范

- [EdgeOne Makers Agent 开发规范](https://github.com/TencentEdgeOne/edgeone-makers-tools/blob/main/skills/makers-agents/SKILL.md)
- [EdgeOne Makers 迁移规范](https://github.com/TencentEdgeOne/edgeone-makers-tools/blob/main/skills/makers-migration/SKILL.md)
- [EdgeOne Makers Storage](https://github.com/TencentEdgeOne/edgeone-makers-tools/blob/main/skills/makers-storage/SKILL.md)
- [EdgeOne Makers Cloud Functions](https://github.com/TencentEdgeOne/edgeone-makers-tools/blob/main/skills/makers-cloud-functions/SKILL.md)
