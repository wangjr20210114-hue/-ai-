# Floris Android 与 dev 网页端功能对齐审计

> 审计日期：2026-08-06
> 仓库：`wangjr20210114-hue/-ai-`
> 工作分支：`floris-android`（仅此分支可修改；`dev` 只读，其他分支不动）
> 对照契约：[`docs/mobile-client-v1.md`](./mobile-client-v1.md)、[`contracts/mobile-client.v1.json`](../contracts/mobile-client.v1.json)
> 对照实现：`frontend/`（dev 网页端）与 `android/`（原生客户端）

## 1. 结论摘要

安卓客户端已经实现“一个后台、多个客户端”的接入原则：身份、聊天编排、搜索、媒体审核、路线、日程、Skills、记忆、持久化全部由 dev 后台（Maker）负责，客户端只做界面、系统权限、通知、文件选择与本地缓存；API 面与 `mobile-client.v1.json` 契约基本完整（`/chat`、`/messages`、`/run`、`/stop`、`/conversations`、`/workspace`、`/places`、`/routes`、`/intelligence`、`/skill_marketplace`、`/skill-uploads`、`/papers`、`/library`、`/reader`、`/document-text`、`/files`、`/profile`、`/proactive`、`/provider_usage`、`/reset`、`/reset-files`、`/auth/*`）。

逐功能域对照 dev 网页端后，主体能力已对齐；剩余差距集中在**聊天会话内的几个交互投影**和**两处输入/下载能力**：

1. 聊天中缺少 proactive 会话内卡片（网页 `ProactiveRenderer`：通知“帮我处理 / 一小时后提醒 / 忽略”，工作流“确认 / 拒绝 / 完成 / 跳过 / 标记失败 / 重试 / 补偿 / 结束”）。
2. 地图推荐动作卡缺少“添加到日程”（`calendar_offer` → `route_calendar_offer_accepted`）。
3. 聊天输入栏缺少 PDF/文档上传（网页输入栏支持 PDF 与图片；安卓目前只有参考图）。
4. 生图卡片缺少“保存到相册”（网页支持下载单张/批量 ZIP，安卓只有整条回答存图）。
5. `experience_hint` 事件已解析到消息模型，但界面未渲染（网页在回答后展示时效/技能提示）。
6. 会议结果卡缺少会议号、开始时间等结果详情（网页显示 `meeting_code`、`join_url`、`start_time`）。

以上均为客户端投影/输入能力，不涉及复制后台业务逻辑，符合客户端边界。

## 2. 审计方法

- 枚举 dev 前端功能文件（`frontend/src/features/*`、`frontend/src/components/*`）与安卓页面（`android/app/src/main/java/com/floris/android/ui/*`）。
- 以 `mobile-client-v1.md` 的 SSE 事件表、功能 API 表与操作表为对照词表。
- 逐项核对：接口是否存在于 `FlorisApi`/`FlorisRepository`；事件是否被 `ChatEventDispatcher`/`ChatViewModel` 消费；UI 是否渲染。
- 复查工作区未提交改动（会议确认卡编辑、`stage_timing`、proactive 信号、工作流失败/补偿按钮），确认其为对齐工作的一部分而非半成品。

## 3. 已对齐清单

| 功能域 | 网页端 | 安卓端 | 结论 |
| --- | --- | --- | --- |
| 身份与会话 | AuthDialog、CloudBase OTP、Guest | LoginScreen、CloudBaseAuthApi、AuthManager、Keystore | 对齐 |
| SSE 流式聊天 | chatTransport、打字机 | FlorisClient、StreamTypewriter | 对齐 |
| 等待队列 | TurnQueueDrawer（编辑/删除/打断） | TurnQueueDrawer（编辑/删除/立即发送） | 对齐 |
| 停止与重试 | stop、retryFailedAnswer | stop、retryLast | 对齐 |
| 澄清卡 | ClarificationCard（single/multi/boolean/date/time/datetime） | ClarificationForm | 对齐 |
| 富搜索来源/媒体 | searchResults/searchMedia 增量合并 + source_id 绑定 | SourceBoundAnswer/SearchSourcesRow/MediaGrid | 对齐 |
| 搜索进度时间线 | ProgressRenderer + stage_timing | SearchProgress + stageTimingsMs（本次工作区） | 对齐 |
| 论文卡片 | PaperRenderer | PaperListCard | 对齐 |
| 地图动作 | WorkspaceActionRenderer（查看地图/添加日程） | MapActionBody（查看地图，缺“添加日程”） | 差距见 4.2 |
| 日历动作 | calendar_changes 预览与确认 | CalendarActionBody | 对齐 |
| 会议创建 | MeetingConfirmationCard（编辑/校验/警告/加入） | meetingActionBody（本次工作区完成） | 对齐（结果详情差距见 4.6） |
| 生图工坊 | ImageStudioCard（对比、再编辑、下载） | ImageActionBody（对比、再编辑，缺下载） | 差距见 4.4 |
| 追问 | followUps 填入输入框 | FollowUpChips | 对齐 |
| 经验提示 | experienceHints 渲染 | 已解析未渲染 | 差距见 4.5 |
| 回答操作 | 复制、保存图片 | 复制、保存为图片 | 对齐 |
| 参考图/语音 | 上传图片、语音输入 | PickMultipleVisualMedia、VoiceInputController | 对齐 |
| 聊天文档上传 | PDF 上传 + 注册阅读库 + 信号 | 无（阅读页有上传） | 差距见 4.3 |
| 会话历史 | ConversationSidebar（重命名/删除/状态） | HistoryScreen（重命名/滑动删除/状态） | 对齐 |
| 日历 | CalendarMonthView + 日程编辑 | CalendarScreen 月视图 + ScheduleEditorDialog | 对齐 |
| 地图/路线 | MakersMap + RouteJourneyCard | MapScreen（WebView 腾讯地图）+ RouteCard | 对齐 |
| Skills 广场 | SkillCatalogView、SkillImportView、SkillReferenceView | SkillsScreen（目录、安装、导入、组件 API） | 对齐 |
| 阅读库 | ReadingLibraryPanel（文件夹/移动/自动整理/删除/助读） | ReadingScreen（同能力 + 系统阅读器打开） | 对齐 |
| 设置/个性化 | AppSettingsButton（偏好、用量、清除数据） | SettingsScreen + PersonalizationScreen | 对齐 |
| 主动提醒面板 | ProactiveBriefPanel | ProfileScreen ProactiveCard（mark_read/snooze/dismiss） | 对齐 |
| 工作流管理 | PersonalizationScreen 工作流卡（confirm/reject/cancel/complete/skip/fail/retry/compensate） | PersonalizationScreen WorkflowCard（本次工作区补齐 fail/compensate） | 对齐 |
| 后台通知 | 浏览器通知 | WorkManager + ProactiveNotifier | 对齐 |
| 新手引导 | FlorisOnboarding | OnboardingOverlay 聚光灯 | 对齐 |
| 会话内 proactive | ProactiveRenderer（通知+工作流） | 无 | 差距见 4.1 |

## 4. 差距与实施项

### 4.1 聊天内 proactive 卡片（P0）

网页在 AI 气泡内渲染：

- 通知（前 3 条、非 dismissed）：“帮我处理”（`mark_read` + 填入 `action_prompt` 草稿）、“一小时后提醒”（`snooze` until=now+3600）、“忽略”（`dismiss`）。
- 待确认工作流：“确认”（`confirm_workflow`）、“暂不”（`reject_workflow`）。
- 进行中工作流：当前步骤“完成这一步 / 跳过 / 遇到问题”（`complete/skip/fail_workflow_step`）、补偿中“已处理影响”（`compensate_workflow_step`）、失败“重试”（`retry_workflow_step`）、整体“结束计划”（`cancel_workflow`）。

安卓实现：新增 `ProactiveChatCard`，`ChatViewModel` 订阅 `repository.proactiveStateFlow` 并提供操作转发（含 busy 状态），`ChatScreen` 在 AI 行内渲染。

### 4.2 地图推荐“添加到日程”（P0）

`WorkspaceActionPayload.calendar_offer == true` 且本轮还没有 `calendar_changes` 动作时，在地图动作卡显示“添加到日程”；点击以 `activity=route_calendar_offer_accepted`、`route_plan_id` 发送一条用户消息。

### 4.3 聊天 PDF/文档上传（P1）

输入栏增加文档按钮（`OpenDocument`，`application/pdf` 等），复用 `FlorisRepository.uploadReadingDocument`（上传 → 注册阅读库 → `file_uploaded` 信号），并在会话内追加“已上传文档”用户消息与“已打开 PDF/论文”AI 提示消息。

### 4.4 生图卡片保存到相册（P1）

生图成功后在图片下方提供“保存到相册”：经 HTTPS 下载图片字节 → `ImageSaver` 写入系统相册。

### 4.5 经验提示渲染（P1）

AI 回答正文后渲染 `experience_hints`：`freshness` 与 `skill` 两类；`login_required` 且为游客时显示登录引导文案。

### 4.6 会议结果详情（P2）

非待确认状态的会议卡补充 `meeting_code`、`start_time`、`trace_id`、`join_url` 展示。

## 5. 验收

- `cd android && ./gradlew :app:testDebugUnitTest` 全绿（含新增纯逻辑测试）。
- 全部改动只发生在 `floris-android` 分支；`dev` 分支不修改、不合并。
