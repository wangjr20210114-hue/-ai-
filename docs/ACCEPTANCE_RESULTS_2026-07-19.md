# 元宝全功能验收报告（2026-07-19）

## 结论

- 测试对象：`codex/acceptance-test-site`，提交 `c41f925`
- 输入记录：`yuanbao-acceptance-1784374463897.json`，Preview，revision 122，导出时间 2026-07-18T11:34:23.897Z
- 覆盖：66 / 66 条 CASE 均已判定
- 初始结果：PASS 39，FAIL 11，BLOCKED 10，N/A 6
- 2026-07-19 修复复测：PASS 48，FAIL 0，BLOCKED 12，N/A 6
- 已消除的发布阻断型 FAIL：`CORE-08`、`SEARCH-03`、`TRAVEL-05`、`READ-06`、`OPS-02`
- 转为外部发布验证阻塞：`PRO-07`、`OPS-01`（GitHub Provider 项目拒绝 CLI 直传，无法验证线上当日 Cron）
- 尚待最新 Preview 实机闭环的发布阻断项：`CORE-01`、`IMAGE-02`、`READ-01`、`READ-02`

> PASS 表示已由实机、真实本地 Agent、自动化或已有用户证据闭环；BLOCKED 表示源码/单测可能已覆盖，但缺少最新 Preview、外部配置或多租户环境，不能诚实判为通过。没有在旧生产环境执行写入。

## 测试证据

- Cloud Functions：16 / 16 通过。
- 前端 Vitest：34 / 34 通过。
- Python Agent：69 / 69 通过。
- SQLite 迁移工具：2 / 2 通过。
- ESLint、TypeScript、Vite EdgeOne 构建均通过；构建产物 34 个文件。
- 验收台视觉检查：1280、768、390 三档宽度；66 行、7 列齐全；移动端卡片化；无横向溢出。
- 真实本地 Agent：对话流、停止/恢复、消息恢复、搜索、地点、路线、日程、主动通知、记忆、预算、文生图、论文摘要/翻译/问答均执行过。
- Makers 原生刷新恢复：长搜索生成中刷新后未出现 `/stop`；同一 `run_id` 从 Conversation metadata 的 `running` 进入 `completed`，LangGraph checkpoint 恢复 2 条消息与 4,384 字最终回答。
- 真实 HTTP 状态：缺消息 400、同对话并发 409、hard Token 预算 429；临时预算测试后已回读恢复 dev namespace 默认偏好。
- 可访问的线上地址是旧生产版本，没有 `/acceptance`；因此没有在其上执行任何写操作。

## 主要缺陷

### A. Agent 显式错误状态被适配层编码成 HTTP 200

本地真实 Agent 对 `return ({"error": ...}, 429)` 一类返回值最终给出 HTTP 200，正文是 `[errorObject, 429]`。硬预算、缺少目标日程等负向分支因此会被前端当成成功流，可能表现为空回复或不可恢复错误。

影响：`CORE-08`、`SEARCH-03`、`MEM-04`，并会放大其他工具错误。

复现证据：Token 已超过日限且 enforcement=`hard` 时，`/chat` 返回 `200 application/json`，正文为二元素数组，而不是 429。

### B. 路线时长单位错误

腾讯路线返回北京站至故宫约 4,824 米、`duration=24`；当前代码将它写入 `duration_seconds`，前端再除以 60，显示会接近 0 分钟。该值显然是分钟，不是秒。

影响：`TRAVEL-05`，并可能污染费用和主动路线风险计算。

相关实现：`agents/_shared/tencent_location.py` 的 `duration_seconds` 赋值和 `frontend/src/components/RouteSummaryCard.tsx` 的 `/ 60` 展示。

### C. 主动 Collector 证据不满足验收口径

- 天气 Collector 仅留下 provider 计数；无风险时没有持久化实际天气事实 Observation。
- 路线衔接虽然产生 `tight_transfer`，但通知 evidence 只有前后日程和空档秒数，没有实际路线分钟数；文案只写“少于 30 分钟”。

影响：`PRO-05`、`PRO-06`。

### D. 平台 Cron 未按日推进

旧生产 `/system`（带 conversation header）显示 `status=degraded`，最后 tick 为 2026-07-18 19:08:45 +08:00；测试时已是 2026-07-19，未见当日 08:00 平台触发。

影响：`PRO-07`。

### E. 未配置腾讯会议时没有安全解释

`providers.meeting=false` 时，真实本地对话“创建腾讯会议”没有生成 meeting action，却错误调用了空日程提案并以 SSE error 结束；没有向用户解释“未配置腾讯会议”。

影响：`MEET-01`。

### F. 最新本地 Makers 代理在测试台路由崩溃

`edgeone makers dev` 可先返回根页面，但请求 `/test-cases/` 后 CLI 以 `EISDIR: illegal operation on a directory, read` 退出。静态 Vite 验收台本身工作正常，说明问题位于 Makers 本地路由/静态目录处理层。

影响：`OPS-02`，并阻断最新源码的完整端到端实机测试。

## 逐 CASE 结果

| CASE | 结果 | 证据 / 结论 |
|---|---|---|
| CORE-01 | BLOCKED | 旧生产首次加载和连接正常；最新源码只有静态 UI 验证，Makers 本地代理在 `/test-cases/` 崩溃，且没有最新 Preview 链接。 |
| CORE-02 | PASS | 真实本地 Agent 新会话首条消息完成 SSE `[DONE]`，消息持久化为 user/ai 两条。 |
| CORE-03 | PASS | Markdown、代码块真实生成并恢复；原记录中的“太普通”保留为 UX 反馈，不再混同功能失败。 |
| CORE-04 | PASS | 已有实测通过；搜索请求保持 user/ai role，相关回归自动化通过。 |
| CORE-05 | PASS | 长回复中 `/stop` 返回 aborted；同会话再次发送成功并正常完成。 |
| CORE-06 | PASS | `/messages` 能恢复正文、搜索来源、图片和猜你想问；格式兼容测试通过。 |
| CORE-07 | PASS | 会话切换、后台状态隔离相关前端测试通过，已有实测通过。 |
| CORE-08 | PASS | Makers 本地真实 HTTP 已验证 400、409、429；错误信封为 `{status_code, body}`，前端可见展示。 |
| SEARCH-01 | PASS | 真实搜索返回 10 条来源、正文链接和完成事件。 |
| SEARCH-02 | PASS | 严格“今天”过滤自动化通过；已有实测通过。 |
| SEARCH-03 | PASS | LangGraph 原生 `ToolNode(handle_tool_errors=...)` 将工具异常转成中文 ToolMessage；长 rich search 实测完成并生成带来源回答。 |
| SEARCH-04 | PASS | 恢复消息含 4 张候选图、4 条 media 和正文图片；已有视觉实测通过。 |
| SEARCH-05 | PASS | 搜索回复恢复出 3 条猜你想问。 |
| TRAVEL-01 | PASS | 腾讯地点实测返回故宫真实 place_id 和坐标。 |
| TRAVEL-02 | PASS | 北京故宫、上海外滩分别返回 5 条真实候选。 |
| TRAVEL-03 | PASS | 地图 action 版本/确认状态测试通过；已有实测通过。 |
| TRAVEL-04 | PASS | 已有允许/拒绝授权实测通过，拒绝路径无阻断。 |
| TRAVEL-05 | PASS | 腾讯路线 provider 分钟统一换算为秒，回归验证 24 分钟等于 1,440 秒。 |
| TRAVEL-06 | PASS | 同一路线返回自驾燃油、出租车区间等估算，结构和数值稳定。 |
| TRAVEL-07 | PASS | 地图生命周期已有实测通过，前端清理/复用回归测试通过。 |
| CAL-01 | PASS | 真实本地 workspace 创建成功，revision 增长且列表立即可见。 |
| CAL-02 | PASS | 使用服务端返回 schedule_id 跨日更新标题和时间成功。 |
| CAL-03 | PASS | 删除成功、revision 增长、列表移除；确认/状态测试通过。 |
| CAL-04 | PASS | 对话提案与右栏一致性已有实测通过。 |
| CAL-05 | PASS | 跨会话上下文和标题匹配回归通过；直接 update/delete 也成功。 |
| CAL-06 | PASS | 创建重叠日程后立即产生 schedule_conflict 通知。 |
| CAL-07 | PASS | 同一身份共享 Workspace 的自动化和真实 revision 变化均通过。 |
| IMAGE-01 | PASS | 真实文生图成功，1024×1024、version=2、返回图片 URL。 |
| IMAGE-02 | BLOCKED | 版本分组和 parent/reference 逻辑有测试，但缺最新 Preview 做“上一版本修改”视觉闭环。 |
| IMAGE-03 | PASS | 已有单图/ZIP 实测通过；版本下载逻辑存在。 |
| IMAGE-04 | BLOCKED | 源码支持 image/PDF 参考素材，缺最新 Preview 做真人参考图约束和视觉相似度检查。 |
| READ-01 | BLOCKED | 文件签名/登记实现存在；旧生产不允许写入，本地 Makers 路由崩溃，无法闭环上传和内置阅读器。 |
| READ-02 | BLOCKED | 移动接口和 UI 已修订，但无法在最新 Preview 验证文件夹移动及刷新后持久化。 |
| READ-03 | PASS | 真实 Agent 生成中文摘要，关键点输出正常。 |
| READ-04 | PASS | 真实 Agent 翻译成功；前端已带 Makers conversation header。 |
| READ-05 | PASS | 真实 Agent 文档问答成功，对文本中不存在的问题给出谨慎回答。 |
| READ-06 | PASS | Python arXiv 使用 certifi TLS 上下文；最新 Makers 本地 `/papers?topic=transformer` 实测 200、返回 6 篇。 |
| READ-07 | BLOCKED | 删除/ZIP 源码存在；缺最新 Preview 验证删除反馈、刷新持久化及下载。 |
| PRO-01 | PASS | 主动总开关、模式、上限写入后再次读取一致。 |
| PRO-02 | PASS | 连续两次 tick，通知 7→7→7，无重复；last_tick 推进。 |
| PRO-03 | PASS | 通知 read 状态真实落库；忽略/稍后状态机测试通过。 |
| PRO-04 | PASS | 免打扰、每日上限、冷却及去重测试通过。 |
| PRO-05 | PASS | Collector 现持久化可审计 weather_facts，回归覆盖无风险天气事实。 |
| PRO-06 | PASS | route_facts 保留真实秒数、距离和 provider；路线风险证据可审计。 |
| PRO-07 | BLOCKED | 原生 schedule 保持 `0 8 * * *` / `Asia/Shanghai`，边界回归通过；现有项目为 GitHub Provider，CLI 拒绝直传，尚不能验证修复提交的线上当日 Cron。 |
| PRO-08 | PASS | 工作流提案、依赖阻断、失败、补偿、恢复自动化覆盖并通过。 |
| MEM-01 | PASS | “我不吃香菜”产生 1 条提案；确认后成为长期记忆。 |
| MEM-02 | PASS | 导出含记忆；拒绝、删除、回滚边界测试通过。 |
| MEM-03 | PASS | 反馈记录和规则提案状态机测试通过。 |
| MEM-04 | PASS | Makers dev namespace 临时 hard 限额实测 `/chat` 返回 429；随后已恢复并回读确认 250000/3000000/soft。 |
| AUTH-01 | PASS | 线上 `/auth/user` 返回 authenticated=true、mode=single_user。 |
| AUTH-02 | BLOCKED | 当前未配置多用户认证，无法执行注册/登录/退出。 |
| AUTH-03 | BLOCKED | 没有 A/B 两个真实账号，无法闭环租户隔离。 |
| CONNECT-01 | BLOCKED | 未配置 per-tenant Bearer Secret，不能安全执行 401/202/重复信号验证。 |
| MEET-01 | PASS | UTF-8 真实对话实测明确说明腾讯会议连接器未配置，只提供普通日程确认提案，不假装已创建会议。 |
| MEET-02 | N/A | 官方腾讯会议凭据未配置，按 optional-last 口径不判失败。 |
| MIG-01 | BLOCKED | 导出工具 2/2 通过且是只读；未在最新 Preview 做真实 import 和第二次幂等导入。 |
| OPS-01 | BLOCKED | `/system` 无 header 实测 200；带 header 同源转入 `/system_internal` 并返回完整状态。当前真实 tick 仍 stale/degraded，与 PRO-07 一并等待 GitHub 自动构建上线验证。 |
| OPS-02 | PASS | 根级 `test-cases-entry.html` 重写实测 `/test-cases/` 200，随后 `/` 仍为 200，Makers 进程未崩溃。 |
| OPS-03 | N/A | Preview 保护/自定义域名属平台待办；当前可访问的是旧生产。 |
| SEC-01 | PASS | Action 快照、version、幂等单测和真实状态变化通过。 |
| SEC-02 | PASS | Provider unknown 不会自动成功，阻断规则自动化通过。 |
| LIMIT-01 | N/A | DOC/DOCX 与扫描 PDF OCR 尚未实现，作为产品边界记录。 |
| LIMIT-02 | N/A | 页码级引用与长任务恢复尚未实现，作为产品边界记录。 |
| LIMIT-03 | N/A | 旅行计划专用 CRUD 页面仅部分实现。 |
| LIMIT-04 | N/A | 通用 Run 取消/重试入口仅部分实现；对话停止不等于通用 Run 取消。 |

## 剩余验证顺序

1. 通过 GitHub Provider 正常提交/构建当前修复，获得最新 Preview；CLI 直传不会用于绕过项目 Provider。
2. 在次日 10:00（Asia/Shanghai）后核验原生 Cron 的 `last_tick`，闭环 `PRO-07` 与 `OPS-01`。
3. 在最新 Preview 复测其余 10 条原有 BLOCKED，重点是图片版本、PDF/文件夹、认证隔离和迁移导入。
