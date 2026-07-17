# FastAPI 退役与 Makers 最终迁移清单

> 日期：2026-07-16  
> 决策：`backend/` 即将弃用，不再作为发布回归门槛；Makers 是唯一生产运行时。
> 原则：不做旧 API 对齐；平台能力或当前 Makers 体验已覆盖且不影响产品的旧能力直接淘汰。

## 1. 已迁移，不再维护 FastAPI 对应实现

| FastAPI 能力 | Makers 事实源 |
|---|---|
| WebSocket 对话、对话/消息 CRUD | `agents/chat` SSE、Makers Checkpointer/Conversation Store、`cloud-functions/conversations` |
| 搜索、富媒体、地点、路线 | `agents/shared/rich_search.py`、`agents/places`、`agents/routes` |
| 日程 CRUD 和完成状态 | `agents/workspace` + 确认式 Action |
| 会议创建、生图 | Makers Action、Provider Ledger、`agents/image` |
| 论文搜索、下载、收藏、上传、阅读与问答 | `cloud-functions/papers`、`library`、`files`、`agents/reader` |
| Memory、Feedback、Usage、预算 | `agents/intelligence`、LangGraph Store |
| Event、Run、Notification、偏好、静默、稍后提醒 | `agents/proactive` + 左栏 Inbox |
| 日程/天气/路线/File Collector | Makers Cron + `agents/shared/proactive.py` + 外部 Signal Connector |
| 健康与业务指标 | `agents/system`；通用 Trace/日志复用 Makers/CLS |

## 2. 不做接口对齐：仅在真实产品需求出现时扩展

| 旧能力 | 当前判定 | 平台/现有能力 | 何时才需要新增 |
|---|---|---|---|
| Run 取消/重试 | 不迁旧 API | Makers 请求中止、LangGraph Checkpoint/Interrupt；主动业务步骤已有确定性 transition | 后台副作用任务出现真实人工恢复需求时，只增加业务 transition |
| 备份/恢复 | 不迁通用备份 API | Neon、Blob、Makers Store 分别使用平台持久化和备份能力 | 出现明确的数据可携带/账户注销要求时，做跨存储生命周期编排 |
| 旅行计划 CRUD | 不迁 | 对话 + 地点 + 路线 + 日程已覆盖当前体验 | 产品明确增加“我的行程”资产页时再设计 `TravelPlanV1` |
| 截断式论文全文任务 | 不迁 | 当前 Reader 和 Makers Agent 能处理交互式阅读 | 明确要求可恢复的整篇翻译/索引产品时重做分块 Job，不复制旧实现 |

因此本次 FastAPI 退役没有“必须补齐的同名接口”。验收目标是当前 Makers 功能零回退和主动 Agent 闭环成立，而不是旧路由数量一致。

## 3. 明确淘汰，不迁移

- FastAPI、Uvicorn、WebSocket transport。
- SQLite Repository、WAL、进程内锁和本地文件索引。
- 本地 Scheduler/Supervisor 常驻循环；改用 EdgeOne `schedules`。
- `/api/setup/access-token`；生产使用官方 Makers Auth 架构。
- 静态城市列表、内置 POI 和本地 OSM 回退；只接受可验证 Provider 结果。
- 旧 Sogou/多源搜索代理；使用 WSA 和 Makers 工具。
- `meeting/setup/install` 与设备登录态；云端只调用持久 Meeting Bridge。
- 已 deprecated 的 `/meeting/create`、`/image/generate` 旧路由。
- 通用备份服务、通用日志/Trace 服务；优先使用平台备份与 Makers/CLS 可观测。

## 4. 新发布门槛

发布只要求：

1. Makers Agent 单元/契约测试。
2. Cloud Functions 安全、租户和平台复用测试。
3. 前端单测、构建和 Lint。
4. EdgeOne 部署校验、生产冒烟和无浏览器 Cron 终验。

不再运行 `backend/tests`，也不因 FastAPI 兼容性阻塞 Makers 发布。`backend/` 只保留到迁移清单全部关闭，之后归档或删除。
