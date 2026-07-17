# EdgeOne Makers 目标架构

## 1. 架构目标

项目只保留一套生产运行时：EdgeOne Makers。应用代码负责元宝的业务语义，平台负责通用运行、存储、调度、模型和可观测基础设施。

```text
React / Vite
  ├─ Makers Agent routes (Python / LangGraph / SSE)
  │    ├─ AI Gateway / Makers Models
  │    ├─ LangGraph Checkpointer
  │    ├─ LangGraph Store
  │    └─ Makers Trace
  ├─ Makers Cloud Functions (Node.js)
  │    ├─ Auth / Conversation / File / Library / Paper
  │    ├─ External Signal Connector
  │    └─ Scheduled Tick Bridge
  ├─ Makers Blob
  └─ Neon Serverless Postgres (仅 multi_user 身份；个人单用户不需要)
```

## 2. 平台能力边界

| 关注点 | 最终能力 | 应用只保留的逻辑 |
| --- | --- | --- |
| Agent 运行 | Makers Agent Runtime | LangGraph 图、领域工具、SSE 公共协议 |
| 模型 | Makers Models / AI Gateway | 模型选择、预算和业务提示词 |
| 会话 | Conversation Store | 标题、前端会话体验、租户外部 ID 映射 |
| 短期状态 | LangGraph Checkpointer | 图状态结构与历史裁剪 |
| 用户长期状态 | LangGraph Store | Workspace、Event、Run、Notification、Workflow、Memory |
| 文件 | Makers Blob | 租户 Key、资产元数据、内容校验 |
| 调度 | `edgeone.json.schedules` | Collector、Policy、去重和通知语义 |
| 身份 | 官方 Makers Auth 参考架构 + Neon | 角色、状态、连接器 Token 哈希 |
| 可观测 | Makers Trace / CLS | `/system` 只报告业务 SLO |
| 边缘安全 | EdgeOne WAF/Bot/频控 | 资源级授权与输入校验 |

## 3. 状态所有权

- Conversation Store：会话列表、标题和消息。
- Checkpointer：每个会话的 LangGraph 执行状态。
- LangGraph Store：用户级日程、地图、Action、Provider Ledger、Event、Run、Notification、Workflow、Memory、Feedback 和 Usage。
- Blob：PDF、论文、生成图片、阅读库资产索引。
- Neon：用户、角色、账号状态和外部连接器 Token 哈希；不复制 Agent 业务状态。
- Migration：本地 SQLite 只读导出；一次性 `/migration` 只调用 Conversation Store/LangGraph Store，文件只调用官方 Blob SDK。

## 4. 安全约束

- 多用户模式下内部会话 ID 必须带服务端生成的 tenant scope。
- Agent 入口不能信任浏览器自报 user header；必须验签 Cookie 或系统调度 Secret。
- Blob Key 必须使用租户前缀，下载和删除均验证前缀。
- 高风险副作用只读取服务端冻结 Action，不接收浏览器重传完整参数。
- Provider 调用前写幂等账本；成功后先持久化结果再更新 UI。
- 网络超时视为结果未知，进入 `reconciliation_required`。

## 5. 不进入生产的内容

- `backend/` FastAPI、SQLite Repository、WebSocket、Supervisor 和 Scheduler。
- 本地 `tmeet` CLI、系统 Keychain 和 `meeting-bridge/`。
- 旧 `/api` 前端 Transport fallback。
- 自建会话数据库、对象存储、Cron、通用队列、通用 Trace 或分布式锁服务。

迁移期间可以保留只读历史代码与离线导出工具，但它们不能进入 EdgeOne 构建、运行时依赖或发布门槛。数据验收完成后删除 `LEGACY_IMPORT_SECRET`，使导入入口不可用。
