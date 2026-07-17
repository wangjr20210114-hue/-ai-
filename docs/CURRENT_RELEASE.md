# 当前发布记录

> 本文件只记录有证据的部署事实。当前代码能力以 [`BASELINE.md`](BASELINE.md) 为准，后续工作以 [`MIGRATION_PLAN.md`](MIGRATION_PLAN.md) 为准。

## Makers 项目与当前部署

- 项目：`ai-active-agent`
- Project ID：`makers-0oeuhire655w`
- 地址：[https://ai-active-agent-tndu0xxa.edgeone.cool](https://ai-active-agent-tndu0xxa.edgeone.cool)
- 当前生产域名：`ai-active-agent-tndu0xxa.edgeone.cool`；2026-07-18 已发布本改造分支，首页返回 200；动态接口仍回退为静态首页，不能作为功能验收证据。
- 当前改造分支：`codex/edgeone-makers-refactor`。
- 当前生产已覆盖为本改造部署 `dptvxaubmrso`，但仍有平台动态路由回退阻塞。

历史记录来自原分支文档；尚未证明其与当前改造提交完全一致。

## 2026-07-17 改造部署证据

| 环境 | Deployment ID | 结论 |
| --- | --- | --- |
| Preview | `dpimno6wz2yc` | 构建成功；项目级 Edge Middleware 在线返回 545，已移除。 |
| Preview | `dp0r3vm5d3rn` | 构建成功；根页面 200，但动态路径被静态页面回退。 |
| Preview | `dpy9xifv8nhw` | 构建成功；共享/测试模块已排除，CLI 只构建 12 条真实 Agent 路由；根页面 200，`/auth/user`、`/workspace`、`/system`、`/library` 仍返回静态 HTML。 |
| Production | `dptvxaubmrso` | 2026-07-18 构建、上传与发布成功；首页 200，但认证、资料库、工作区和系统接口仍返回静态 HTML。控制台确认该部署只登记了 63 个静态资源，`函数` 与 `Agents` 页签均为空，CLI 构建出的 Cloud Functions 和 12 个 Agent 路由没有被平台注册。 |

本地 `edgeone makers dev` 对同一构建产物验证通过：`/auth/user`、`/library`，以及携带 `makers-conversation-id` 的 `/workspace`、`/system` 均为真实 JSON 200。平台 Preview 路由回退仍待控制台日志或生产发布验证。根据官方文档，Preview 应可用于部署验证，且下划线前缀目录不会生成 Agent 路由；当前现象已作为平台阻塞记录，不能把 Preview 的“部署成功”误报为线上功能验收。

## 已记录的线上能力

- 多会话并行聊天、SSE 心跳、停止和消息恢复。
- WSA 富搜索、网页媒体抽取和 HY-Vision 复核。
- 腾讯地点、地图、道路路线和日程工作区。
- 文生图、图生图、版本轮播、Blob 归档和 ZIP 下载。
- PDF 上传、阅读库、论文检索和全屏助读。
- 日历、主动提醒入口、记忆、预算和持久工作流的代码链路。

## 当前改造待发布

- 文档唯一事实源和零缩水基线。
- Makers 生产链 CI 与依赖锁定。
- Neon 唯一 Schema。
- 单用户无数据库部署路径与多用户 Neon 可选路径。
- SQLite 到 Makers Store/Blob 的一次性迁移链。
- 腾讯会议官方 API 适配（可选，不阻塞个人部署）。
- Provider 未知结果的人工核对状态。

## 已完成的发布前检查

- EdgeOne CLI：`1.6.13`，账号登录有效。
- 本地分支已关联 Makers 项目 `ai-active-agent`。
- 项目已有 Makers AI Gateway 等核心 Provider 变量。
- 个人部署改用 `AUTH_MODE=single_user`；`AI_GATEWAY_MODEL` 有代码默认值。
- Neon/JWT 仅在开放多用户时需要，腾讯会议为最后阶段可选连接器。
- Agent 单元测试：53 通过；迁移工具：2 通过；Node 平台测试：9 通过；前端测试：22 通过；ESLint、类型构建、`git diff --check` 通过。
- CLI 1.6.13 成功构建 Node Functions、Python LangGraph Agents 与静态前端；最后一次构建仅含 12 个真实 Agent 路由。
- 本地 Makers 联调完成，不启动 FastAPI。

生产发布会替换现有线上版本；必须在发布后立即复测本节所列四个端点和完整功能清单。变量真实值不得写入仓库。

## 已知边界

- DOC/DOCX、扫描 PDF OCR 和页码级引用未实现。
- PDF、KaTeX 和地图仍使主 JS chunk 约 1.36 MB。
- 真实 EdgeOne Cron、多用户 A/B 隔离、WAF/频控和 CLS 告警仍需线上终验。
- Preview 与 Production 的动态路由当前均被静态页面回退。控制台已确认不是业务处理异常，而是部署未注册任何 Cloud Function/Agent；下一步应改用新建 Makers 项目验证，或将改造分支推送到 GitHub 后采用平台 Git 构建链，绕过当前项目的直接上传注册问题。
- SQLite 迁移工具已完成代码测试，但仓库中没有真实旧数据库，尚未执行数量/哈希/抽样回读。

## 下一次发布必须记录

1. Git commit SHA。
2. Deployment ID 与完整 Preview URL。
3. 环境变量名称检查结果，不记录值。
4. 自动化结果。
5. 两用户隔离、无浏览器 Cron 和真实 Provider 冒烟结果。
6. 回滚 Deployment ID。
