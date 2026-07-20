# 旧 FastAPI 用户能力清单

本文件只保留迁移验收所需的用户结果，不保留 FastAPI 路由和 SQLite 表作为目标架构。`backend/` 在迁移期间是只读领域参考，不是生产备用链。

| 旧能力 | Makers 等价状态 | 迁移决策 |
| --- | --- | --- |
| WebSocket 对话与消息保存 | 已等价 | 使用 SSE、Conversation Store、Checkpointer |
| 会话列表与切换 | 已等价 | Makers Conversation Store |
| 联网搜索、来源和媒体 | 已等价并增强 | WSA rich search + 视觉复核 |
| 地点、路线、日程 | 已等价并增强 | Makers Workspace + 腾讯位置服务 |
| 腾讯会议创建 | 可选、推迟验收 | 已改用官方服务端 API；个人部署不要求申请企业凭据 |
| AI 生图 | 已等价并增强 | 支持图生图、版本、Blob、ZIP |
| PDF 上传与阅读 | 核心等价 | Blob 直传和浏览器阅读；OCR 尚未实现 |
| 论文搜索、下载、翻译、总结、问答 | 核心等价 | Makers Paper/Reader；长任务恢复和页码引用待补 |
| 日程/天气/文件 Collector | 核心等价 | EdgeOne Cron + Signal Connector |
| Event、Run、Observation | 核心等价 | LangGraph Store 业务状态 |
| Notification、静默、冷却、稍后提醒 | 已等价 | Makers Proactive |
| Action 快照、幂等、未知结果阻断 | 已等价 | Makers Workspace Provider Ledger |
| Memory、Feedback、Usage、预算 | 已等价 | Makers Intelligence |
| 工作流、步骤依赖、失败补偿 | 核心等价 | Makers Proactive Workflow |
| Run 人工取消/重试 | 部分等价 | 工作流步骤已有入口；通用 Run 产品入口待补 |
| 旅行计划 CRUD 资产 | 数据可迁移，UI 待补 | TravelPlan 已进入 Workspace 持久状态；专用 CRUD 产品入口待补 |
| SQLite 备份/恢复 | 迁移链已实现 | 只读导出到 Conversation Store、LangGraph Store 和 Blob；真实库待执行 |
| 本地访问令牌 | 不迁移 | 当前个人演示固定所有者，不提供登录入口 |
| SQLite/WAL/进程锁 | 不迁移 | 属于旧实现，不是用户功能 |
| FastAPI/WebSocket/Supervisor | 不迁移 | 由 Makers Runtime、SSE、Cron 取代 |
| 本地 OSM 数据库 | 不原样迁移 | 保留“Provider 失败可降级”的用户结果，不部署本地数据库 |

## 退役判定

只有同时满足以下条件，相关旧代码才可删除：

1. 上表对应能力已通过自动化和 Preview 验收，或明确记录产品取消决定。
2. 旧数据已迁移并完成数量/哈希/抽样回读校验。
3. 生产前端不再调用旧路由。
4. Makers 部署和回滚不依赖旧服务。
