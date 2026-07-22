# EdgeOne Makers 能力基线

> 当前业务分支：`agent/makers-native-persistence-fixes`
> 更新日期：2026-07-22
> 生产目标：EdgeOne Makers 是唯一线上运行时；FastAPI 运行时代码已删除，SQLite 只作为一次性只读迁移来源。

## 1. 基线原则

1. “功能不缩水”指用户能完成的任务、持久数据、安全确认和故障恢复语义不缩水，不要求保留旧 URL、WebSocket 或 SQLite 表。
2. 代码存在不等于可交付；只有进入 Makers 生产入口、通过自动化并完成预览环境验证的能力才标记为可部署。
3. 平台已有的运行时、会话、检查点、对象存储、定时任务、模型网关和可观测能力直接复用。
4. 外部副作用必须保留确认、冻结快照、幂等账本和未知结果阻断。
5. 旧数据在迁移校验通过前不得删除。

## 2. 当前用户能力

| 能力 | 代码状态 | 部署状态 | 主要事实源 |
| --- | --- | --- | --- |
| 多会话聊天、SSE、停止、刷新恢复 | 已实现并测试 | Preview/Production 已连接并加载历史会话 | `agents/chat`、`agents/messages`、`cloud-functions/conversations` |
| 联网图文回答 | 已实现并测试 | 搜索前保留 LLM 语义规划且默认 6 秒超时后交给主模型继续语义路由；Makers 网关/DeepSeek 降级单次无响应预算默认各 12 秒；单轮一次 rich_search/一次 SearchPro；事实与视觉意图合并，使用 Makers Store TTL/安全陈旧缓存；默认搜索/提图/视觉硬预算 10/5/7 秒 | `agents/chat/_capability_plan.py`、`agents/chat/_llm.py`、`agents/chat/_ui_tools.py`、`agents/_shared/rich_search.py` |
| 地点、地图、道路路线、费用估算 | 已实现并测试 | 腾讯结果与查询不匹配时回退 OSM；路线按用户缓存 6 小时 | `agents/places`、`agents/routes`、`agents/_shared/tencent_location.py` |
| 日程 CRUD 与确认式变更 | 已实现并测试 | 可用自然语言新增、改标题/描述/时间/地点、删除；地点修改必须来自地点库；不存在/不唯一目标会自然提示；变更后旧主动提醒同步刷新或失效 | `agents/workspace`、`agents/chat/_calendar_context.py`、LangGraph Store |
| 腾讯会议创建 | 官方个人 MCP Skill 适配已实现 | Skills 广场引导个人用户取得 Token；未配置时不暴露工具；确认后才调用 `schedule_meeting` | `agents/_shared/side_effects.py`、`SkillsMarketplaceButton.tsx` |
| 多模态理解、文生图、图生图、版本、Blob、ZIP | 已实现并测试 | 用户附图先经视觉 Provider 描述；混元为主，Cloudflare Workers AI 提供视觉/文生图/图生图降级，百炼与 Gemini 可作视觉后备；生成结果复制到 Makers Blob | `agents/_shared/vision.py`、`agents/_shared/side_effects.py`、`agents/image`、`InputBar.tsx` |
| PDF、图片上传、阅读库、论文助读 | 已实现核心链路 | PDF 上传后直接打开内置助读；阅读库支持手动分类与删除反馈；无 DOCX/OCR | `cloud-functions/files`、`library`、`papers`、`agents/reader` |
| 搜索/写作/翻译/生图/文档主动机会 | 已实现并测试 | 回答后由独立语义模型最多识别一条高价值下一步；文档上传和图片 Action 成功形成可信事件，生图结果返回后再异步做语义迭代判断；实时刷新提醒栏并在下一空白会话自然主动开场；包含置信度、冷却、过期、Action 去重和隐私过滤 | `agents/_shared/opportunities.py`、`agents/chat`、`agents/proactive`、`MessageBubble.tsx` |
| 主动日程/天气/路线提醒 | 已实现并测试 | 打开网页及相关日程变更时刷新；未读风险由模型在空白新对话中自然发起，策略设置位于统一设置；EdgeOne Schedule 触发顶层 `/proactive-tick` Cloud Function，复用 Makers Blob 原子锁后转给 `/proactive` Agent；顶层路径已有历史生产触发证据，嵌套 `/api/proactive-tick` 回归已移除 | `cloud-functions/proactive-tick`、`agents/proactive`、`useSSEChat.ts` |
| Notification、免打扰、每日上限、稍后提醒 | 已实现并测试 | 在线读取、即时刷新、业务去重及稍后/已读/忽略跨请求持久化均已在生产验证；只剩后台 Schedule 真实每日触发证据 | `agents/_shared/proactive.py` |
| Memory、Feedback、Rule、Token 预算 | 已实现并测试 | 待预览复验 | `agents/intelligence` |
| 持久工作流、失败阻断、重试与补偿 | 已实现并测试 | 待预览复验 | `agents/_shared/proactive.py` |
| 个人所有者身份 | 已实现并测试 | 固定 `local-user`，无注册登录或应用数据库 | `auth/current-user.js`、`agents/_shared/auth.py` |
| SQLite 历史数据迁移 | 导出/导入链已实现并测试 | 真实数据数量、哈希、抽样回读待执行 | `tools/export_sqlite.py`、`agents/migration` |
| 业务健康视图 | 已实现 | Makers/CLS 告警待控制台配置 | `agents/system` |

## 3. 已知未完成项

### P0：已在本分支完成，待 CI 平台复核

- CI 已以 Makers Agent、Cloud Functions 和 EdgeOne 构建作为发布门槛。
- 已删除 Neon、JWT、登录注册和租户隔离代码，个人演示不需要身份数据库。
- 根 Python 直接依赖已锁定版本。
- 当前架构、能力基线、部署和迁移计划已有唯一事实源。

### P1：代码阻塞与核心线上验收已完成

- 腾讯会议只使用官方个人 MCP Token/Skill；外部 Meeting Bridge、设备登录态和旧企业签名 API 均已删除。
- 本分支已完成真实 EdgeOne Preview/Production、动态路由登记和个人工作区核心读取验收；生产 `dptvf8ss3dl9` 已成功。Cron 业务链、云端路由和手动桥接已核验，真实每日触发仍需在下一计划时刻用平台日志确认。
- SQLite 迁移工具已完成，真实旧库迁移与 Preview 回读尚未执行。

### P2：产品增强但不阻塞核心迁移

- DOC/DOCX 转换、扫描 PDF OCR、页码级引用。
- 论文长任务的可恢复分块索引与全文处理。
- 阅读库 JSON 索引的并发写冲突防护。
- 前端 PDF、KaTeX、地图进一步动态拆包。
- 邮件、系统日历和企业 IM 的真实授权连接器（当前个人演示不提供）。

## 4. 零缩水验收门槛

- 所有基线能力有至少一个自动化用例和一个预览环境用例。
- 生产入口不存在活动 FastAPI、Uvicorn、SQLite、`/api` 或 WebSocket fallback。
- 会议、日程等高风险副作用重复确认不会重复执行。
- Provider 超时或结果未知时进入人工核对，不能直接重试。
- Conversation、Workspace、Blob、Intelligence 和 Proactive 均固定写入个人所有者工作区。
- 浏览器关闭时 EdgeOne Cron 能推进 `last_tick`；若受保护 Preview 的平台 Schedule 仍在路由层 404，该项保持外部阻塞，禁止用手动 tick 冒充通过。
- 从全新 clone 只依赖文档声明的环境变量即可构建和部署。

## 5. 当前自动化基线

2026-07-22 当前工作树结果：

- Makers Agent：142 项通过。
- SQLite 导出工具：2 项通过。
- Cloud Functions、Schedule 适配、验收持久化和平台约束：20 项通过。
- 前端 Vitest：73 项通过（16 个测试文件）。
- ESLint：通过。
- EdgeOne 模式生产构建：通过。
- EdgeOne Preview `dpbkmy4qt93e`、Production `dptvf8ss3dl9` 和生图主动闭环 Production `dpgwmrcmmoz5`：构建成功；应用已连接，主动文档闭环、真实混元生图及生图后语义迭代机会通过。
- 已知非阻塞项：Vite 仍有大于 500 KB 的分包提示，后续需要继续按功能动态拆包。

这些结果不替代真实 Provider、平台 Cron 和预览部署验收。
