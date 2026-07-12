# 主动式 Agent 架构改造变更记录

> 分支：`agent/proactive-runtime-refactor-v2`
> 基线提交：上传项目初始快照
> 对照：`元宝主动式Agent_现有能力盘点与目标架构设计`

## 已完成的结构性改造

1. **持久运行时**：Event、Run、Plan、Observation、租约与执行结果统一写入 SQLite。
2. **不可变 Action**：会议、生图使用版本化输入、快照哈希、版本确认和稳定幂等键。
3. **单一 Executor**：Transport 不直接执行副作用；确认后由 Supervisor 后台领取。
4. **外部调用账本**：新增 `provider_calls`。Provider 成功响应先落账，再提交 Action，覆盖成功响应与 Action 提交之间的崩溃窗口。
5. **运行恢复**：启动及运行期间周期性回收过期 Run/Job；纯计算任务可重排，副作用按账本自动恢复或转人工核对。
6. **主动运行**：Scheduler、日程/天气/文件 Collector、OpportunityDetector、通知去重/冷却/免打扰/每日上限。
7. **Skill 收敛**：聊天、翻译、搜索、论文进入 Skill + ModelGateway；WebSocket 仅保留协议职责。
8. **用户控制**：Action Center、Run 时间线、通知、记忆提案、长期记忆、反馈、预算和显式取消。
9. **本地安全**：本地访问令牌、严格 CORS、REST/WS 共用鉴权、SSRF/重定向/响应大小保护。
10. **产品恢复**：校验备份、重启原子恢复、健康快照、请求关联日志。
11. **结构化图文回答**：检索结果生成稳定 `source-*` / `media-*` 标识；Chat/Search 共用 grounded prompt；前端安全解析图片、引用和来源卡片，兼容旧消息协议。
12. **权限回归修复**：生图恢复为确认型副作用；高风险 AUTO 计划由策略层强制升级为确认，避免绕过统一 Action/Executor 链路。

## 数据库迁移

- v1：原始业务表
- v2：身份、会话、消息、文件
- v3：Event、Run、Observation、Action
- v4：执行租约、lane、Action 结果与核对标记
- v5：Job、Notification、偏好与 Usage
- v6：Memory proposal、Memory、Feedback
- v7：记忆版本、敏感度、反馈幂等、预算偏好
- v8：Provider 调用账本与崩溃恢复桥接

## 当前验证

- 后端：52/52 unittest 通过。
- 完整 FastAPI lifespan E2E 通过。
- 前端：5/5 Vitest 通过。
- ESLint、TypeScript、Vite production build 通过。
- Python compileall 与 FastAPI 应用导入通过。

## 仍需后续扩展

- 旅游规划步骤级 checkpoint/workflow。
- 搜索引用覆盖率验证、来源时效评分和证据冲突专用展示。
- 论文页码级分块索引与 OCR。
- 邮件、系统日历、企业消息等授权 Collector。
- 腾讯会议/生图 Provider 的远程 request-id 查询，实现真正外部状态自动核对。
- Playwright 浏览器矩阵与前端动态拆包。
