# 多用户生产切换手册

> 模式：干净切换，不迁移旧 `local-user` 数据。  
> 原则：先证明新身份链可用，再删除旧数据；任何阶段都不恢复 FastAPI。

## 1. 前置配置

1. 创建 Neon PostgreSQL（腾讯官方 `makers-agents-auth` 推荐方案）。
2. 执行 [`db/001_users.sql`](../db/001_users.sql)。
3. 在 EdgeOne Makers 环境变量配置：
   - `DATABASE_URL`：Neon pooled connection string；
   - `JWT_SECRET`：至少 32 字节随机值；
   - `PROACTIVE_SCHEDULE_SECRET`：与 JWT 不同的至少 32 字节随机值；
   - `AUTH_MODE=multi_user`。
4. 在 EdgeOne 控制台启用 WAF、Bot 防护，并对 `/auth/login`、`/auth/register`、`/signals` 设置频控。
5. 将 Makers Agent Trace、函数日志、错误率和 Token/成本接入平台/CLS 告警。

## 2. 部署前门槛

- Makers Agent 测试、前端测试、构建、Lint、Cloud Functions 语法与平台复用测试全部通过。
- 生产前端不存在 `/api` 或 WebSocket fallback。
- `DATABASE_URL/JWT_SECRET/PROACTIVE_SCHEDULE_SECRET` 不进入 Git、Blob 或前端产物。
- `edgeone.json` 的 Cron 只触发 `/proactive-tick` 平台 Function。

## 3. 金丝雀验证

1. 部署后注册 `tenant-a` 与 `tenant-b` 两个临时用户。
2. A 创建对话、日程、记忆、文件、阅读收藏、工作流和连接器 Secret。
3. B 的 Conversation、Workspace、Proactive、Intelligence、Blob/Library 均不得出现 A 的对象。
4. 用 A Secret 注入一个日历信号，只能在 A 生成 Event/Run；重复注入不得重复。
5. 工作流失败只生成一条补偿提醒；补偿前依赖步骤不推进；重试生成新的 attempt 去重键。
6. 登出后受保护 Agent/Function 返回 401；篡改 Cookie、过期 JWT 和普通用户伪造系统 header 均失败。

## 4. 旧数据清理

仅在第 3 节全部通过后执行：

1. 删除旧单用户 Conversation Store 中的全部会话。
2. 删除 Blob 中旧全局 `library/`、`uploads/`、`papers/`、`generated/` 对象；保留 `tenants/`。
3. 删除 LangGraph Store 的旧 namespace：
   - `yuanbao_user_workspace_v1/local-user`
   - `yuanbao_proactive_v1/local-user`
   - `yuanbao_intelligence_v1/local-user`
4. 删除临时 A/B 用户及其测试租户对象，再创建正式管理员。

清理是不可逆的，用户已明确允许放弃旧数据。实现不包含任何旧 namespace fallback，因此即使物理清理延迟，旧数据也不会进入新用户视图。

## 5. 无浏览器主动终验

1. 为正式用户创建未来 24 小时内日程后退出登录并关闭页面。
2. 等待跨过下一个整点。
3. 重新登录并检查 `/system`：`last_tick.finished_at` 必须推进，且 `trigger_origin` 为计划任务。
4. Notification 必须包含原因、证据、时间和下一步；重复整点扫描不产生重复 Event/Notification。
5. 若 Provider 失败，只允许 checkpoint/Run 失败记录，不得伪造天气、路线或副作用成功。

## 6. 回滚边界

- 身份链失败：将 `AUTH_MODE` 临时切回 `single_user` 仅用于恢复服务，不恢复 FastAPI。
- 新租户数据异常：停止 Cron 和写入，保留 Store/Blob 现场调查。
- 旧数据已删除后不做数据回滚；功能回滚只能回到 Makers 单用户运行模式。
