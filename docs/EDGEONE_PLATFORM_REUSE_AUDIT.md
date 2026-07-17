# EdgeOne Makers 平台能力复用审计

> 审计日期：2026-07-16  
> 原则：平台正式托管能力或腾讯官方参考实现优先；只自研主动式 Agent 的业务语义。

## 1. 结论

当前生产架构不再自建会话数据库、检查点数据库、对象存储、Cron、模型网关或通用 Trace。多用户认证也不再采用 Blob 用户表与自创 PBKDF2/JWT 协议，而采用腾讯官方 `makers-agents-auth` 的分层：Edge Middleware、Cloud Functions、Neon、bcrypt、HttpOnly JWT。

仍需由应用实现的是 Makers 没有提供的主动业务层：Event、Observation、Policy、Run、Notification Inbox、用户可确认 Action、幂等账本和持久 Workflow。这些不是通用基础设施的重复实现，而是产品领域模型。

## 2. 复用矩阵

| 能力 | 最终方案 | 处理 | 理由 |
|---|---|---|---|
| LLM 与工具调用 | Makers AI Gateway、Makers 原生工具 | 复用 | 模型密钥、流式调用和原生工具由平台管理 |
| 会话与消息 | Makers Conversation Store | 复用 | 不维护第二套聊天数据库 |
| Agent Checkpoint | Makers LangGraph Checkpointer | 复用 | 中断恢复和线程状态由平台注入 |
| 用户长期状态 | Makers LangGraph Store | 复用 | Workspace、Proactive、Intelligence 只保存业务文档 |
| 文件与 PDF | EdgeOne Pages Blob | 复用 | 强一致读取、元数据与租户前缀 |
| 定时触发 | `edgeone.json.schedules` + Makers Function | 复用 | 不使用浏览器 Timer 或常驻进程 |
| 定时抢占 | Blob `setJSON(..., {onlyIfNew:true})` | 薄封装 | 使用平台原子条件写，未自建分布式锁服务 |
| 用户认证 | 官方 `makers-agents-auth` 架构 | 官方参考 | EdgeOne 没有托管终端用户目录；官方建议 Neon + bcrypt + HttpOnly JWT + Middleware |
| 租户身份 | JWT `sub` + Agent 二次验签 | 官方参考扩展 | Middleware 早拒，Agent 不信任浏览器自报 header |
| 通用日志与 Trace | Makers 可观测、腾讯云 CLS Agent 可观测 | 复用 | 删除应用自建 OPS webhook/通用 tracing；`/system` 只输出业务 SLO |
| WAF、DDoS、Bot、IP 频控 | EdgeOne 安全能力 | 配置 | 不在业务代码重复实现边缘安全产品 |
| Event/Run/Policy | 应用领域模型 | 保留 | 平台没有主动 Agent 的决策语义 |
| Notification Inbox | 应用领域模型 | 保留 | 平台不负责用户级提醒、静默、冷却与反馈 |
| Action 幂等/未知结果 | 应用领域模型 | 保留 | 外部副作用需要业务幂等键、冻结快照和人工核对 |
| Workflow/DAG | 应用领域模型 | 保留 | 平台 Cron 只负责唤醒，不理解业务步骤和补偿 |
| 外部连接器密钥 | Neon 保存哈希，明文一次性返回 | 保留 | 平台不提供本应用的 Calendar/Email/IM webhook 身份；信号经 Cloud Function 鉴权后再进入 Agent |

## 3. 已删除或禁止的重复建设

- Blob 用户表、Blob 登录失败计数和自研 PBKDF2 密码系统。
- 自建会话表、SQLite、FastAPI WebSocket 和文件中转层。
- 浏览器定时器充当后台 Scheduler。
- 通用 OPS webhook、应用内 OpenTelemetry/Sentry 替代实现。
- 自建对象存储、队列和分布式锁服务。
- 以 `conversation_id`、查询参数或普通前端 header 冒充可信用户身份。

`cloud-functions/platform-reuse.test.js` 会在回归中检查上述架构约束，防止后续重新引入。

## 4. 平台配置而非代码任务

1. 开启 EdgeOne WAF、Bot 防护和登录/API 频控。
2. 配置 `AUTH_MODE=multi_user`、Neon `DATABASE_URL`、32 字符以上的 `JWT_SECRET` 和 `PROACTIVE_SCHEDULE_SECRET`。
3. 执行 `db/001_users.sql`。
4. 将 Agent Trace、Token、错误率和函数日志接入 Makers/CLS 可观测与告警。
5. Provider 密钥只使用 Makers 环境变量，不写入 Blob、前端或 Git。

## 5. 官方依据

- [Makers Agent 用户认证最佳实践](https://cloud.tencent.com/document/product/1552/125470)
- [EdgeOne Pages Blob](https://cloud.tencent.com/document/product/1552/117428)
- [EdgeOne Pages Functions 定时任务](https://cloud.tencent.com/document/product/1552/125606)
- [Makers AI Gateway](https://cloud.tencent.com/document/product/1552/125045)
- [Makers Agent Traces 全链路可观测](https://cloud.tencent.com/document/product/1552/125869)
- [腾讯云 CLS Agent 可观测](https://cloud.tencent.com/document/product/614/126791)

## 6. 审计边界

平台当前没有文档化的通用消息队列、业务 Workflow 引擎、用户通知中心或外部 Action 幂等服务。因此主动运行时仍由平台 Cron 唤醒并在 LangGraph Store 中推进业务状态机；如果 EdgeOne 后续推出对应托管能力，应重新审计并优先迁移。
