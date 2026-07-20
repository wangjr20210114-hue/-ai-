# EdgeOne Makers 能力基线

> 当前业务分支：`agent/makers-native-persistence-fixes`（本轮变更待提交）
> 更新日期：2026-07-20
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
| 多会话聊天、SSE、停止、刷新恢复 | 已实现并测试 | Preview/Production 已连接并加载历史会话 | `agents/chat`、`agents/messages`、`cloud-functions/conversations` |
| 联网图文回答 | 已实现并测试 | 搜索前保留 LLM 语义规划；单轮富搜索只执行一次，查询合并并使用 Makers Store TTL 缓存；是否取图由规划器按理解价值决定 | `agents/chat/_capability_plan.py`、`agents/chat/_ui_tools.py`、`agents/_shared/rich_search.py` |
| 地点、地图、道路路线、费用估算 | 已实现并测试 | 腾讯结果与查询不匹配时回退 OSM；路线按用户缓存 6 小时 | `agents/places`、`agents/routes`、`agents/_shared/tencent_location.py` |
| 日程 CRUD 与确认式变更 | 已实现并测试 | 可用自然语言新增、改标题/描述/时间/地点、删除；地点修改必须来自地点库；不存在/不唯一目标会自然提示；变更后旧主动提醒同步刷新或失效 | `agents/workspace`、`agents/chat/_calendar_context.py`、LangGraph Store |
| 腾讯会议创建 | 官方 API 适配已实现 | 最后阶段可选；未配置时不暴露工具 | `agents/_shared/side_effects.py` |
| 文生图、图生图、版本、Blob、ZIP | 已实现并测试 | 支持选择或 Cmd/Ctrl+V 粘贴参考图；生成状态覆盖浏览器图片载入 | `agents/image`、`ImageStudioCard.tsx`、`InputBar.tsx` |
| PDF、图片上传、阅读库、论文助读 | 已实现核心链路 | PDF 上传后直接打开内置助读；阅读库支持手动分类与删除反馈；无 DOCX/OCR | `cloud-functions/files`、`library`、`papers`、`agents/reader` |
| 主动日程/天气/路线提醒 | 已实现并测试 | EdgeOne Cron 需无浏览器线上终验 | `agents/proactive`、`proactive-tick` |
| Notification、免打扰、每日上限、稍后提醒 | 已实现并测试 | 在线读取通过；真实 Cron 触发待跨日终验 | `agents/_shared/proactive.py` |
| Memory、Feedback、Rule、Token 预算 | 已实现并测试 | 待预览复验 | `agents/intelligence` |
| 持久工作流、失败阻断、重试与补偿 | 已实现并测试 | 待预览复验 | `agents/_shared/proactive.py` |
| 个人所有者身份 | 已实现并测试 | 固定 `local-user`，无注册登录或应用数据库 | `auth/current-user.js`、`agents/_shared/auth.py` |
| SQLite 历史数据迁移 | 导出/导入链已实现并测试 | 真实数据数量、哈希、抽样回读待执行 | `tools/export_sqlite.py`、`agents/migration` |
| 业务健康视图 | 已实现 | Makers/CLS 告警待控制台配置 | `agents/system` |

## 3. 已知未完成项

### P0：已在本分支完成，待 CI 平台复核

- CI 已以 Makers Agent、Cloud Functions 和 EdgeOne 构建作为发布门槛。
- 已删除 Neon、JWT、登录注册和租户隔离代码，个人演示不需要身份数据库。
- 根 Python 直接依赖已锁定版本。
- 当前架构、能力基线、部署和迁移计划已有唯一事实源。

### P1：代码阻塞与核心线上验收已完成

- 腾讯会议已改用官方服务端 API，外部 Meeting Bridge 和设备登录态已移除。
- 本分支已完成真实 EdgeOne Preview/Production、动态路由登记和个人工作区核心读取验收；真实 Cron 仍待专项终验。
- SQLite 迁移工具已完成，真实旧库迁移与 Preview 回读尚未执行。

### P2：产品增强但不阻塞核心迁移

- DOC/DOCX 转换、扫描 PDF OCR、页码级引用。
- 论文长任务的可恢复分块索引与全文处理。
- 阅读库 JSON 索引的并发写冲突防护。
- 前端 PDF、KaTeX、地图进一步动态拆包。
- 邮件、系统日历和企业 IM 的真实授权连接器（当前个人演示不提供）。

## 4. 零缩水验收门槛

- 所有基线能力有至少一个自动化用例和一个预览环境用例。
- 生产入口不存在活动 FastAPI、Uvicorn、SQLite、`/api` 或 WebSocket fallback。
- 会议、日程等高风险副作用重复确认不会重复执行。
- Provider 超时或结果未知时进入人工核对，不能直接重试。
- Conversation、Workspace、Blob、Intelligence 和 Proactive 均固定写入个人所有者工作区。
- 浏览器关闭时 EdgeOne Cron 仍能推进 `last_tick`。
- 从全新 clone 只依赖文档声明的环境变量即可构建和部署。

## 5. 当前自动化基线

2026-07-20 当前工作树结果：

- Makers Agent：75 项通过。
- SQLite 导出工具：2 项通过。
- Cloud Functions、验收持久化和平台约束：16 项通过。
- 前端 Vitest：34 项通过。
- ESLint：通过。
- EdgeOne 模式生产构建：通过。
- EdgeOne Preview `dph2wvagts0x`：构建成功，应用已连接，核心只读数据加载通过。
- 已知非阻塞项：主 JS chunk 约 1.52 MB，后续需要代码拆包优化。

这些结果不替代真实 Provider、平台 Cron 和预览部署验收。
