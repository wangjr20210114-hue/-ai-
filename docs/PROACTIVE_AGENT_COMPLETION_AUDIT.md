# 主动式 Agent P0–P3 完成审计

> 审计日期：2026-07-16  
> 判定规则：本地测试只证明代码契约；平台 Cron、真实租户隔离、WAF/CLS 与 Provider 行为必须用生产证据证明。

## 总结

- **本地代码完成**：P0–P3 业务契约、Makers-only 前端、官方认证架构、平台能力复用。
- **生产完成尚未证明**：Neon 身份库和 Makers 身份变量未配置；新版本未部署；Cron、双租户和旧数据清理未在线验证。
- 因此当前目标不能标记完成。

## P0：主动最小闭环

| 要求 | 实现证据 | 自动化证据 | 生产证据 | 判定 |
|---|---|---|---|---|
| 后台唤醒 | `edgeone.json.schedules` → `/proactive-tick` | 平台复用测试检查 Cron 配置 | 尚未跨整点观察 | 本地完成，线上待证 |
| Event/Run/Observation/Notification | `agents/shared/proactive.py` + LangGraph Store | Agent 去重/持久 Inbox 测试 | 尚未部署 | 本地完成 |
| 后端日程机会检测 | Schedule Collector；React 不计算机会 | 冲突、临近、重复扫描测试 | 尚未部署 | 本地完成 |
| Inbox 与 Policy | 总开关、类型、免打扰、每日上限、稍后、忽略 | Policy 与 UI 回归 | 尚未部署 | 本地完成 |
| 用户关闭页面仍运行 | Function Cron，不依赖浏览器 Timer | 架构扫描证明无浏览器调度 | 尚未跨整点观察 | 未最终证明 |

## P1：可靠执行和权限

| 要求 | 实现证据 | 自动化证据 | 判定 |
|---|---|---|---|
| 冻结 Action/哈希/幂等账本 | `agents/shared/workspace.py` | 篡改拒绝、重复确认、未核对调用测试 | 完成 |
| lease/recovery | Provider 调用前持久账本；过期进入 `reconciliation_required` | stale action recovery 测试 | 完成 |
| 天气/路线 Collector | 腾讯位置/天气/路线 Provider | Provider 缺失不编造、风险信号测试 | 本地完成，真实 Provider 待线上 |
| 权限矩阵 | `observe/remind/propose/low_risk_auto` | observe 只写 Event/Run 测试 | 完成；当前无自动副作用白名单 |
| Run 时间线与解释 | 左栏持久 Run、原因、证据、下一步 | 前端构建与 Agent public state | 本地完成 |

## P2：记忆、反馈和外部信号

| 要求 | 实现证据 | 自动化证据 | 判定 |
|---|---|---|---|
| 记忆提案/确认/敏感度 | `agents/shared/intelligence.py` | 未确认不注入、敏感记忆不自动注入 | 完成 |
| 版本、历史、回滚、删除、导出 | 同一 Intelligence Store 文档 | 更新/回滚测试 | 完成 |
| 反馈 → Rule Proposal | 忽略三次只产生待确认规则 | feedback 测试 | 完成 |
| Token 预算 | daily/monthly/off/soft/hard | usage 测试 | 完成 |
| 外部日历/邮件/企业消息 | 每用户 Bearer Secret → `/signals` → Event/Run | JWT/平台契约与 Agent 去重测试 | 本地完成；真实连接器待线上 |

## P3：工作流与多用户生产化

| 要求 | 实现证据 | 自动化证据 | 生产证据 | 判定 |
|---|---|---|---|---|
| DAG/checkpoint/人工介入 | 持久 Workflow Step + dependencies | 确认、依赖、重复 tick 测试 | 尚未部署 | 本地完成 |
| 失败/重试/补偿 | attempt 去重键、补偿状态、依赖阻断 | 补偿与重试测试 | 尚未部署 | 本地完成 |
| 多用户身份/RBAC | 腾讯官方 Neon+bcrypt+JWT+Middleware 架构 | JWT 篡改/过期、Python 身份、namespace 隔离 | Neon 未配置 | 本地完成，线上未完成 |
| 租户 Store/Blob/Conversation | JWT `sub` namespace 和 `tenants/{sub}` | A/B Store 隔离与平台架构扫描 | 尚未双用户验证 | 本地完成，线上待证 |
| 调度/原子锁 | EdgeOne Cron + Blob `onlyIfNew` | 平台复用测试 | 尚未部署 | 平台复用，线上待证 |
| 可观测和外部告警 | 业务 SLO `/system`；通用 Trace/日志交给 Makers/CLS | `/system` 代码和平台复用测试 | CLS/WAF 告警未配置 | 配置未完成 |
| 策略评估 | 接受率、忽略率、Rule Proposal、通知/Run 状态 | `/system.policy_evaluation` | 尚无生产样本 | 本地完成 |

## 跨阶段不变量

| 不变量 | 证据 | 判定 |
|---|---|---|
| 现有 Makers 功能不回退 | Agent 46 项、前端 22 项、构建、Lint、Cloud Functions 6 项通过 | 本地通过 |
| FastAPI 不再是生产依赖 | App 只使用 Makers SSE；WebSocket 和 `/api` fallback 已删除 | 通过 |
| 平台能力绝不重复建设 | `EDGEONE_PLATFORM_REUSE_AUDIT.md` + `platform-reuse.test.js` | 通过 |
| “猜你想问”只填输入栏 | `followUps.test.ts` 明确断言不创建/发送消息 | 通过 |
| 旧数据不迁移 | 新租户只读 tenant namespace；无 `local-user` fallback | 通过，物理清理待切换 |

## 完成目标仍需的权威证据

1. Neon 执行 `db/001_users.sql`，Makers 设置四个身份环境变量。
2. 部署成功且 EdgeOne 接受 `schedules` 配置。
3. 两个真实用户完成 Conversation、Store、Blob、连接器跨租户负向测试。
4. 清空旧单用户 Conversation/Blob/Store。
5. 浏览器关闭且无聊天请求时，跨整点 `last_tick` 推进。
6. Makers/CLS 告警和 EdgeOne WAF/登录频控已在控制台启用。
