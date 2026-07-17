# 元宝主动式 Agent 最新分支能力差距审查与测试 CASE

> **归档说明（2026-07-15）**：本文审查的是旧 FastAPI 本地分支，不再是 Makers 生产“最新分支”。当前能力与测试规划见 [`CURRENT_ARCHITECTURE_AND_REFACTOR_PLAN.md`](CURRENT_ARCHITECTURE_AND_REFACTOR_PLAN.md)。

> 审查日期：2026-07-11  
> 仓库：`wangjr20210114-hue/-ai-`  
> 审查分支：`origin/agent/proactive-runtime-refactor-v2`  
> 审查提交：`822ec32e08e3660a2e6fd458e235c6d3ca32dc02`  
> 对照文档：`元宝主动式Agent_现有能力盘点与目标架构设计 (1).docx` V1.0

## 1. 结论摘要

最新分支已经完成主动式 Agent 的主要“软件骨架”：持久 Event/Run/Action、确认快照、唯一 Executor、Supervisor/Scheduler、三类 Collector、通知、记忆/反馈/预算、本地鉴权、SSRF、备份恢复均有真实代码，并且仓库现有自动化检查全部通过。

但它还没有达到目标文档所定义的完整产品级闭环。当前最准确的定位是：

- **架构骨架完成度约 80%**：目标核心对象、表、服务和主调用链大部分已存在。
- **可长期可靠使用完成度约 55%–60%**：消息可靠投递、前端状态恢复、统一 Provider 边界、文件流式处理、预算前置决策、远程副作用核对等仍有缺口。
- **自动化验收覆盖约 35%–40%**：后端核心状态链覆盖较好，但前端只有 3 个 reducer 测试；大量 REST/WS/组件、真实浏览器链路和 Provider 条件测试没有覆盖。

以上百分比是按“代码存在 25% + 行为自动化 35% + 重启/错误/用户可见闭环 40%”加权的工程判断，不是代码行数比例。

当前不建议继续大规模增加新 Skill。应先完成 P0/P1 的可靠性与统一接线，否则功能越多，绕行链和不可恢复状态越多。

## 2. 审查证据与质量基线

| 检查项 | 结果 | 说明 |
| --- | --- | --- |
| 远端最新分支 | 通过 | 重新 fetch 后，最新远端仍为 `agent/proactive-runtime-refactor-v2`，提交时间 2026-07-11 21:11:46 +08:00 |
| 后端 unittest | **47/47 通过** | 使用 `requirements.lock` 的锁定依赖，在独立审查环境复跑 |
| 前端 Vitest | **3/3 通过** | 仅覆盖 `appState` reducer |
| ESLint | 通过 | 零错误 |
| TypeScript | 通过 | `tsc -b` 通过 |
| Vite production build | 通过 | 主 JS 约 1,342 KB，gzip 约 395 KB；存在大于 500 KB 拆包警告 |
| GitHub Actions | 已存在 | 后端 Python 3.11、前端 Node 22，包含测试、lint、build |
| Word 目标文档结构化读取 | 完成 | 465 个段落、135 张表均已提取 |
| Word 逐页视觉审查 | 未完成 | 当前环境缺少 LibreOffice/soffice，不能生成逐页 PNG；不影响能力文本比对，但未验证文档版式 |
| 真实 Provider E2E | 未执行 | 缺少本次审查专用 Key、额度和腾讯会议沙箱；不能据此宣称真实外部链路已通过 |

## 3. 已基本没问题、可以进入验收测试的模块

“可以测试”表示具备真实实现和可重复自动化证据，可以开始产品验收；不表示无需继续补边界测试。

| 模块 | 当前证据 | 建议验收重点 |
| --- | --- | --- |
| FastAPI 生命周期与组合根 | 完整 lifespan E2E 通过；启动会迁移、装配 Supervisor、鉴权和恢复服务 | 正常启动、后台组件启动失败时健康页降级、优雅关闭 |
| SQLite 迁移器 | 迁移幂等、旧表接管、旧消息无损迁移测试通过 | 用真实旧库副本升级并核对行数与约束 |
| 固定本地身份与基础持久化 | 固定 `local-user`、默认会话、消息重载测试通过 | 浏览器刷新、后端重启后历史仍存在 |
| Event / Run / Observation Repository | 去重、状态转换、租约、重试、取消、恢复均有自动化测试 | 并发领取、终态不可回退、Observation 顺序 |
| PendingAction 不可变确认 | 快照哈希、版本、过期、取消、重复确认测试通过 | 旧 version 409、篡改快照拒绝、重复确认不重复执行 |
| 单一 Executor 主链 | 会议/生图旧直调接口已 409 阻断；确认后由 Executor 执行 | 同一 Action 只执行一次、失败与核对状态可见 |
| Provider 调用账本 | 已覆盖“Provider 成功落账、Action 提交前崩溃”的恢复测试 | 成功账本恢复、started→unknown、不盲目重试 |
| Supervisor / Scheduler | 周期维护、租约、checkpoint 自动化通过 | 后端持续运行时回收过期任务，重启后继续领取 |
| 日程 Collector | 临近、逾期、冲突批次测试通过 | 无用户消息时产生去重通知 |
| 旅行天气 Collector 基础 | 风险匹配与 Provider 失败不覆盖 checkpoint 测试通过 | 真实天气源失败、恢复、重复天气不重复提醒 |
| 本地鉴权与 CORS 基础 | Token 持久、REST/WS 鉴权、WS subprotocol 测试通过 | 非回环访问、错误 Origin、Token 不进入 URL/日志 |
| SSRF 安全 HTTP | 私网、非 HTTP、重定向、Content-Type、响应大小测试通过 | IPv6、DNS rebinding、多跳重定向、压缩炸弹边界 |
| 备份与重启恢复 | 备份—暂存—重启恢复往返、ZIP 路径穿越测试通过 | 大文件、损坏清单、磁盘不足、恢复前安全副本 |
| ModelGateway 基础 | text/json/stream、usage、取消前检查、认证错误测试通过 | 超时、429、额度、非法 JSON、流中断 |
| 记忆/反馈/Usage Repository | 确认、版本、敏感标记、导出删除、反馈幂等、预算持久测试通过 | API 409、清空、导出、重复 feedback |

## 4. 已拥有但功能仍较窄、需要继续开发的模块

### 4.1 P0：消息持久化与审计关联

**现状问题**

- 后端 `AgentExecutor._execute_streaming_skill()` 先保存 AI 消息元数据，其中包含 `run_id`、`intent`、Provider request id 和 usage。
- 前端 `useWebSocket.ts` 收到 `stream_end` 后，又调用 `saveConversationMessage()` 保存同一消息 ID。
- `conversation_repo.save_message()` 的 `ON CONFLICT` 会以客户端 metadata 覆盖服务端 metadata，导致消息与 Run、Provider、Usage 的审计关联丢失。

**开发方案**

- 修改 `backend/database/repositories/conversation_repo.py`
  - 新增 `merge_message_metadata(existing, incoming, source)`。
  - 服务端保留字段 `run_id`、`intent`、`provider_request_id`、`usage` 禁止被客户端覆盖。
  - `save_message()` 增加 `metadata_authority: Literal["server", "client"]`。
- 修改 `frontend/src/hooks/useWebSocket.ts`
  - 删除 AI `stream_end` 后的二次持久化；服务端消息以 bootstrap/消息 API 为准。
  - 客户端仅持久化尚未发送给 Agent 的本地草稿或上传展示卡，并使用不同资源类型。
- 新增 `backend/tests/test_message_authority.py`
  - `test_client_cannot_overwrite_server_run_metadata()`。
  - `test_duplicate_server_save_is_idempotent()`。
- 新增 `frontend/src/hooks/useWebSocket.persistence.test.ts`
  - 断言服务端完成消息不会再次 POST `/messages`。

**开发后自测现象**

发送普通聊天后，数据库 `messages.metadata` 中始终包含正确 `run_id/intent/usage`；刷新页面后 UI 数据仍恢复；客户端重复收到 `stream_end` 不改变审计字段。

### 4.2 P0：WebSocket 可靠投递、游标补发与断线恢复

**现状问题**

- `WSClient.send()` 在未连接时静默丢弃消息。
- 输入栏会先持久化用户消息，再尝试 WebSocket 发送；断线窗口内会出现“消息存在但没有 Event/Run”。
- 协议没有 cursor、sequence、replay、客户端 ACK 和指数退避；通知/Run 主要依赖 5 秒轮询。

**开发方案**

- 新增迁移 v9：
  - `client_events(id, conversation_id, type, payload, status, created_at, acknowledged_at)`。
  - `ws_outbox(sequence, conversation_id, type, payload, created_at)`。
  - `messages.client_message_id` 唯一索引。
- 新增 `backend/application/message_delivery_service.py`
  - `ingest_client_message(conversation_id, client_message_id, text)`：消息、Event、Run 同一事务或可恢复 inbox。
  - `publish(envelope)`：持久化 outbox 后再尝试实时发送。
  - `replay(conversation_id, after_cursor)`：按 sequence 补发。
  - `acknowledge(client_message_id)`：返回已创建的 event/run。
- 修改 `backend/api/websocket.py`
  - 增加协议版本、cursor、`client_event.ack`、`resume`。
  - Transport 只调用 delivery/application service。
- 修改 `frontend/src/services/websocket.ts`
  - `sendOrQueue(msg): Promise<Ack>`。
  - 本地待发送队列、指数退避、心跳超时、cursor 持久化。
- 新增 `backend/tests/test_ws_delivery.py` 和 `frontend/src/services/websocket.test.ts`。

**开发后自测现象**

发送瞬间拔网线，UI 显示“待发送”；恢复网络后只创建一个 Event/Run；刷新或重连后补齐遗漏的 Run/Notification，重复 envelope 不重复渲染。

### 4.3 P0：统一文件应用服务与真正流式上传

**现状问题**

- `FileApplicationService` 已创建，但 `main.py` 和 `/api/files` 没有使用它。
- `store_upload()` 虽接收 AsyncIterator，仍把所有 chunks 放入列表并 `b"".join()`，不是常量内存上传。
- `/api/paper/upload` 仍 `await file.read()`，形成第二条上传链，且没有统一触发 FileCollector。
- 缺少文件删除生命周期和其引用处理。

**开发方案**

- 修改 `backend/application/file_application_service.py`
  - `store_upload()` 改为边读边写 `tempfile.SpooledTemporaryFile` 或临时文件，同时累计 size/SHA-256。
  - 新增 `finalize_pdf(temp_path, metadata)`、`delete_file(file_id, owner_id)`。
  - `recover_missing_file()` 禁止读取任意用户路径，改接受受控恢复目录中的候选对象。
- 修改 `backend/main.py`：装配 `FileApplicationService` 到 `app.state`。
- 修改 `backend/api/file_routes.py`：只委托 `FileApplicationService.store_upload()`。
- 修改 `backend/api/paper_routes.py`：删除重复上传实现或委托 `/api/files` 同一服务。
- 新增 `backend/tests/test_file_application_service.py`。

**开发后自测现象**

上传接近 50MB PDF 时进程内存不会同比增加 50MB；超限文件在读完整文件前被拒绝；两条入口得到相同 file_id、校验和与 Collector 事件；数据库失败时临时文件被清理。

### 4.4 P1：Transport/Provider 统一收敛

**现状问题**

- WebSocket 主链已收敛，但旅游 REST 仍直接调用 `hunyuan_service`。
- 论文附加功能 `_stream_llm()` 直接使用 `httpx` 和 DeepSeek 配置，绕过 ModelGateway、Usage、统一取消和统一错误。
- `agent/runtime.py` 仍保留内存 Runtime；`agent/core/*` 是兼容 wrapper，增加认知成本。
- 前端 `api.ts` 仍保留已废弃 `createMeeting()`、`generateImage()` 客户端。

**开发方案**

- 新增 `backend/application/travel_application_service.py`
  - `analyze_request()`、`generate_plan()`、`save_plan()`、`write_schedule_action()`。
- 新增 `backend/application/paper_application_service.py`
  - `search()`、`ingest_file()`、`stream_operation()`、`question_answer()`。
- 修改 `backend/api/routes.py`、`paper_routes.py`：只做 DTO/HTTP 转换。
- 修改 `frontend/src/services/api.ts`：删除废弃副作用客户端，按领域拆为 `agentApi.ts`、`travelApi.ts`、`paperApi.ts`、`systemApi.ts`。
- 在无外部调用点依赖旧 Runtime 后，删除 `AgentRuntime` 与无价值 wrapper；保留一轮弃用日志再删除。
- 新增架构测试：API 层禁止导入 Provider 实现、禁止直接 `httpx.AsyncClient`。

**开发后自测现象**

同一搜索/论文/模型请求从 REST 或 WS 进入时得到相同错误码、usage 和取消行为；全仓搜索不到 API 层直接 Provider/HTTP 调用；废弃会议/生图接口仍明确返回 409 或在版本升级后删除。

### 4.5 P1：预算必须进入计划与所有 Provider 调用

**现状问题**

- `UsageService.check_budget()` 目前只在 `Executor.execute_action()` 调用。
- 普通聊天、翻译、搜索、论文等模型调用没有统一 hard budget 拦截。
- soft budget 的“超限需确认”没有进入异步 `PolicyEngine`，目前只是注释承诺。

**开发方案**

- 新增 `backend/agent/policy/budget_rule.py`
  - `evaluate(estimated_cost, usage_summary, preferences)`。
- 将 `AgentPolicy.decide()` 改为 async，注入 `UsageService` 或预先计算的 PolicyContext。
- 在 `ModelGateway.complete_*`/`stream_text` 最终 Provider 调用前执行 hard budget 二次校验。
- 给每个 Skill 增加 `estimate_usage()`/`estimated_cost_cny()`。
- 新增 `test_budget_policy.py`：soft→确认、hard→拒绝、off→允许、并发预算竞争。

**开发后自测现象**

hard budget 超限时聊天和生图都不会发出 Provider 请求；soft budget 超限时 UI 显示费用与确认；Action 确认后仍按冻结费用上限执行，若预算被另一任务消耗则显示明确冲突而不是静默超支。

### 4.6 P1：前端 Agent 状态与管理界面

**现状问题**

- Run/Action/Notification 没进入全局规范化 store；Activity Center 每 5 秒全量轮询。
- 缺少目标文档要求的 `useRun/useActions/useNotifications`，无乱序/重复事件合并。
- Action 卡只显示 JSON 输入，未完整展示风险、费用、可逆性、过期时间和来源。
- 通知后端有 snooze，前端没有“稍后提醒”；偏好只能开关，不能编辑静默时段、上限、冷却。
- Job 后端支持 pause/resume，前端不提供；失败 Run 缺少 retry 按钮。
- 记忆后端支持编辑/清空，前端只支持删除/导出。
- 后端支持会话列表/新建，前端没有新建、切换、重命名会话。

**开发方案**

- 新增：
  - `frontend/src/store/agentState.ts`
  - `frontend/src/hooks/useRun.ts`
  - `frontend/src/hooks/useActions.ts`
  - `frontend/src/hooks/useNotifications.ts`
  - `frontend/src/components/agent/RunTimeline.tsx`
  - `frontend/src/components/agent/PendingActionCard.tsx`
  - `frontend/src/components/agent/NotificationCenter.tsx`
  - `frontend/src/components/profile/AutomationSettings.tsx`
  - `frontend/src/components/profile/MemoryEditor.tsx`
  - `frontend/src/components/chat/ConversationSwitcher.tsx`
- 所有 REST 初始状态与 WS 增量事件进入同一 reducer，并按 version/sequence 去重。
- 为 409、过期、取消、重试、snooze、偏好保存增加组件测试。

**开发后自测现象**

刷新 Action 页面后状态恢复；重连收到乱序事件不会回退终态；用户能在卡片上看清风险/费用/过期时间；可稍后提醒、暂停 Collector、重试失败 Run、编辑/清空记忆、切换会话。

### 4.7 P1：副作用远程核对

**现状问题**

Provider 成功响应落入本地账本后可恢复；但 Provider 已实际成功、进程在写账本前崩溃时只能 `reconciliation_required`，不能自动查询远程真实状态。会议/生图 Adapter 也未真正传递幂等键给 Provider。

**开发方案**

- 新增 `backend/providers/contracts.py`
  - `execute(input, idempotency_key)`。
  - `find_by_idempotency_key(key)`。
  - `get_result(external_resource_id)`。
- 新增 `backend/providers/tencent_meeting.py`、`hunyuan_image.py`。
- 修改 `AgentExecutor.reconcile_unknown_side_effect()`：先查远端，再决定 recovered/failed/manual_review。
- 新增 Provider 合约测试与崩溃点注入测试。

**开发后自测现象**

在“远端成功、写本地账本前”强制终止进程，重启后系统查到同一外部资源并补全成功；若 Provider 不支持查询，明确进入人工核对且按钮不可重复执行。

### 4.8 P1：测试体系扩充

**现状问题**

- 47 个后端测试偏重 happy path 和核心仓储；未覆盖多数 REST/WS/组件边界。
- 前端只有 1 个测试文件、3 个 reducer 用例。
- 没有 Playwright 浏览器 E2E、真实 Provider 条件套件、迁移矩阵和故障注入矩阵。

**开发方案**

- 新增 `backend/tests/contract/`、`integration/`、`e2e/` 分层。
- 新增 `frontend/src/**/*.test.tsx` 与 `e2e/*.spec.ts`。
- 新增 `scripts/run_conditional_e2e.py`，按 Provider 环境变量显式 opt-in。
- CI 增加覆盖率门槛：后端核心 domain/repository ≥80%，前端 Agent reducer/API ≥75%；浏览器 E2E 使用 fake Provider。

**开发后自测现象**

PR 无外网即可完成确定性 E2E；真实 Provider 测试单独显示 skipped/passed，不阻塞普通 PR；故意破坏版本冲突、WS 补发或租约代码会稳定触发测试失败。

## 5. 尚未开发或基本未形成产品闭环的模块

| 优先级 | 模块 | 当前状态 | 应新增的核心文件/函数 | 开发后验收现象 |
| --- | --- | --- | --- | --- |
| P1 | WebSocket outbox/inbox 与游标补发 | 未实现 | `message_delivery_service.py::publish/replay/acknowledge`；`ws_outbox_repo.py`；前端 `sendOrQueue/resume` | 断线期间消息不丢，重连只补一次 |
| P1 | 多会话产品 UI | 后端仅有 list/create；前端未实现 | `ConversationSwitcher.tsx`；API `rename/archive`；store `SET_ACTIVE_CONVERSATION` | 可新建、切换、重命名，会话数据互不串线 |
| P1 | Provider 远程对账 | 本地账本有，远程查询无 | `providers/contracts.py::find_by_idempotency_key/get_result` | 崩溃后自动找到已创建会议/图片 |
| P2 | 通用步骤级工作流引擎 | 未实现 | `agent/workflow/models.py`；`workflow_runtime.py::start_step/checkpoint/resume/compensate` | 旅游计划中途重启后从最后完成步骤继续 |
| P2 | 论文页码级索引、引用与 OCR | 未实现 | `documents/indexer.py`、`ocr_worker.py`、`citation_service.py` | 扫描 PDF 可后台 OCR，回答带准确页码引用 |
| P2 | 邮件/系统日历/企业消息 Collector | 未实现 | `collectors/calendar_collector.py`、`email_collector.py`、`im_collector.py` 与授权 Setup | 无聊天消息时可从已授权外部源触发，关闭开关后不采集 |
| P2 | 可确认、可回滚的策略提案 | 只有建议 DTO，不会落地 | `policy/rule_proposal.py`、`policy_version_repo.py`、`RuleProposalCard.tsx` | 三次负反馈后生成提案；用户确认才生效；可回滚 |
| P2 | 搜索证据冲突与逐句引用 | 仅结果列表/来源 | `search/evidence_graph.py`、`citation_binding.py`、确定性 ranker | 每个关键结论可点击来源；冲突来源并列展示 |
| P3 | 指标后端、trace 与外部告警 | 仅日志/健康快照 | `observability/metrics.py`、OTel instrumentation、告警 adapter | 可查看延迟、失败率、队列积压与预算趋势 |
| 范围外 | 多用户/组织/分布式高可用 | 明确未实现 | 账户、租户、RBAC、分布式锁、外部 DB | 只有产品转云时再立项，不应混入当前本地版本 |

## 6. 建议开发顺序

| 顺序 | 优先级 | 交付包 | 进入下一步的门槛 |
| --- | --- | --- | --- |
| 1 | P0 | 消息 metadata 权威、WS 可靠投递/补发 | 断线、重复、刷新、重启四类消息测试全绿；不存在“消息有、Run 无” |
| 2 | P0 | FileApplicationService 真接线、统一上传 | `/api/files` 与论文入口共享同一服务；常量内存；失败无残留 |
| 3 | P1 | REST/WS Provider 收敛、删除绕行 | API 层禁止直接 Provider/httpx；所有模型调用有统一错误、usage、取消 |
| 4 | P1 | 预算前置 Policy 与远程副作用核对 | soft/hard/off、崩溃核对用例通过 |
| 5 | P1 | 前端规范化状态与管理 UI | Action/Run/Notification/Memory/Conversation 浏览器 E2E 通过 |
| 6 | P1 | 测试矩阵与覆盖率门禁 | 确定性 Playwright E2E 进入 CI；真实 Provider 套件可选运行 |
| 7 | P2 | 工作流、论文索引、外部 Collector、策略版本 | 按业务价值逐项独立立项，不并行铺开 |

## 7. 当前已有功能测试 CASE 表

说明：`A` 表示仓库已有自动化证据；`M` 表示应立即人工执行；`N` 表示建议新增自动化。真实 Provider CASE 必须使用测试账号/额度，不能在普通 CI 中执行。

| CASE ID | 模块 | 类型 | 前置条件 | 操作步骤 | 预期现象 | 当前证据 |
| --- | --- | --- | --- | --- | --- | --- |
| BAS-001 | 启动 | A/M | 空临时目录 | 启动 FastAPI lifespan | 自动建库、生成 token、Supervisor 启动，健康接口为 ok/degraded 而非静默失败 | A |
| BAS-002 | 鉴权 | A | 服务已启动 | 不带 token 请求 `/api/system/health` | 返回 401，不泄露内部信息 | A |
| BAS-003 | Token Setup | A/M | 回环地址、允许 Origin | 请求 `/api/setup/access-token` | 仅回环+白名单 Origin 成功；Token 不在 URL | A |
| BAS-004 | 迁移 | A | 旧版数据库副本 | 连续执行两次迁移 | 第二次无重复表/列/数据，旧消息行数不变 | A |
| BAS-005 | 关闭 | N | 有运行中 Supervisor | 停止应用 | Supervisor、Gateway、数据库连接优雅关闭，无悬挂任务 | N |
| MSG-001 | 用户消息 | M/N | WS 正常 | 发送“你好” | 先持久化 user message，再创建唯一 Event/Run，返回流式 AI 消息 | 部分 A |
| MSG-002 | 重复消息 | N | 相同 client message id | 重发同一 WS envelope | 只存在一个 user message、Event 和 Run | 部分 A |
| MSG-003 | 刷新恢复 | M | 已完成聊天 | 刷新浏览器 | 历史消息完整，streaming=false，无重复消息 | A/M |
| MSG-004 | 后端重启 | M | 已完成聊天 | 重启后端再刷新 | 消息仍在，默认会话不变 | A/M |
| MSG-005 | 断线发送 | N | 关闭 WS 后保持页面 | 输入并发送消息，再恢复 WS | 目标应为自动补发并只创建一个 Run；当前预计会暴露消息已存但 Run 缺失 | 缺口 |
| MSG-006 | AI 审计 metadata | N | 完成一次模型聊天 | 查询 messages 表和 Run | message metadata 保留 run_id/usage/provider；当前可能被前端覆盖 | 缺口 |
| RUN-001 | Run 状态机 | A | 创建 Event | 顺序推进 created→classified→planned→policy_checked→queued→executing→succeeded | 每步有 Observation，终态不可回退 | A |
| RUN-002 | 并发领取 | N | 一个 queued Run | 两 worker 同时 claim | 只有一个成功并获得 lease | 部分 A |
| RUN-003 | 纯计算过期恢复 | A | executing 且 lease 过期 | 运行 maintenance | 在 attempt 限制内重新排队 | A |
| RUN-004 | 用户取消 | A/M | 模型流执行中 | 点击取消 | Provider 流终止，Run=cancelled，消息不继续增长 | A |
| RUN-005 | 失败重试 | M/N | 构造 retryable failed Run | 点击 retry | attempt+1、重新 queued；超过上限拒绝 | 部分 A |
| ACT-001 | 会议建议 | M | tmeet 可用或 fake | 输入明确会议时间 | 只创建 waiting_confirmation Action，不创建真实会议 | A/M |
| ACT-002 | Action 快照 | A | 已有建议卡 | 对比 UI 参数、snapshot、执行输入 | 规范化输入一致，hash 可复算 | A |
| ACT-003 | 旧版本确认 | A/M | Action version 已变化 | 用旧 version 确认 | 409；不执行 Provider | A |
| ACT-004 | 重复确认 | A | 同一 action/version | 并发或连续确认两次 | 只有一次成功；只产生一个 provider_call | A |
| ACT-005 | Action 过期 | A/M | expires_at 已过 | 点击确认 | 409/expired；Run 同步终止 | A |
| ACT-006 | Action 取消 | A/M | awaiting_confirmation | 点击取消 | Action、Run 均 cancelled；之后不能确认 | A |
| ACT-007 | 生图预算 | M/N | 设置 hard budget 小于预计费用 | 确认生图 | Provider 不被调用，Action/Run 显示预算错误 | 代码有/缺专测 |
| ACT-008 | 外部结果未知 | A | started 调用无成功账本 | 让租约过期 | reconciliation_required，系统不自动重试 | A |
| ACT-009 | 成功账本恢复 | A | provider_call=succeeded，Action 未提交 | 重启/maintenance | 自动补全 Action/Run succeeded | A |
| COL-001 | 日程临近 | A/M | 30 分钟内未完成日程 | 等待 Collector 或手动触发 job | 产生一次 upcoming 通知 | A |
| COL-002 | 日程逾期 | A/M | 已过开始时间且未完成 | 运行 Collector | 产生 overdue 通知，不重复刷屏 | A |
| COL-003 | 日程冲突 | A/M | 两日程重叠 | 运行 Collector | 通知包含双方标题和冲突原因 | A |
| COL-004 | 天气风险 | A/M | 旅行期有户外日程，fake 天气恶化 | 运行天气 Collector | 产生受影响日程通知 | A |
| COL-005 | 天气源失败 | A | 已有旧 checkpoint | Provider 抛错 | Job 可重试，旧 checkpoint 不被空结果覆盖 | A |
| COL-006 | 文件上传事件 | M/N | 有合法 PDF | 上传文件 | 文件保存后产生 file.uploaded Event/Run/Notification | 代码有/缺 E2E |
| NOT-001 | 通知去重 | A | 相同 dedup_key | 重复处理信号 | 只有一条通知 | A |
| NOT-002 | 冷却 | M/N | cooldown>0 | 短时间内生成同类来源通知 | 第二条被 suppressed，Run 记录原因 | 代码有/缺专测 |
| NOT-003 | 静默时段 | M/N | 当前时间设为 quiet hours | 产生非紧急通知 | 通知持久化且 snoozed_until 指向静默结束 | 代码有/缺专测 |
| NOT-004 | 每日上限 | M/N | daily_limit=1 | 连续产生两条通知 | 第二条 suppressed；高优先级核对错误可绕过 | 代码有/缺专测 |
| NOT-005 | 已读/忽略 | M | 有未读通知 | 点击已读、忽略 | read_at/dismissed_at 持久化；忽略记录反馈 | M |
| NOT-006 | 稍后提醒 | N | 有通知 | 点击“稍后提醒” | snoozed_until 更新并在到期后重新可见；当前前端无按钮 | 缺口 |
| FILE-001 | 合法 PDF | A/M | 文本型 PDF | 上传 | 校验签名、提取文本、记录页数/hash，刷新可打开 | A/M |
| FILE-002 | 伪 PDF | M/N | 扩展名 pdf、内容非 PDF | 上传 | 422，不落盘、不入库 | 代码有/缺专测 |
| FILE-003 | 超大 PDF | M/N | >50MB | 上传 | 读到上限即拒绝，无临时残留 | 部分实现 |
| FILE-004 | 重复 PDF | A/M | 同一内容不同文件名 | 上传两次 | 复用 hash/受控去重，不产生不一致索引 | A/M |
| FILE-005 | 文件丢失恢复 | A/M | 索引存在、磁盘文件删除 | 重启/恢复 | hash 一致才恢复；不一致拒绝 | A |
| FILE-006 | ZIP 路径穿越 | A | 恶意备份 ZIP | 暂存恢复 | 在解压前拒绝，不写出安全目录 | A |
| SKL-001 | 普通聊天 | M | 模型 Key 可用 | 多轮问答 | 使用持久历史，流式输出，记录 usage | 部分 A |
| SKL-002 | 翻译 | M/N | 模型 Key 可用 | 输入中英互译 | 意图正确，长文本边界明确，错误统一 | 缺专测 |
| SKL-003 | 聚合搜索 | A/M | fake 或真实搜索源 | 搜索一个时效问题 | 显示进度、来源、最终答案；单源失败可降级 | 部分 A |
| SKL-004 | 论文搜索 | A/M | fake/真实 arXiv | 搜索论文 | 不调用本机 HTTP 自己；返回论文列表 | A |
| SKL-005 | 论文 SSE | M/N | DeepSeek 可用 | 翻译/总结/问答 | 当前应验证 direct httpx 的错误、usage、取消不一致，并作为收敛回归基线 | 缺口 |
| SKL-006 | 旅游生成 | M/N | 模型/地图可用 | 生成多日旅游计划 | 保存计划、路线和日程；失败不伪装成功 | 缺专测 |
| MEM-001 | 记忆提案 | A/M | 创建候选记忆 | 确认前查询 memories | 不进入长期记忆；确认后写入 | A |
| MEM-002 | 记忆版本冲突 | A | 旧 version 更新 | 提交修改 | 409，不覆盖较新值 | A |
| MEM-003 | 敏感记忆 | A/M | key 含 token/密码 | 创建提案 | 标记 sensitive，仍需确认 | A |
| MEM-004 | 编辑/清空 | M/N | 已有记忆 | 在 UI 编辑、清空 | 后端已有 API；当前 UI 缺入口 | 缺口 |
| FDB-001 | 反馈幂等 | A | 同 client_feedback_id | 提交两次 | 只保存一条，返回相同或一致结果 | A |
| FDB-002 | 规则建议 | A/M | 同来源连续负反馈 | 提交第三次 dismiss | 返回需确认的暂停/冷却建议，但不自动改策略 | A |
| USE-001 | Usage 记录 | A | fake 模型返回 tokens | 完成调用 | token、model、provider、cost 写入一次 | A |
| USE-002 | 日/月预算 | A/M | 设置预算偏好 | 刷新/重启 | 偏好与汇总持久化，告警阈值正确 | A |
| USE-003 | 普通模型 hard budget | N | hard budget 已超 | 发起聊天 | 目标应拒绝 Provider；当前只在 Action Executor 检查 | 缺口 |
| SEC-001 | 私网 SSRF | A | URL 指向 127.0.0.1/私网/metadata IP | 请求抓取 | 在 DNS/连接前拒绝 | A |
| SEC-002 | 重定向 SSRF | A | 公网 URL 302 到私网 | 请求抓取 | 逐跳重新校验并拒绝 | A |
| SEC-003 | 日志脱敏 | M/N | 带 token/query 的请求 | 查看日志 | 不出现 token、Secret、完整敏感 query | 部分实现 |
| BAK-001 | 备份恢复 | A/M | 有 DB、文件、记忆 | 导出、暂存、重启 | 数据与文件 hash 一致，旧运行目录有安全副本 | A |
| BAK-002 | 损坏备份 | M/N | 修改 ZIP 中文件 | 暂存恢复 | 校验失败；当前运行数据不变 | 部分 A |
| UI-001 | Action Center | M/N | 有 Action/Run/Notification | 打开“我的”面板 | 状态可见，确认/取消/已读可操作 | 缺组件自动化 |
| UI-002 | 断线重连 | N | 页面正常 | 断网 10 秒再恢复 | 目标应指数退避并游标补发；当前仅固定 2 秒重连 | 缺口 |
| UI-003 | 乱序事件 | N | 模拟重复/乱序 Run 更新 | 推送事件 | 终态不回退、不重复插入 | 未实现规范化 store |
| UI-004 | 生产构建 | A | 依赖已安装 | lint、test、build | 全通过；允许记录但不忽略 500KB 拆包警告 | A |

## 8. 最终判定

最新分支不是“只有骨架”的版本：M1–M3 的核心可靠执行链已经基本成立，M4–M6 也完成了若干重要纵向切片。它可以开始模块级和受控端到端测试。

但当前文档中的“v4.0.0 / M1–M6 核心完成”表述仍偏乐观。至少在以下门槛全部通过前，不宜承诺“长期运行、消息不丢、所有能力统一可恢复”：

1. 修复 AI 消息 metadata 被客户端覆盖。
2. 建立 WS inbox/outbox、ACK、cursor/replay，消除“消息有、Run 无”。
3. 真正接线 FileApplicationService 并移除论文重复上传链。
4. 论文/旅游 REST 进入统一 ApplicationService、ModelGateway、错误、Usage 与取消边界。
5. 预算进入所有 Provider 调用和计划 Policy。
6. 补齐前端规范化状态、关键组件测试和确定性浏览器 E2E。

完成上述 P0/P1 后，项目才适合进入“扩展新 Collector、工作流引擎、OCR/引用”等 P2 功能阶段。
