# 当前发布记录

> 只记录当前有效事实。变量真实值、Preview 签名、Cookie、Provider Key 和用户数据不得写入仓库。

## 发布目标

- Makers 项目：`ai-active-agent`
- Project ID：`makers-0oeuhire655w`
- GitHub：`wangjr20210114-hue/-ai-`
- 生产分支：`agent/makers-native-persistence-fixes`
- 业务发布基线：以该分支最新成功 Production 提交为准；文档主动闭环最低修复点为 `0242112cf196651f11fdc0f03cfb5e99fa75fa65`
- Preview Deployment：`dpbkmy4qt93e`
- Preview 构建：成功，71 秒，2026-07-22 18:50（Asia/Shanghai）
- 已验证生产 Deployment：`dptvf8ss3dl9`，成功，69 秒，2026-07-22 19:31（Asia/Shanghai）
- 生图主动闭环 Production：`dpgwmrcmmoz5`，提交 `bdc4dcd`，成功，72 秒，2026-07-22 20:14（Asia/Shanghai）
- Schedule 恢复 Production：`dpk2eynbxljq`，提交 `50d2833`，成功，Cron 已恢复 `0 8 * * *`，2026-07-22 21:05（Asia/Shanghai）
- 搜索流式体验 Production：`dp9z057q9vsv`，提交 `6b59e04`，成功，2026-07-23 12:35（Asia/Shanghai）
- 后续生产 Deployment：以 EdgeOne Makers“构建部署”中该分支最新成功的 Production 行为准。

生产分支已从旧的 `codex/edgeone-makers-refactor` 切换到当前分支。切换前的稳定生产 Deployment 为 `dp8p5j6dewo0`；它只用于回滚，不再代表当前功能基线。

## 本版实现

本版以主办方“无需用户主动触发，AI 实时识别机会点或预判需求并主动提供服务”为目标，补齐回答后的主动机会闭环：

1. 对话回答完成后，后台并行执行语义机会判断，不阻塞主回答。
2. 由 LLM 判断写作优化、翻译复核、搜索更新、生图迭代、文档下一步和任务下一步，不用关键词硬编码替代语义判断。
3. 每轮最多生成一条机会；简单问答、算术、脑筋急转弯、待确认副作用和敏感内容不触发。
4. 机会写入 Makers 原生 `Event → Run → Notification`，通过 SSE `proactive_update` 实时刷新 Header 轮播和左栏提醒。
5. 机会带置信度阈值、6 小时同类冷却和过期时间，避免重复打扰与无限堆积。
6. 用户可“按建议处理 / 稍后 / 忽略”；状态持久化后同时影响 Header 轮播和左栏，不向新对话注入消息。
7. 文档上传信号通过 `/proactive` 的 `ingest_signal` 进入同一闭环，立即生成文档总结/下一步建议。
8. 用户采纳文档建议时，前端从 Makers Blob 读取并解析该 PDF，把有界文本作为仅本轮可见的文档上下文交给模型；输入区显示文件名，Blob Key 不进入可见指令，模型不会误去公网搜索同名文件。
9. 图片 Action 成功后，前端异步发送一次去重的 `image_generated` 事件；独立 LLM 判断比例、构图或版本适配价值，图片结果不会等待这次判断。图片 URL、Blob Key、二进制和完整提示词不写入主动事件；联系方式、证件号、账号和密钥类文本由程序化安全门再次拒绝。

完整设计见 [`CONTEST_SOLUTION.md`](CONTEST_SOLUTION.md)，系统边界见 [`ARCHITECTURE.md`](ARCHITECTURE.md)。

## Preview 线上证据

`dpbkmy4qt93e` 已完成以下真实线上验收：

- 页面在 30 秒内从“连接中”进入“已连接”，历史会话、日历和阅读工作区可读取。
- 输入管理层周报草稿后，模型正常流式整理回答；回答结束约 9 秒，左栏自动出现且只出现一条“周报可适配管理层偏好”。
- 主动机会包含自然说明和“按建议处理 / 稍后 / 忽略”，证明回答、识别、触达和反馈形成闭环。
- 测试站显示 69 条 Case，并从 Makers Blob 读取既有共享数据。
- PRO-09 在线标记为“通过”后保存为共享版本 157；新开独立页面重新读取仍为“通过”。
- Preview 默认域名受 EdgeOne 访问保护；必须从 Deployment 的“预览”按钮取得 3 小时签名链接。直接访问裸域名返回 401 不代表应用鉴权失败。

## Production 线上证据

`dp9z057q9vsv` 已完成搜索流式体验的非破坏性生产验收：

- “最近 AI 有什么新进展？”在正文生成过程中已出现就地来源链接；来源没有抢在回答前，也没有在回答底部重复生成目录。
- 进度从“正在理解你想解决的问题”进入“正在把核实后的信息整理成回答”，不再出现“工具已返回”等内部术语。
- 回答完成后立即停止生成状态并出现 3 条“猜你想继续问”；回答气泡与追问区域实测宽度均为 430px。
- DOM 审计显示 `turn_tool_invocations=1`、`turn_provider_calls=1`，本轮没有重复 SearchPro 请求。
- 线上模型实际使用 `[来源](URL)` 标签，补充回归后两种形态（URL-only 和显式“来源”）均统一渲染成小字引用。

`dptvf8ss3dl9` 已完成以下非破坏性真实生产验收：

- `PRO-10`：上传测试 PDF 后，真实产生 1 个 Signal、1 个 Event、1 个 Run 和 1 个 Notification，没有重复或跳过；文档提醒进入左栏与阅读库。
- 采纳文档建议时，`/chat` 使用一次性 `document_context`，准确提炼原文数字、计划和两条行动项；SSE 没有 `tool_call` 或 `rich_search`，证明不会再把同名私有文件误搜成公网网页。
- `PRO-11`：在两个新会话重复发送同一管理层周报请求，revision 和同语义机会数量均不增加；6 小时同类冷却生效。
- “稍后 / 已读 / 忽略”的时间戳在独立请求重新读取后仍存在；测试文档、Blob 对象和测试提醒已清理。
- 共享验收站已持久化到版本 159：69 条 Case 中，生产阻断项通过 43/44；剩余 `PRO-07` 只等待 EdgeOne 每日 Schedule 在真实触发时刻的日志证据，不用手动请求冒充通过。
- `dpgwmrcmmoz5` 的 `PRO-09` 增量验证：真实 `hy-image-v3.0` 生图成功、无降级并写入 Makers Blob；明确要求后续移动端版本时，`image_generated` 创建 1 个 0.95 置信度的 9:16 迭代建议；重复同一 Action 不创建第二条。测试图片和提醒已清理，共享验收站更新至版本 163。
- 两次 Schedule 探针及恢复结果已写入 `PRO-07`；共享验收站版本 165，运行信息指向 `dpk2eynbxljq`，结果仍为阻塞而不是把 500 误标为通过。

## 测试站

- 路径：生产主站 `/test-cases/`
- 数据：Makers Blob 强一致共享状态
- 写入：单人编辑、最后保存生效，不实现多人同时编辑冲突合并
- 证据：图片/视频通过预签名直传保存到 Makers Blob
- 审计：记录测试人、主机 ID、主机名称、编辑时间和字段
- Case 数：69
- 新增主办方闭环用例：PRO-09、PRO-10、PRO-11

绑定生产自定义域名后，任意主机访问同一网址都可读取和编辑同一份数据。详细启动、部署和恢复步骤见 [`ACCEPTANCE_SITE.md`](ACCEPTANCE_SITE.md)。

Makers Blob 的共享编辑已经完成；但 EdgeOne 默认 `edgeone.cool` 域名只提供 3 小时受保护预览。要让“任意主机长期直接打开”成为稳定生产入口，仍需在项目“域名管理”绑定一个用户可控制 DNS 的自定义域名。

## 自动化证据

- Python Agent：144 项通过。
- Node Cloud Functions、平台约束和验收持久化：21 项通过。
- 前端 Vitest：85 项通过，17 个测试文件。
- SQLite 只读迁移工具：2 项通过。
- ESLint：通过。
- TypeScript / Vite EdgeOne 构建：通过。
- `git diff --check`：通过。
- 验收数据结构：69 条 Case。

构建只有 Vite 大于 500 KB 的已知分包提示；没有构建错误。依赖安装日志提示一个高等级间接依赖审计项，未阻断构建，后续应在不破坏 EdgeOne 兼容性的前提下单独升级验证。

## 当前边界

- Cloudflare Workers AI 和腾讯会议个人 Token 仍只配置到 Preview，生产不继承测试 Token；生产优先使用已配置的混元能力。
- 腾讯会议是可选 Skill，不属于比赛主动服务主链路；未授权时必须自然提示，不伪造成功。
- EdgeOne Schedule 的代码、配置、原子锁和手动桥接测试已通过。2026-07-22 临时生产探针分别在 20:45 和 21:01 被平台真实触发，但受保护的默认 `edgeone.cool` 部署域名均在进入 Cloud Function 运行时前返回 500（日志为 0ms/0MB），没有下游 `/proactive` 调用或当前小时锁；Cron 已恢复 `0 8 * * *`。`PRO-07` 保持阻塞，绑定稳定自定义域名后必须重新取得 Function/Agent 双 2xx 与 `last_tick` 推进证据。
- 默认 `edgeone.cool` 地址受 3 小时访问保护；长期公开生产访问仍缺自定义域名和 DNS 绑定。
- DOC/DOCX、扫描 PDF OCR 和页码级引用不在本版完成范围。
- 无法保证所有外部搜索都在 5–10 秒完成；目标是单轮一次 `rich_search`、并行事实/视觉查询、缓存命中时优先快速返回。

## 发布与回滚

- 发布：推送生产分支后由 EdgeOne 自动构建 Production；必须确认状态成功，再对生产主站和 `/test-cases/` 做非破坏性冒烟。
- 回滚：在 EdgeOne Makers 选择上一成功 Production Deployment `dp8p5j6dewo0`。
- 回滚不删除 Makers Blob、Conversation Store、LangGraph Store/Checkpointer 或外部数据库数据。
- 测试站 JSON 导出只作为离线备份，Makers Blob 才是共享主数据。

详细发布命令和控制台步骤见 [`DEPLOYMENT.md`](DEPLOYMENT.md)。
