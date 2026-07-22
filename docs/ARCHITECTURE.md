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
  │    ├─ Conversation / File / Library / Paper
  │    └─ Scheduled Tick Bridge
  └─ Makers Blob
```

## 2. 平台能力边界

| 关注点 | 最终能力 | 应用只保留的逻辑 |
| --- | --- | --- |
| Agent 运行 | Makers Agent Runtime | LangGraph 图、领域工具、SSE 公共协议 |
| 模型 | Makers Models / AI Gateway | 模型选择、预算和业务提示词 |
| 视觉/生图 Provider | 混元 + 可配置外部托管 API | Provider 顺序、超时预算、结果校验；不自建推理服务 |
| 会话 | Conversation Store | 标题与前端会话体验 |
| 短期状态 | LangGraph Checkpointer | 图状态结构与历史裁剪 |
| 用户长期状态 | LangGraph Store | Workspace、Event、Run、Notification、Workflow、Memory |
| 文件 | Makers Blob | 资产元数据与内容校验 |
| 调度 | `edgeone.json.schedules` | Collector、Policy、去重和通知语义 |
| 身份 | 固定个人所有者 | 不提供注册、登录或租户能力 |
| 可观测 | Makers Trace / CLS | `/system` 只报告业务 SLO |
| 边缘安全 | EdgeOne WAF/Bot/频控 | 资源级授权与输入校验 |

## 3. 状态所有权

- Conversation Store：会话列表、标题和消息。
- Checkpointer：每个会话的 LangGraph 执行状态。
- LangGraph Store：用户级日程、地图、Action、Provider Ledger、Event、Run、Notification、Workflow、Memory、Feedback 和 Usage。
- 搜索规划：独立 LLM 读取当前问题和已过滤的非敏感记忆，合并事实与视觉意图；每轮一次 SearchPro，来源页按设置并发，默认 10/5/7 秒分段预算；单轮任务缓存阻止重复调用，跨轮结果按时效 TTL 存入用户级 LangGraph Store。
- 视觉能力：混元优先；Cloudflare Workers AI 复用托管视觉、文生图和图生图模型，百炼/Gemini 可作视觉理解后备。应用只保留降级路由、输入边界和 Makers Blob 持久化，不实现模型推理。
- 长期记忆：后台 LLM 只提取用户明确表达的稳定偏好、目标和项目背景；应用层再次拒绝联系方式、凭证、证件、精确地址、财务和医疗信息，并按置信度、TTL 和使用次数清理。记忆值不进入公共 API 或前端列表。
- 日程变更：大模型只冻结确认 Action；服务端按当前 Workspace 的 schedule_id 执行。地点必须是地点服务返回的 place_id；成功后立即重算日程/天气/路线信号，刷新仍有效的通知并淘汰旧通知。
- Blob：PDF、论文、生成图片、阅读库资产索引。
- Migration：本地 SQLite 只读导出；一次性 `/migration` 只调用 Conversation Store/LangGraph Store，文件只调用官方 Blob SDK。

## 4. 安全约束

- 所有运行状态固定写入 `local-user` 工作区；前端不能覆盖该所有者。
- 会话 ID 必须限制长度并由 Makers Conversation Store/Checkpointer 作为事实源。
- 高风险副作用只读取服务端冻结 Action，不接收浏览器重传完整参数。
- Provider 调用前写幂等账本；成功后先持久化结果再更新 UI。
- 网络超时视为结果未知，进入 `reconciliation_required`。

## 5. 不进入生产的内容

- 已删除的 FastAPI、SQLite Repository、WebSocket、Supervisor 和 Scheduler。
- 本地 `tmeet` CLI、系统 Keychain 和 `meeting-bridge/`。
- 旧 `/api` 前端 Transport fallback。
- 自建会话数据库、对象存储、Cron、通用队列、通用 Trace 或分布式锁服务。

迁移期间只保留独立的 SQLite 只读导出工具，不再保留旧运行时代码。导出工具不能进入 EdgeOne 构建、运行时依赖或发布门槛；数据验收完成后删除 `LEGACY_IMPORT_SECRET`，使导入入口不可用。
