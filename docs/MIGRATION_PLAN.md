# EdgeOne Makers 零缩水改造计划

> 状态：核心 Makers 改造完成；当前进入 Preview 复验、真实数据迁移与增强阶段
> 原则：先证明等价，再退役旧实现；平台轮子优先；每一阶段都可独立回滚。

## P0：建立可信发布基线（代码完成）

### P0.1 文档与能力基线

- 建立 `BASELINE.md`、`ARCHITECTURE.md`、本计划与 `DEPLOYMENT.md`。
- 将旧 FastAPI 的用户结果归纳到 `LEGACY_FASTAPI_CAPABILITIES.md`。
- 删除已被当前事实源覆盖的历史计划、重复审计和过时测试表。

完成条件：仓库内不再存在两个互相冲突的“当前架构”或“当前基线”。

### P0.2 CI 与可复现构建

- Agent：安装根依赖、compileall、运行 `agents/_tests`；下划线目录不会被 Makers 当作路由扫描。
- Cloud Functions：运行 JWT、租户和平台复用测试。
- Frontend：Vitest、ESLint、EdgeOne mode build。
- 扫描生产入口，禁止 FastAPI/WebSocket/SQLite fallback 回流。
- 锁定根 Python 直接依赖版本。

完成条件：全新 clone 的 CI 与本地命令一致。

### P0.3 数据库唯一 Schema

- 只保留 `db/001_users.sql`。
- Schema 幂等创建用户、角色、状态和连接器 Token 索引。
- 添加结构测试，避免 roles 类型再次漂移。

完成条件：新 Neon 项目只需执行一份 SQL。

## P1：清除单仓库部署阻塞（完成）

### P1.1 可选腾讯会议连接器

状态：官方 API 适配已完成，但降为最后阶段可选连接器。未配置时工具不暴露，不阻塞个人部署。

- 删除外部 FastAPI Meeting Bridge 和本地 `tmeet` fallback。
- 使用腾讯会议官方服务端 API；凭据只放 Makers 环境变量。
- 保留 Action 确认、快照、Provider Ledger、幂等和人工核对。
- 对网络超时和 5xx 标记 `reconciliation_required`，禁止盲重试。

完成条件：EdgeOne 预览环境无需额外服务器即可创建会议。

### P1.2 EdgeOne 预览部署

状态：项目已关联 GitHub，并通过平台 Git 构建链完成 Preview 与 Production。当前 Preview `dph2wvagts0x` 构建提交 `9ed04b1` 成功，生成 13 条 Python Agent 路由和每日 Schedule；受保护访问链接显示“已连接”，历史会话、日程、路线缓存、阅读库和代码展示读取通过。小时级 Cron 已按 Makers 最短 1 天限制改为每日 08:00；详情见 `CURRENT_RELEASE.md`。

- 从目标分支创建独立 Makers Preview。
- 校验当前身份模式必需环境变量、Blob 和 Conversation Store；仅多用户模式校验 Neon Schema。
- 完成聊天、搜索、地图、日程、生图、PDF、论文、会议冒烟。
- 跨整点验证无浏览器 Cron。
- 使用两个真实测试用户完成负向隔离。

完成条件：保存 Deployment ID、预览 URL、测试证据和回滚目标。

## P2：数据迁移和遗留能力等价（迁移链已实现，真实数据待执行）

### P2.1 SQLite 离线迁移

状态：只读导出器、Makers Conversation/LangGraph Store 导入器和官方 Blob SDK 导入链已实现；待使用真实旧库执行数量、哈希和抽样回读。

- 提供只读导出器，不启动 FastAPI。
- 将会话迁入 Conversation Store，文件迁入 Blob，用户状态迁入 LangGraph Store。
- 记录数量、稳定 ID、内容哈希、失败项和重跑 checkpoint。
- 导入完成后抽样回读；校验前不删除 SQLite 或本地文件。

### P2.2 用户结果能力补齐

- 跨存储数据导出与账号删除流程。
- 旅行计划作为可持久资产，而非只存在于聊天文本。
- Run/Workflow 的人工重试、取消和补偿入口。
- 论文长任务保存步骤级 checkpoint。

完成条件：`LEGACY_FASTAPI_CAPABILITIES.md` 中所有用户结果均为“等价完成”或经产品确认取消。

## P3：可靠性与体验

- 阅读库并发更新保护和更细粒度资产索引。
- PDF/KaTeX/地图动态加载，缩小主包。
- DOC/DOCX 受控转换、OCR、页码级引用。
- 邮件、系统日历和企业 IM 连接器。
- Provider 远端幂等查询和自动核对。
- Playwright 真实浏览器矩阵与 Provider 沙箱测试。

## 每阶段统一交付

1. 代码与 Schema。
2. 自动化测试和结果。
3. 文档事实更新。
4. 数据兼容说明。
5. Preview 验收步骤。
6. 回滚路径。
