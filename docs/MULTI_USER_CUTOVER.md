# 多用户生产切换手册

> 模式：先验证多用户身份链，再执行可校验的数据迁移。
> 原则：未获得明确删除授权且迁移校验未通过前，不删除任何旧数据；任何阶段都不恢复 FastAPI。

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

## 4. 旧数据迁移与清理

第 3 节全部通过后，先使用 P2 离线迁移工具导出并导入：

1. 导出旧单用户 Conversation、Blob 与 LangGraph Store 清单。
2. 导入到目标租户并比较对象数量、稳定 ID、内容哈希和抽样回读。
3. 生成待清理清单，包含旧 Conversation、Blob 和以下 namespace：
   - `yuanbao_user_workspace_v1/local-user`
   - `yuanbao_proactive_v1/local-user`
   - `yuanbao_intelligence_v1/local-user`
4. 只有迁移报告通过并得到明确删除授权后，才执行清理。

实现不包含旧 namespace fallback，因此物理清理延迟不会让旧数据进入新用户视图。清理是不可逆操作，必须单独确认。

## 5. 无浏览器主动终验

1. 为正式用户创建未来 24 小时内日程后退出登录并关闭页面。
2. 等待跨过下一个整点。
3. 重新登录并检查 `/system`：`last_tick.finished_at` 必须推进，且 `trigger_origin` 为计划任务。
4. Notification 必须包含原因、证据、时间和下一步；重复整点扫描不产生重复 Event/Notification。
5. 若 Provider 失败，只允许 checkpoint/Run 失败记录，不得伪造天气、路线或副作用成功。

## 6. 回滚边界

- 身份链失败：将 `AUTH_MODE` 临时切回 `single_user` 仅用于恢复服务，不恢复 FastAPI。
- 新租户数据异常：停止 Cron 和写入，保留 Store/Blob 现场调查。
- 数据迁移失败时停止新写入并保留两侧数据；不得以删除旧数据作为回滚手段。
