# EdgeOne Makers 主动式 Agent 实现状态

> 更新日期：2026-07-16  
> 范围：当前 Makers 生产主链；不把 `backend/` 旧 FastAPI 能力计入完成度  
> 状态：代码与本地回归完成，生产定时触发需在部署后终验

## 1. 结论

本轮已经把系统从“页面内主动提示”改造成**可切换单用户/多用户的主动 Agent**：页面关闭后，EdgeOne cron 仍会触发后台扫描；Event、Run、Observation、Notification、工作流、记忆与反馈均持久化；高风险副作用仍需确认，并具备快照、幂等账本、未知结果阻断和人工补偿。

多用户采用腾讯官方 `makers-agents-auth` 架构：Neon 用户唯一索引、bcrypt、HttpOnly `jwt_token`、Edge Middleware 早拒、Agent 二次验签和租户 namespace。生产切换仍需配置身份环境变量后在线终验。

## 2. P0：最小主动闭环

| 任务点 | 状态 | 实现 |
| --- | --- | --- |
| 平台后台触发 | 已实现，待线上触发终验 | `edgeone.json` 配置 `Asia/Shanghai` 每小时 `/proactive-tick` Makers Function；函数补稳定系统会话后桥接 `/proactive` Agent |
| 持久 Event/Run/Observation/Notification | 已实现 | LangGraph Store 单用户 namespace；确定性 ID 和去重键 |
| 后端日程 Collector | 已实现 | 临近、冲突、紧接行程；页面不再计算机会 |
| Policy | 已实现 | 总开关、提醒类型、免打扰、每日上限、去重 |
| Notification Inbox | 已实现 | 未读、已读、忽略、稍后、原因、证据、下一步 |
| 触达 | 已实现基础层 | 持久站内 Inbox；页面打开时可授权浏览器系统通知 |

## 3. P1：可靠执行与垂直主动能力

| 任务点 | 状态 | 实现 |
| --- | --- | --- |
| Action 冻结快照 | 已实现 | 规范 JSON SHA-256、版本校验、确认后篡改拒绝 |
| 幂等与 Provider ledger | 已实现 | 全局幂等键；调用前写账本；未核对调用禁止重复 |
| lease/recovery | 已实现 | 执行租约；过期进入 `reconciliation_required`，不盲重试副作用 |
| 天气 Collector | 已实现 | 已核实坐标 → 腾讯天气；风险天气才提醒；失败只写 checkpoint |
| 路线 Collector | 已实现 | 已核实坐标 → 真实路线时长；衔接不足才提醒 |
| Run 时间线 | 已实现 | 左栏显示最近持久 Run；`/system` 输出状态聚合 |

## 4. P2：记忆、反馈和信号

| 任务点 | 状态 | 实现 |
| --- | --- | --- |
| 长期记忆 | 已实现 | 主模型只能提案；用户确认后才注入后续对话；可拒绝、删除、导出 |
| 反馈 | 已实现 | 接受、忽略、稍后进入持久反馈 |
| Rule Proposal | 已实现 | 连续忽略同类提醒后提出关闭规则；必须确认，不静默改策略 |
| Usage/预算 | 已实现 | 持久 token 统计；日/月预算；off/soft/hard |
| 文件信号 | 已实现 | PDF 上传后写入去重 Event/Run |
| 日历变更信号 | 已实现 | 直接 CRUD 和确认 Action 都写入去重 Event/Run |
| 外部连接器 | 已实现租户入口 | 每用户可轮换 Bearer Secret；数据库只保存哈希；日历、邮件、企业消息统一进入 Event/Run |

## 5. P3：持久工作流与生产化

| 任务点 | 状态 | 实现/边界 |
| --- | --- | --- |
| 多步骤工作流 | 已实现业务 DAG | 主模型提案、用户确认、时间偏移、步骤依赖、持久 checkpoint、失败/重试/补偿/停止 |
| 人工介入 | 已实现 | 依赖步骤必须由用户明确完成、跳过或补偿后推进 |
| 健康与指标 | 已实现 | `/system` 报告业务 scheduler、Run、通知、Action、账本、记忆、预算和策略接受/忽略率；通用 Trace/日志复用 Makers/CLS |
| 浏览器通知 | 已实现基础层 | 用户授权后、页面打开或后台存活时显示系统通知；持久 Inbox 不依赖页面 |
| 多用户/RBAC | 代码完成，待配置终验 | 官方 Neon+bcrypt+JWT 架构；用户/管理员角色；Conversation、Store、Blob、连接器密钥均按租户隔离 |
| 调度与原子抢占 | 复用平台 | EdgeOne Cron + Blob `onlyIfNew` 强一致原子锁；不自研队列或通用 Worker |
| DAG/补偿 | 已实现安全业务层 | 依赖、失败、重试、补偿和分支阻断；不自动编排未确认的高风险副作用 |

## 6. 不变量

1. 当前聊天、搜索、富媒体、地图、日程、生图、会议、论文和 PDF 能力不得回退。
2. Collector 只采集事实；Policy 决定是否提醒；高风险副作用只经过 Action 确认。
3. Provider 失败不能编造天气、路线或执行成功。
4. 用户关闭主动功能、提醒类型或工作流后，后台必须尊重设置。
5. 记忆和规则永远先提案、后确认。
6. “猜你想问”点击只填入输入栏，发送仍由用户显式完成。

## 7. 自动化基线

- Makers Agent：46 项通过。
- 前端：22 项通过（FastAPI/WebSocket 退役测试已删除）。
- Cloud Functions 平台复用/安全契约：4 项通过。
- 旧 FastAPI 已进入退役流程，不再作为 Makers 发布回归门槛；剩余迁移项见 `FASTAPI_RETIREMENT_MIGRATION.md`。
- TypeScript/Vite 生产构建：通过。
- ESLint：通过。
- 已知非阻塞项：前端主 chunk 仍大于 500KB。

## 8. 部署终验

部署后必须完成：

1. `/proactive` 手动 tick 能持久化 `last_tick`。
2. `/system` 返回 scheduler、Run、Notification、Action 与 Intelligence 健康信息。
3. 创建一个 0 分钟工作流提案，确认后 tick 只生成一条通知；重复 tick 不重复。
4. 页面刷新后通知、Run、工作流和记忆仍存在。
5. 等待平台计划任务跨整点触发，确认 `last_tick.started_at` 在无聊天请求时推进。
6. “猜你想问”点击后只更新输入栏，不产生用户消息。
7. 多用户模式下 A/B 用户的 Conversation、Workspace、Blob、Intelligence、Proactive 与连接器 Secret 互不可见。
8. 工作流失败后只生成一次补偿提醒；重试使用新的 attempt 去重键，依赖步骤在补偿完成前不推进。
