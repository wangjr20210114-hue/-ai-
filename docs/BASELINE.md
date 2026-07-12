# 项目基线说明

> **状态更新（2026-07-11）**：本文件记录的是改造前 M0–M2 基线，已归档。当前实现已完成主动 Runtime、Supervisor、Collector、ModelGateway、Memory/Feedback/Usage、本地安全和备份恢复等核心改造。请以 [`IMPLEMENTATION_STATUS.md`](IMPLEMENTATION_STATUS.md) 和根目录 [`README.md`](../README.md) 为当前事实来源。

## 基线目标

本基线保留当前已有的前后端功能、Agent 抽象、旅游/搜索/论文等新增模块，作为后续主动式 Agent 改造的唯一源码起点。

本次基线整理只处理仓库卫生、状态说明和实施计划，不修改现有业务行为，也不把本地运行数据纳入版本控制。

## 纳入基线

- FastAPI 后端、React 前端和 SQLite 数据访问代码。
- `agent/` 中的事件、计划、策略、运行时、响应器和技能注册机制。
- `agents/travel/` 中的旅游领域实现。
- `skills/` 中的 Chat、Search、Image、Meeting、Travel、Paper、Translation 技能实现。
- 当前前端交互和样式实现。
- 环境变量示例、依赖清单和项目说明。

## 不纳入基线

- `.env` 和任何真实 API 密钥。
- SQLite 数据库、WAL/SHM 文件和用户上传内容。
- `backend/venv`、`frontend/node_modules` 和构建产物。
- `.codebuddy`、`.playwright-cli` 等本地工具缓存。
- Python、测试、类型检查和覆盖率缓存。

## 2026-07-10 M1 验证状态

| 检查项 | 结果 | 说明 |
| --- | --- | --- |
| 后端源码编译 | 通过 | 排除随项目复制的虚拟环境后，Python 源码可编译 |
| 后端应用导入 | 通过 | `backend/main.py` 可成功导入并创建 FastAPI 应用 |
| 前端正式构建 | 通过 | TypeScript 与 Vite 8 生产构建通过 |
| 前端 lint | 通过 | ESLint 零错误、零警告 |
| 自动化测试 | 通过 | 后端 13 个 unittest、前端 3 个 Vitest 用例通过 |
| 生产依赖审计 | 通过 | `npm audit --omit=dev` 为 0 漏洞 |
| 浏览器视觉冒烟 | 通过 | 实测消息发送、刷新恢复、WebSocket 重连和后端进程重启恢复 |

## M0 已完成内容

- 修复全部前端类型和 lint 问题，没有关闭质量规则。
- 引入 Vitest 和后端标准库测试入口，覆盖 reducer、策略、运行时和迁移器。
- 增加 GitHub Actions CI，在提交和拉取请求上执行后端编译/测试及前端 lint/测试/构建。
- 引入带版本表、事务和幂等行为的 SQLite 迁移器，现有数据库可被版本化接管。
- 增加 `backend/requirements.lock`，前端继续使用 `package-lock.json`。
- 升级 Vite、Vitest 和 PDF.js，消除已发现的生产及开发依赖漏洞。
- 修复路线 CSS 缺失选择器和路线坐标类型错误。

## M1 已完成内容

- 创建并持久化固定 `local-user` 与 `default-conversation`，前端不再生成随机 session。
- 新增 conversations/messages API，完整 UI 消息及技能元数据可在刷新、重连和重启后恢复。
- WebSocket 连接恢复时从数据库重建模型对话历史。
- 新增真实 PDF 上传：文件签名、50MB 限制、500 页限制、加密检测和文本提取。
- 使用 SHA-256 去重、随机存储名、路径隔离和持久 files 索引。
- files 索引仍在但磁盘文件丢失时，同哈希 PDF 可沿用原文件 ID 恢复，不破坏已有引用。
- 论文下载、阅读、分析和问答接口可从 files 表回源，不再依赖内存缓存。
- 启动时兼容迁移旧随机 session 数据及已收藏的旧论文文件。
- 兼容 M0 前的旧 `messages(session_id, scenario, ...)` 表：保留原表并幂等导入默认会话。
- 旅游计划、日程、论文收藏等旧 API 保留 session 参数兼容性，但服务端统一按 `local-user` 读写和校验归属。

## M2 实施中内容

- migration 3 新增 `agent_events`、`agent_runs`、`agent_observations` 和 `pending_actions`。
- 新增持久 Runtime Repository，覆盖事件去重、Run 状态迁移、观察记录和有限重试。
- PendingAction 使用规范化参数快照、SHA-256 快照哈希、版本确认和唯一幂等键。
- 新增 Run 查询、待确认 Action 列表、确认、取消和重试 API。
- 已覆盖确认版本冲突、重复确认、过期联动、取消和有限重试测试；会议/生图执行链尚未迁移。

## 已知核心限制

1. 当前只有用户消息会真实触发 Agent；定时、天气、文件等事件尚无采集器和后台调度器。
2. 持久 Runtime 数据层和 API 已建立，但现有 Orchestrator 仍使用内存 Runtime，尚未完成接线。
3. 会议和生图的旧确认按钮仍直接调用 REST，尚未迁移到 PendingAction 执行链。
4. 通用 PDF 已真实上传并提取文本，但“文件到达即主动摘要”需在 M3 接入事件调度。
5. 默认监听地址、CORS 和无认证接口不适合暴露到局域网。
6. README 中部分主动服务、偏好学习和成本追踪描述仍超前于实现。

## 基线使用规则

- 后续改造以 `docs/PROACTIVE_AGENT_REFACTOR_PLAN.md` 为准。
- 每个里程碑必须独立通过构建、测试和验收后再进入下一阶段。
- 新增副作用操作必须使用持久化 Action、确认快照和幂等键。
- 不继续扩充新 Skill，直到持久化运行时、主动触发和确认闭环完成。
- 个人版保持单进程 FastAPI + SQLite，不引入不必要的分布式组件。
