# 个人主动式 Agent 完整改造计划

> **归档说明（2026-07-15）**：本文是旧 FastAPI + SQLite 本地版的历史目标设计，不再作为 Makers 生产改造计划。当前计划见 [`CURRENT_ARCHITECTURE_AND_REFACTOR_PLAN.md`](CURRENT_ARCHITECTURE_AND_REFACTOR_PLAN.md)。


## 实施状态

- **M0 基线稳定化：已完成（2026-07-10）**
- **M1 持久身份、会话和文件：已完成（2026-07-10）**
- **M2 持久 Agent Runtime 与确认闭环：实施中（2026-07-10）**
- M3–M6：待实施

## 1. 目标与边界

### 1.1 产品目标

把当前“用户发消息后自动选择工具”的对话应用，改造成一个可在个人电脑长期运行、能够感知变化、判断机会、征得授权、执行动作、记录结果并从反馈中调整的主动式 Agent。

正式版必须形成以下闭环：

```text
感知 -> 事件持久化 -> 机会检测 -> 策略过滤 -> 计划/确认
     -> 执行 -> 观察/恢复 -> 通知 -> 用户反馈 -> 偏好更新
```

### 1.2 个人版约束

- 单用户、低并发，优先可靠性和可理解性，不追求大规模吞吐。
- 保持单个 FastAPI 应用和 SQLite；允许同进程后台任务，不引入消息中间件和微服务。
- 默认只监听本机，用户数据和密钥保存在本地。
- LLM 负责语义判断和内容生成；权限、幂等、预算、时间窗口等关键约束必须由确定性代码控制。
- 所有主动行为必须能解释“为什么触发、读取了什么、将执行什么”。

### 1.3 非目标

- 不建设多租户、组织、角色权限和企业审计系统。
- 不追求完全自治；外部写操作、付费操作和不可逆操作默认需要确认。
- 不在核心闭环完成前继续增加大量新 Skill。
- 不把向量数据库作为第一阶段前置条件。

## 2. 完成标准

项目只有同时满足以下条件，才可称为“功能完整的个人主动式 Agent”：

1. 应用重启后，用户身份、对话、任务、待确认动作和通知都能恢复。
2. 没有用户消息时，至少三类事件源可以产生主动建议。
3. 同一事件不会重复打扰；支持冷却、每日上限和免打扰时间。
4. 用户确认的参数与最终执行参数完全一致。
5. 任何副作用操作都有幂等键、执行记录和可见结果。
6. 任务支持超时、取消、有限重试和失败恢复。
7. 用户可以查看、删除、导出自己的记忆和运行记录。
8. 前后端构建、测试、类型检查和核心端到端流程全部通过。
9. 默认仅本机可访问，文件上传、密钥和本地接口具有基本安全边界。

## 3. 首期主动场景

先把三个高价值场景做完整，再把同一机制推广到其他 Skill。

### 3.1 日程守护

- 事件：日程临近、时间冲突、逾期未完成、当天行程变化。
- 行为：提前提醒、给出准备清单、建议改期或标记冲突。
- 权限：提醒可自动；修改日程必须确认。

### 3.2 旅行守护

- 事件：未来旅行临近、目的地天气明显变化、计划中的室外活动不适合。
- 行为：提示风险并生成替代安排草案。
- 权限：生成草案可自动；写入日程必须确认。

### 3.3 文件到达即处理

- 事件：用户真实上传 PDF/文档。
- 行为：安全存储、提取文本、自动生成摘要和可继续提问的阅读卡片。
- 权限：读取和摘要可自动；向外发送或删除原文件必须确认。

搜索、翻译、论文、聊天和生图第一阶段继续作为被动能力；会议创建和生图保留确认机制。

## 4. 目标架构

### 4.1 模块边界

```text
api/
  http.py                 REST 查询、确认、取消和管理接口
  websocket.py            会话消息和实时事件推送
agent/
  events.py               统一事件模型
  scheduler.py            持久调度和到期任务扫描
  collectors/             日程、天气、文件等事件采集器
  opportunity.py          规则优先的机会检测
  planner.py              生成结构化 AgentPlan
  policy.py               权限、预算、冷却和免打扰策略
  executor.py             唯一 Skill 执行入口
  runtime.py              持久状态机、租约、恢复和审计
  memory.py               个人资料、事实、摘要和反馈
  notifier.py             应用内通知及未来桌面通知适配
skills/
  base.py                 参数模型、权限、幂等和执行协议
  travel.py / meeting.py / ...
services/
  外部 API 和本地 CLI 的纯适配层
database/
  migrations/             可重复执行的数据库迁移
  repositories/           按领域拆分的数据访问
```

### 4.2 单进程运行模型

- FastAPI lifespan 启动一个后台 Supervisor。
- Supervisor 周期性领取 SQLite 中到期的 Job，并使用租约避免重复执行。
- Collector 只负责产生标准事件，不直接调用 Skill。
- Runtime 负责状态迁移，Executor 不直接修改任务状态。
- WebSocket 断开不影响任务运行；通知先落库，连接恢复后补发。
- SQLite 保持 WAL 模式；所有状态迁移使用短事务。

## 5. 核心领域模型

### 5.1 事件 AgentEvent

```json
{
  "id": "evt_xxx",
  "type": "schedule.due",
  "source": "schedule_collector",
  "user_id": "local-user",
  "subject_id": "schedule_xxx",
  "payload": {},
  "dedup_key": "schedule.due:schedule_xxx:2026-07-10T14:30",
  "occurred_at": 0,
  "received_at": 0
}
```

要求：事件不可变；`dedup_key` 唯一；payload 有按事件类型定义的 Pydantic 模型。

### 5.2 计划 AgentPlan

计划必须包含：

- 触发事件和触发原因。
- Skill 名称和已验证参数。
- 拟执行步骤和预期输出。
- 风险、权限、费用上限、超时和失败策略。
- 对用户展示的确认摘要。
- 参数快照哈希，防止确认后被重新生成。

### 5.3 动作 PendingAction

状态机：

```text
draft -> awaiting_confirmation -> confirmed -> executing
     -> succeeded | failed | cancelled | expired
```

规则：

- `confirmed` 后只能执行保存的参数快照。
- 确认接口接收 `action_id + version`，避免确认旧版本。
- 每个外部副作用都携带稳定 `idempotency_key`。
- `expired/cancelled/succeeded` 不允许再次执行。
- 重试沿用原 Action 和幂等键，不创建第二个外部资源。

### 5.4 运行 AgentRun

状态机：

```text
created -> classified -> planned -> policy_checked
       -> waiting_confirmation | queued | executing
       -> succeeded | failed | cancelled | skipped
```

每次迁移写入 observation，包括耗时、模型、Token、外部调用、错误分类和用户可见消息。

## 6. SQLite 数据设计

首轮迁移至少新增：

| 表 | 作用 | 关键字段 |
| --- | --- | --- |
| `users` | 稳定本地身份 | `id`, `display_name`, `timezone`, `created_at` |
| `conversations` | 会话 | `id`, `user_id`, `title`, `summary`, `updated_at` |
| `messages` | 对话历史 | `id`, `conversation_id`, `role`, `content`, `metadata` |
| `agent_events` | 事件收件箱 | `id`, `type`, `dedup_key`, `payload`, `processed_at` |
| `agent_runs` | Agent 运行 | `id`, `event_id`, `status`, `plan_json`, `lease_until` |
| `agent_observations` | 审计轨迹 | `run_id`, `status`, `step`, `payload`, `error`, `ts` |
| `pending_actions` | 待确认和副作用动作 | `id`, `run_id`, `snapshot`, `version`, `idempotency_key`, `status` |
| `scheduled_jobs` | 持久任务 | `id`, `job_type`, `next_run_at`, `payload`, `lease_until` |
| `notifications` | 主动通知收件箱 | `id`, `user_id`, `run_id`, `read_at`, `dismissed_at` |
| `memories` | 明确事实和偏好 | `id`, `kind`, `key`, `value`, `confidence`, `source` |
| `feedback` | 采纳/忽略/纠正 | `id`, `run_id`, `action`, `reason`, `created_at` |
| `usage_records` | 模型及费用 | `run_id`, `provider`, `model`, `tokens`, `cost`, `latency_ms` |
| `files` | 文件持久索引 | `id`, `sha256`, `path`, `mime`, `size`, `owner_id` |

要求：

- 使用迁移版本表，不再只依赖 `CREATE TABLE IF NOT EXISTS`。
- JSON 字段统一序列化入口并设版本。
- 删除父记录时明确级联策略。
- 提供数据库备份、恢复和健康检查命令。

## 7. 主动触发与打扰控制

### 7.1 Collector 协议

每个 Collector 实现：

```text
collect(checkpoint) -> events, next_checkpoint
```

- Collector 必须可重复运行。
- checkpoint 和事件同时持久化。
- 外部 API 失败不删除旧 checkpoint。
- Collector 不生成自然语言，不直接通知用户。

### 7.2 机会检测

采用两级机制：

1. 确定性规则：时间窗口、状态变化、冲突和文件类型。
2. 可选 LLM 判断：只用于排序、摘要和语义相关性，输出结构化 JSON。

不要在第一版实现“奖励模型”。先记录足够反馈，再决定是否需要模型训练或复杂评分。

### 7.3 打扰预算

策略最少包含：

- 同 `dedup_key` 永不重复通知。
- 同类建议默认冷却 4 小时，可配置。
- 默认每日主动通知上限 5 条。
- 默认免打扰 22:30–08:00，紧急事件除外。
- 连续忽略同类建议后自动降低优先级。
- 每张通知显示来源、触发原因、时间和将执行的动作。

## 8. 权限与安全策略

| 动作 | 默认策略 | 示例 |
| --- | --- | --- |
| 本地只读观察 | Auto | 读取内部日程、检查任务状态 |
| 生成本地草案 | Auto/Suggest | 行程替代方案、文档摘要 |
| 消耗明显额度 | Confirm | 生图、大批量全文翻译 |
| 创建外部资源 | Confirm | 创建会议、写入外部日历 |
| 修改/删除用户数据 | Confirm | 删除日程、覆盖计划 |
| 凭证、支付、不可逆高风险动作 | Deny 或强确认 | 修改授权、购买、公开发布 |

实施要求：

- 默认绑定 `127.0.0.1`，首次启动生成本地访问令牌。
- WebSocket 和 REST 使用相同身份验证。
- session ID 不再承担身份认证职责。
- 参数在进入 Plan 前、执行前各验证一次。
- 文件名与存储路径分离；校验 MIME、文件签名、大小、页数和解压限制。
- API 错误不向前端暴露堆栈、密钥、内部路径和供应商原始响应。
- 安装 CLI、打开浏览器授权等环境变更移到显式 Setup 流程。

## 9. 记忆与反馈

### 9.1 记忆分层

- 会话记忆：当前会话最近消息。
- 摘要记忆：长会话压缩摘要，可追溯到原消息。
- 明确事实：家乡、时区、常用出发地等用户确认事实。
- 偏好：通知时间、旅行风格、常用语言等可编辑设置。
- 临时状态：正在规划的旅行、待确认动作，不进入长期偏好。

### 9.2 写入原则

- 敏感信息默认不自动写入长期记忆。
- 推断偏好必须带置信度和来源，低置信度先询问。
- 用户可以查看、修改、删除、全部清空和导出。
- 不直接让原始对话无限增长进入模型上下文。

### 9.3 反馈闭环

记录 `accepted / dismissed / corrected / reverted`，先用可解释规则调整：

- 采纳提升同类机会优先级。
- 忽略降低优先级并延长冷却。
- 纠正更新事实或参数映射。
- 撤销降低自动化级别，必要时退回强确认。

## 10. Skill 统一改造

### 10.1 统一协议

每个 Skill 必须声明：

- `InputModel` 和 `OutputModel`。
- 支持的事件类型和能力说明。
- 权限、风险、预算和超时。
- 是否产生副作用及幂等策略。
- `plan()`、`execute()`、`render()` 和可选 `compensate()`。
- 可测试的服务依赖接口。

Transport handler 不得再优先绕过 Skill；REST 和 WebSocket 都调用同一个应用服务。

### 10.2 现有 Skill 处理顺序

1. 会议：先完成不可变确认快照、幂等创建和授权 Setup。
2. 文件/论文：真实上传、持久文件索引、重启恢复和后台解析。
3. 旅游：结构化计划、日程写入确认、天气变化替代方案。
4. 搜索：来源模型、引用校验、超时和部分结果降级。
5. 生图：额度确认、任务状态和结果持久化。
6. 翻译/聊天：统一模型网关、历史摘要和错误处理。

删除 WebSocket 内部对 `127.0.0.1:8000` 的自调用，改为直接调用共享应用服务。

## 11. API 与前端改造

### 11.1 核心 API

```text
POST   /api/conversations
GET    /api/conversations/{id}/messages
POST   /api/events                     # 本地受信事件入口
GET    /api/runs/{run_id}
GET    /api/actions?status=awaiting_confirmation
POST   /api/actions/{action_id}/confirm
POST   /api/actions/{action_id}/cancel
POST   /api/runs/{run_id}/retry
GET    /api/notifications
PATCH  /api/notifications/{id}
GET    /api/memories
PUT    /api/memories/{id}
DELETE /api/memories/{id}
GET    /api/settings/automation
PUT    /api/settings/automation
```

所有修改接口返回更新后的资源和版本，不只返回 `{ok: true}`。

### 11.2 WebSocket 事件

统一为带版本的 envelope：

```json
{
  "version": 1,
  "type": "run.updated",
  "id": "msg_xxx",
  "ts": 0,
  "payload": {}
}
```

支持：

- 连接后按游标补发丢失消息。
- `run.created/updated/completed`。
- `action.awaiting_confirmation/expired`。
- `notification.created`。
- 心跳、协议版本和明确错误码。

### 11.3 前端页面

- 稳定的对话历史和新建会话。
- “Agent 动态”面板：运行步骤、来源、耗时和错误。
- “待确认动作”列表：确认前显示完整参数、费用和可逆性。
- “主动通知中心”：采纳、忽略、稍后提醒。
- “自动化设置”：免打扰、每日上限、各场景开关和权限等级。
- “记忆管理”：查看、编辑、删除、导出。
- 长任务允许取消，断线重连后继续显示真实状态。

## 12. 可靠性与可观测性

### 12.1 错误分类

- `configuration_error`
- `authentication_error`
- `quota_exhausted`
- `rate_limited`
- `timeout`
- `validation_error`
- `external_service_error`
- `cancelled`
- `internal_error`

只有瞬时网络错误和限流可以自动重试；校验、授权和配额错误不得盲目重试。

### 12.2 重试与恢复

- 指数退避加随机抖动。
- 每个 Skill 有最大尝试次数和总超时。
- 进程启动时扫描 `executing` 且租约过期的 Run。
- 对未知结果的副作用操作先查询外部状态，再决定是否重试。
- 用户取消时传播 cancellation token，并将晚到结果标为已取消后的观察结果。

### 12.3 日志和成本

- 结构化日志包含 `run_id/event_id/action_id`，不记录密钥和完整敏感正文。
- 记录每次模型调用的 provider、model、tokens、估算费用、延迟和错误类型。
- 前端展示单任务成本、当天成本和预算告警。
- 设置每日/每月软预算；超限后把高成本自动动作降级为确认。

## 13. 测试策略

### 13.1 后端

- 单元测试：策略矩阵、状态机、去重、冷却、参数验证、费用计算。
- Repository 测试：临时 SQLite、迁移、并发领取、重启恢复。
- Skill 合约测试：每个 Skill 共用一套输入、超时、错误和幂等测试。
- 集成测试：使用假的 LLM、地图、天气和会议适配器，不依赖真实网络。
- 安全测试：资源归属、路径穿越、超大文件、错误信息泄露。

### 13.2 前端

- Reducer、WebSocket 重连、流式消息和确认状态单元测试。
- 关键组件交互测试：确认、取消、忽略、稍后提醒、任务恢复。
- 类型检查和 lint 必须零错误。

### 13.3 端到端

至少覆盖：

1. 用户创建日程，后台在到期窗口生成一次提醒。
2. 提醒被忽略后冷却生效。
3. 会议计划确认后使用原参数只创建一次。
4. 确认前修改计划会导致旧版本确认失败。
5. 长任务中重启服务，恢复后继续或明确失败。
6. 上传 PDF，重启后仍能打开、总结和问答。
7. WebSocket 断开重连后补齐任务状态。

## 14. 里程碑与实施顺序

### M0：基线稳定化（已完成，2026-07-10）

任务：

- 修复 11 个 TypeScript 构建错误和全部 lint 错误。
- 增加后端测试框架、前端测试框架和基础 CI 脚本。
- 锁定 Python 依赖，移除复制的虚拟环境依赖假设。
- 增加数据库迁移框架和开发/测试配置。
- 把 README 能力状态改成“已实现/部分实现/规划中”。

验收：

- 后端源码、导入、单元测试全部通过。
- 前端 build、lint、单元测试全部通过。
- 全新目录可按 README 一次安装并启动。

### M1：持久身份、会话和文件（已完成，2026-07-10）

任务：

- 创建固定 `local-user`，首次启动生成并持久保存。
- 持久化 conversations/messages，重连和刷新恢复历史。
- 实现真实文件上传、哈希、元数据、路径隔离和重启恢复。
- 为现有数据提供一次性迁移或兼容读取。

验收：

- 刷新、重连、重启后对话和个人数据仍存在。
- 上传的 PDF 重启后仍可打开和处理。
- 不再用随机 session ID 作为资源所有权边界。

### M2：持久 Agent Runtime 与确认闭环（6–8 人日）

任务：

- 实现 events/runs/observations/actions 表和 Repository。
- 将 Agent Runtime 改为持久状态机。
- 实现确认、取消、过期、重试和幂等 API。
- 会议和生图首先迁移到新 Action 协议。
- 增加启动恢复和租约机制。

验收：

- 用户确认的快照与最终执行参数字节级一致。
- 重复确认不会重复创建外部资源。
- 进程在等待确认或执行中重启后状态可恢复。

### M3：主动调度与通知（6–9 人日）

任务：

- 实现 Supervisor、scheduled_jobs 和事件收件箱。
- 实现日程 Collector、旅行天气 Collector、文件上传事件。
- 实现规则机会检测、去重、冷却、免打扰和每日预算。
- 实现持久通知中心和 WebSocket 补发。

验收：

- 无用户消息时三个首期场景均能产生主动通知。
- 同一事件只通知一次，重启不会重复。
- 免打扰和每日上限可验证生效。

### M4：Skill 收敛与服务可靠性（7–10 人日）

任务：

- 统一 Skill 输入输出模型和唯一 Executor。
- 移除 transport handler 绕行和本机 HTTP 自调用。
- 引入统一模型网关、超时、错误分类、重试和取消。
- 依次迁移旅游、论文、搜索、翻译和聊天。
- 外部服务使用可替换 Adapter，测试中完全可伪造。

验收：

- 所有 Skill 通过共享合约测试。
- REST、WebSocket、后台事件使用同一执行入口。
- 配额、授权、超时和取消不会被错误标记为成功。

### M5：记忆、反馈和自动化控制（5–7 人日）

任务：

- 实现会话摘要、明确事实、偏好和临时状态分层。
- 实现采纳、忽略、纠正、撤销反馈。
- 实现自动化设置、记忆管理和数据导出/清空。
- 使用规则根据反馈调整冷却和优先级。

验收：

- 用户能解释、编辑和删除所有长期记忆。
- 连续忽略会降低同类通知频率。
- 清空个人数据后不存在孤立记忆和通知。

### M6：安全、成本与发布验收（4–6 人日）

任务：

- 本机绑定、本地令牌、统一资源归属校验。
- 文件、日志、错误和密钥安全加固。
- Token/费用持久化、预算和可视化。
- 数据库备份恢复、健康检查和诊断导出。
- 完成端到端、故障注入和长时间运行测试。

验收：

- 全部完成标准和端到端用例通过。
- 连续运行 72 小时无重复副作用、任务泄漏和不可恢复状态。
- 新机器按文档能够安装、初始化、备份和恢复。

## 15. 工作拆分与提交规则

- 每个里程碑单独分支或连续的小提交，不混合大规模格式化。
- 数据库迁移、领域模型、Repository、服务、API、前端按依赖顺序提交。
- 每个行为变更同时提交测试和文档。
- 不以“接口已定义”作为完成；必须有真实调用链和验收用例。
- 不允许通过关闭 lint/typecheck 来达到绿色构建。
- 每个里程碑结束时更新 `docs/BASELINE.md` 的验证状态。

## 16. 风险与取舍

| 风险 | 应对 |
| --- | --- |
| 主动通知过多导致用户关闭功能 | 规则优先、每日上限、冷却、免打扰、来源解释 |
| LLM 参数漂移导致错误副作用 | Pydantic 校验、不可变快照、确认版本和幂等键 |
| 单进程崩溃丢任务 | SQLite 持久状态、短事务、租约和启动恢复 |
| 外部 API 不稳定或额度耗尽 | Adapter、超时、错误分类、预算和降级 |
| 记忆错误长期污染结果 | 来源、置信度、用户可编辑、明确/推断分离 |
| 改造期间继续堆叠旧架构 | 冻结新 Skill，先完成 Runtime 和 Executor 收敛 |

## 17. 推荐的首个开发批次

第一批只执行 M0，不同时改主动调度。建议按以下顺序：

1. 修复前端 TypeScript 构建错误。
2. 修复 lint 并建立前后端测试入口。
3. 锁定依赖和规范本地环境。
4. 引入数据库迁移但不改变业务行为。
5. 为当前 WebSocket、会议确认、日程 CRUD 和论文文件建立回归测试。

M0 全绿后再进入持久身份和 Runtime；这能显著降低在不稳定基线上重构核心 Agent 的风险。
