# 主动式 Agent 改造实现状态

> 更新日期：2026-07-11
> 实现分支：`agent/proactive-runtime-refactor`
> 对照文档：`元宝主动式Agent_现有能力盘点与目标架构设计` 与 `docs/PROACTIVE_AGENT_REFACTOR_PLAN.md`

## 1. 总体结论

本次改造已经完成架构文档中 M1–M6 的核心纵向闭环：

```text
持久资源 → 持久 Event/Run → 确定性 Policy → 不可变 Action
→ 单一 Executor → Supervisor/Scheduler → 主动 Collector/Notification
→ 记忆/反馈/预算 → 本地安全/备份/可观测性
```

当前系统已经具备“真正主动式 Agent”的基础软件属性：后台事件不依赖用户消息触发；状态可跨重启恢复；副作用先确认后执行；执行有幂等、租约和审计；通知可解释且受冷却、静默和上限约束；用户可以管理记忆、预算、取消任务和恢复数据。

它仍是**本地单用户版本**。外部 Provider 可用性、更多 Collector、通用可恢复工作流和多租户云安全不在本次完成范围内。

## 2. 里程碑完成情况

| 阶段 | 目标 | 状态 | 关键落地 |
| --- | --- | --- | --- |
| M1 | 身份、会话、消息、文件持久化 | 完成 | 固定 local-user、conversation/message、PDF 索引与恢复 |
| M2 | Runtime、Action、Executor | 完成 | Event/Run/Observation、不可变 Action、会议/生图单一执行链 |
| M3 | 主动感知、调度和通知 | 完成核心范围 | Supervisor、Scheduler、日程/天气/文件 Collector、机会检测和免打扰 |
| M4 | Skill 收敛和统一 Provider | 完成核心范围 | ModelGateway、标准错误、Chat/翻译/搜索/论文迁移、薄 WebSocket |
| M5 | Memory、Feedback、Usage | 完成 | 记忆提案确认、反馈幂等、预算偏好和前端管理 |
| M6 | 安全与产品化 | 完成核心范围 | 本地令牌、SSRF、安全取消、健康日志、校验备份和重启恢复 |

## 3. 已拥有且可直接测试的能力

### 3.1 持久资源

- 固定本地用户和默认会话。
- 用户与 AI 消息持久化，浏览器断线不再决定模型结果是否保存。
- PDF 文件签名、50MB 限制、500 页限制、加密检测、文本提取、哈希去重和文件丢失恢复。
- 旧消息表、旧随机 session 和旧论文文件迁移。

### 3.2 持久 Agent Runtime

- Event 使用唯一 `dedup_key` 去重。
- Run 状态机、Plan 哈希、执行 lane、attempt、lease owner/expiry 和终态时间。
- 每次状态变化与 Observation 同事务提交。
- 启动时扫描过期租约：纯计算 Run 可重排；未知副作用不盲重试。
- Run 查询、时间线、重试和显式取消 API。

### 3.3 安全副作用

- 会议和生图声明版本化输入模型。
- 用户确认的是后端冻结的 Action snapshot，而不是前端重新发送的参数。
- Snapshot SHA-256、Action version 和唯一 idempotency key。
- 前端只提交 `action_id + version`。
- 唯一 Executor 执行；成功结果先持久化，再做通知、Usage 或前端推送。
- 外部结果不确定时进入 reconciliation_required，不自动重复创建会议或图片。
- 已开始的外部副作用拒绝不安全取消。

### 3.4 主动运行

- Supervisor 持久领取后台 Run 和 Job。
- Scheduler 具备租约、checkpoint、失败次数和启动恢复。
- ScheduleCollector 产生临近、逾期和冲突事件。
- TravelWeatherCollector 识别旅行期内天气变化和户外风险，Provider 失败不覆盖旧 checkpoint。
- FileCollector 将真实上传转换成主动事件。
- OpportunityDetector 输出确定性原因、优先级和通知候选。
- Notification 支持去重、冷却、静默时段、每日上限、已读、忽略和稍后提醒。

### 3.5 模型与 Skill

- ModelGateway 统一 Provider 配置、非流式/流式/JSON 请求、错误分类和 Usage。
- Provider 认证、限流、额度、超时和响应结构错误具有稳定错误码。
- Chat、翻译、搜索和论文搜索不再由 WebSocket 编排。
- 搜索和论文 Skill 通过通用流事件发送进度、来源和最终结果。
- 论文搜索复用领域 Service，不再由后端 HTTP 调用自身 `127.0.0.1` 接口。
- 浏览器断开时模型继续执行并保存结果；用户显式取消才终止 CancellationToken。

### 3.6 用户控制与产品化

- 记忆先产生 proposal，用户确认后才写入；支持版本冲突、敏感度、导出和删除。
- 反馈具有客户端幂等键，并生成可解释的调整建议，不直接暗改高风险规则。
- Usage 按 Provider/操作记录 token、次数、单位和成本，支持日/月预算与 hard/soft/off。
- 自动生成本地访问令牌；REST 和 WebSocket 使用同一身份边界。
- Setup token 接口只允许回环客户端和白名单 Origin。
- 任意网页抓取经过协议、DNS/IP、逐跳重定向、Content-Type 和大小校验。
- 健康接口报告数据库、Supervisor、模型配置、认证和待恢复状态。
- 请求日志携带 request_id、状态码和耗时，不记录令牌或 URL query。
- 备份包含 SQLite 在线快照、托管文件和逐文件哈希，不包含 Secret；恢复在重启时原子执行并保留安全副本。

## 4. 已拥有但仍需扩展的能力

| 能力 | 当前边界 | 推荐扩展 |
| --- | --- | --- |
| 旅游规划 | 领域服务较丰富，但仍以一次性生成和 REST 表单为主 | 引入 WorkflowStep、步骤输入输出、checkpoint、局部重算和人工修改后续跑 |
| 搜索可信度 | 有多源检索和安全抓取 | 增加逐句 citation 绑定、来源新鲜度、冲突证据展示和可重复排序 |
| 论文阅读 | 搜索、下载、阅读和模型分析可用 | 增加分页索引、关键词/向量混合检索、后台索引任务和页码级引用 |
| PDF | 文本型 PDF 完整 | 增加沙箱 OCR、扫描件队列、恶意内容隔离和大文档增量索引 |
| 主动 Collector | 已有日程、天气、文件 | 增加系统日历、邮件、企业消息、浏览器授权事件和用户自定义规则 |
| 反馈学习 | 会记录反馈并提出建议 | 增加经用户确认的 RuleProposal、可回滚策略版本和离线评估 |
| 副作用核对 | 结果未知时保守阻止重试 | 对接腾讯会议/生图 Provider 的 request-id 或幂等键查询接口 |
| 长任务恢复 | 可取消、有限重试和租约恢复 | 模型流无法从 token 中点续传；长工作流应保存步骤级 checkpoint |
| 前端 | 管理界面已接入 | 增加独立 Action/Notification 页面、虚拟列表、无障碍和动态代码拆分 |

## 5. 尚未拥有的能力

- 多用户、组织、云端账户和远程访问控制。
- 分布式 worker、跨节点锁和高可用数据库。
- 邮件、操作系统通知、真实外部日历和企业 IM Collector。
- 任意复杂任务的通用 DAG/补偿工作流引擎。
- Provider 级未知副作用自动对账。
- 扫描 PDF OCR 和多模态文档索引。
- 完整 Playwright 浏览器端到端测试矩阵及真实 Provider 沙箱测试。
- 生产级指标后端、分布式 tracing 和外部告警平台。

## 6. 关键代码位置

| 目标 | 主要文件 |
| --- | --- |
| 应用入口和组件装配 | `backend/main.py` |
| 用户消息用例 | `backend/application/agent_application_service.py` |
| 主编排 | `backend/agent/orchestrator.py` |
| 唯一执行入口 | `backend/agent/executor.py` |
| 显式取消 | `backend/agent/cancellation.py` |
| Supervisor | `backend/agent/supervisor.py` |
| Scheduler | `backend/agent/scheduler.py`、`database/repositories/job_repo.py` |
| Collector | `backend/agent/collectors/` |
| Opportunity | `backend/agent/opportunity.py` |
| Policy | `backend/agent/policy/` |
| Runtime 状态唯一写入 | `backend/database/repositories/runtime_repo.py` |
| Action 用例 | `backend/application/action_service.py` |
| ModelGateway | `backend/services/model_gateway.py` |
| SSRF 安全客户端 | `backend/services/safe_http.py` |
| 本地认证 | `backend/security/local_auth.py` |
| 备份恢复 | `backend/services/backup_service.py` |
| 薄 WebSocket | `backend/api/websocket.py` |
| Action/Notification UI | `frontend/src/components/profile/AgentActivityCenter.tsx` |
| Memory/Usage UI | `frontend/src/components/profile/AgentIntelligencePanel.tsx` |
| 健康与恢复 UI | `frontend/src/components/profile/SystemSafetyPanel.tsx` |

## 7. 数据库迁移

| 版本 | 内容 |
| --- | --- |
| 1 | 原始旅游、日程、POI、缓存和论文表 |
| 2 | users、conversations、messages、files |
| 3 | agent_events、agent_runs、agent_observations、pending_actions |
| 4 | lease、execution lane、Action result、Provider request ID、reconciliation |
| 5 | scheduled_jobs、notifications、notification_preferences、usage_records |
| 6 | memories、memory_proposals、feedback_records |
| 7 | memory version/sensitivity、feedback client idempotency、usage preferences |
| 8 | provider_calls：副作用调用账本、请求/响应持久化与崩溃恢复核对 |

迁移使用版本表、事务和幂等建表；旧数据库由测试覆盖，不要求用户删除本地数据。

## 8. 验收结果

### 自动化结果

- 后端：**46/46 unittest 通过**。
- 前端：**3/3 Vitest 通过**。
- ESLint：通过，零错误。
- TypeScript 与 Vite 生产构建：通过。
- FastAPI/Uvicorn 真实启动：通过。
- 本地令牌引导：通过。
- `/api/system/health`：数据库与 Supervisor 状态通过。
- 已知非阻塞项：前端主 chunk 大于 500KB。

### 重点覆盖

- 旧数据库迁移和数据不丢失。
- Event 去重、状态冲突和不可变 Action。
- 重复确认不重复执行 Provider。
- 副作用租约过期进入人工核对。
- 流式断线仍持久化回答。
- 显式取消终止模型流并写入 cancelled。
- 日程三类事件和天气失败 checkpoint。
- Memory 乐观版本、敏感记忆、Feedback 幂等、Usage 预算。
- 私网/回环/元数据 URL、危险重定向、类型和响应大小拒绝。
- 本地令牌持久化、未授权拒绝和恶意 Origin 拒绝。
- 备份/恢复往返、Secret 排除和 ZIP 路径穿越拒绝。

## 9. Definition of Done 对照

| 文档要求 | 结果 |
| --- | --- |
| 身份、会话、文件、Job、Event、Run、Action、Notification 重启恢复 | 完成 |
| 至少三类主动来源 | 完成：日程、天气、文件 |
| 去重、冷却、每日上限、静默时段 | 完成 |
| 副作用确认参数不可变 | 完成 |
| 幂等、未知结果不盲重试 | 完成；自动 Provider 对账待扩展 |
| 长任务超时/取消/有限重试/重启恢复 | 完成核心；token 级续传不支持 |
| Opportunity 和 Notification 可解释 | 完成 |
| 记忆可查看、确认、删除、导出 | 完成 |
| Provider 错误统一 | 完成 |
| 本地安全、预算、备份和可观测性 | 完成核心 |
| 自动化测试和文档一致 | 完成 |

## 10. 后续优先级

1. 将旅游规划改造成可持久化 WorkflowStep，而不是继续增加新的单次 REST 功能。
2. 为腾讯会议和生图接入 Provider 查询接口，关闭 reconciliation 人工缺口。
3. 增加邮件/系统日历 Collector，但必须沿用 Event dedup、Policy 和 Notification 限流。
4. 为论文构建后台分页索引和页码级 citation。
5. 增加 Playwright E2E：确认后执行、刷新恢复、断线继续、取消、静默通知和备份恢复。
6. 前端动态导入 PDF Reader、地图和管理面板，降低首屏包体。
