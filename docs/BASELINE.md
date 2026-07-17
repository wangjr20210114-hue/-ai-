# EdgeOne Makers 能力基线

> 基线提交：`d8d3c745a93e1009062cf2b16e152593746bc5b2`
> 评估日期：2026-07-17
> 生产目标：EdgeOne Makers 是唯一线上运行时；FastAPI/SQLite 只作为迁移期间的历史能力参考。

## 1. 基线原则

1. “功能不缩水”指用户能完成的任务、持久数据、安全确认和故障恢复语义不缩水，不要求保留旧 URL、WebSocket 或 SQLite 表。
2. 代码存在不等于可交付；只有进入 Makers 生产入口、通过自动化并完成预览环境验证的能力才标记为可部署。
3. 平台已有的运行时、会话、检查点、对象存储、定时任务、模型网关和可观测能力直接复用。
4. 外部副作用必须保留确认、冻结快照、幂等账本和未知结果阻断。
5. 旧数据在迁移校验通过前不得删除。

## 2. 当前用户能力

| 能力 | 代码状态 | 部署状态 | 主要事实源 |
| --- | --- | --- | --- |
| 多会话聊天、SSE、停止、刷新恢复 | 已实现并测试 | 待本分支预览复验 | `agents/chat`、`agents/messages`、`cloud-functions/conversations` |
| 联网图文回答 | 已实现并测试 | 依赖 WSA、视觉模型配置 | `agents/_shared/rich_search.py` |
| 地点、地图、道路路线、费用估算 | 已实现并测试 | 依赖腾讯地图服务端/前端 Key | `agents/places`、`agents/routes`、`agents/_shared/tencent_location.py` |
| 日程 CRUD 与确认式变更 | 已实现并测试 | 待预览复验 | `agents/workspace`、LangGraph Store |
| 腾讯会议创建 | 官方 API 适配已实现 | 最后阶段可选；未配置时不暴露工具 | `agents/_shared/side_effects.py` |
| 文生图、图生图、版本、Blob、ZIP | 已实现并测试 | 依赖混元 Key | `agents/image`、`ImageStudioCard.tsx` |
| PDF 上传、阅读库、论文助读 | 已实现核心链路 | PDF only；无 DOCX/OCR | `cloud-functions/files`、`library`、`papers`、`agents/reader` |
| 主动日程/天气/路线提醒 | 已实现并测试 | EdgeOne Cron 需无浏览器线上终验 | `agents/proactive`、`proactive-tick` |
| Notification、免打扰、每日上限、稍后提醒 | 已实现并测试 | 待预览复验 | `agents/_shared/proactive.py` |
| Memory、Feedback、Rule、Token 预算 | 已实现并测试 | 待预览复验 | `agents/intelligence` |
| 持久工作流、失败阻断、重试与补偿 | 已实现并测试 | 待预览复验 | `agents/_shared/proactive.py` |
| 单用户/多用户身份 | 已实现并测试 | 个人单用户无需 Neon；多用户 A/B 隔离待线上终验 | `cloud-functions/auth`、`auth/current-user.js`、`agents/_shared/auth.py` |
| SQLite 历史数据迁移 | 导出/导入链已实现并测试 | 真实数据数量、哈希、抽样回读待执行 | `tools/export_sqlite.py`、`agents/migration` |
| 业务健康视图 | 已实现 | Makers/CLS 告警待控制台配置 | `agents/system` |

## 3. 已知未完成项

### P0：已在本分支完成，待 CI 平台复核

- CI 已以 Makers Agent、Cloud Functions 和 EdgeOne 构建作为发布门槛。
- Neon 已统一为 `db/001_users.sql` 一份 Schema。
- 根 Python 直接依赖已锁定版本。
- 当前架构、能力基线、部署和迁移计划已有唯一事实源。

### P1：代码阻塞已解除，线上验收未完成

- 腾讯会议已改用官方服务端 API，外部 Meeting Bridge 和设备登录态已移除。
- 本分支未完成真实 EdgeOne 预览部署、环境校验、Cron 和双用户隔离终验。
- SQLite 迁移工具已完成，真实旧库迁移与 Preview 回读尚未执行。

### P2：产品增强但不阻塞核心迁移

- DOC/DOCX 转换、扫描 PDF OCR、页码级引用。
- 论文长任务的可恢复分块索引与全文处理。
- 阅读库 JSON 索引的并发写冲突防护。
- 前端 PDF、KaTeX、地图进一步动态拆包。
- 邮件、系统日历和企业 IM 的真实授权连接器。

## 4. 零缩水验收门槛

- 所有基线能力有至少一个自动化用例和一个预览环境用例。
- 生产入口不存在活动 FastAPI、Uvicorn、SQLite、`/api` 或 WebSocket fallback。
- 会议、日程等高风险副作用重复确认不会重复执行。
- Provider 超时或结果未知时进入人工核对，不能直接重试。
- Conversation、Workspace、Blob、Intelligence、Proactive 和连接器 Secret 按用户隔离。
- 浏览器关闭时 EdgeOne Cron 仍能推进 `last_tick`。
- 从全新 clone 只依赖文档声明的环境变量即可构建和部署。

## 5. 当前自动化基线

2026-07-17 本地结果：

- Makers Agent：53 项通过。
- SQLite 导出工具：2 项通过。
- Cloud Functions：9 项通过。
- 前端 Vitest：22 项通过。
- ESLint：通过。
- EdgeOne 模式生产构建：通过。
- 已知非阻塞项：主 JS chunk 约 1.36 MB。

这些结果不替代真实 Provider、平台 Cron、多用户和预览部署验收。
