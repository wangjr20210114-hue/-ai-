# Floris Android 与 dev 功能对齐审计

> 审计日期：2026-08-07
>
> Android 分支：`floris-android`
>
> 后端：直接复用 `https://floris-dev.jlutx.com`，不复制任何 Maker 业务逻辑
> 只读对照：`origin/dev`、OpenAPI 1.9.0、组件与 SSE v1 Contract

## 结论

Android 已采用“原生客户端 + dev 后端”的单后端结构。身份、租户隔离、权益、Skills、聊天规划、富搜索、审图、地点核验、路线链、日程、论文、记忆、主动提醒和持久化全部由 dev/Maker 决定；Android 只实现 Compose 界面、系统鉴权交换、权限、定位、语音、通知、文件选择、相册、地图绘制、短期渲染缓存和每会话等待队列。

代码级功能面已覆盖网页登录态的公开能力。上线前仍需在真机上完成登录、定位、通知、语音、地图 Key、相册和文件选择的设备验收，以及使用 dev 账号执行端到端在线冒烟。

## 公开接口覆盖

`FlorisApi` 的业务路径由单元测试做精确集合校验，多一个或少一个都会失败：

- 身份：`/auth/session`、`/auth/mobile/session`、`/auth/logout`、`/profile`
- 聊天：`/chat`、`/messages`、`/run`、`/stop`、`/conversation`、`/conversations`
- 文件与阅读：`/files`、`/document-text`、`/papers`、`/reader`、`/library`
- 工作区：`/workspace`、`/places`、`/routes`
- 个性化：`/intelligence`、`/proactive`、`/provider_usage`
- Skills：`/skill_marketplace`、`/skill-uploads`
- 数据维护：`/reset`、`/reset-files`

CloudBase 登录是唯一直接调用 Provider 的身份 Adapter；腾讯地图 WebView 只绘制后端已核验地点与路线。其他 Feature/View 不允许自行访问业务后端、模型、搜索 Provider、数据库或地图路线 Provider。

## 功能对齐矩阵

| 功能域 | Android 实现 | 权威状态来源 |
| --- | --- | --- |
| 游客与 CloudBase 邮箱登录 | OTP、短期 Floris Bearer、Keystore refresh token、单次 401 恢复、退出隔离 | CloudBase + `/auth/mobile/session` |
| 会话 | 新对话置顶、首问命名、改名、删除、历史恢复、切换对焦最后一次提问 | `/conversations`、`/messages` |
| 流式聊天 | SSE 正文、进度、来源、媒体、卡片、追问、用量；未知事件忽略 | `/chat` + chat-events-v1 |
| 中断与恢复 | 最多 5 条等待队列；编辑/删除/打断；停止 tombstone；进程恢复同一 Maker run | `/stop`、`/run` |
| 富搜索与图片 | 发送即计时；来源/审图乱序增量合并；严格 `source_id/source_url` 段落绑定；无兜底图 | `search_results`、`search_media` |
| 主动澄清 | 全字段表单、自定义地点、提交后只读摘要、正确 `answers[]` 协议 | `clarification_action` |
| 地点与路线 | WGS84 新鲜定位、失败回传、手动起点澄清、多交通 Section、缩放分层、当前视口路段聚焦、步行点线 | `/chat`、`/places`、`/routes` |
| 日程 | 月视图、创建/编辑/删除、路线转日程、确认/取消与版本锁 | `/workspace` |
| 会议与生图 | 参数编辑、确认、结果详情、加入链接、继续编辑、保存相册 | `/workspace`、`/image` |
| Skills | 分类、启停、依赖/冲突、连接、私有 Skill 多种导入、审核、组件 API 文档 | `/skill_marketplace`、`/intelligence`、`/skill-uploads` |
| 阅读与论文 | 搜索、保存、上传、服务端文本提取、助读流、文件夹、移动、自动整理、结果保存 | `/papers`、`/files`、`/document-text`、`/reader`、`/library` |
| 个人中心 | 昵称、头像上传与本地显示缓存、会员、用量、新手介绍、退出 | `/profile`、`/provider_usage` |
| 记忆与主动提醒 | 记忆/规则确认、偏好、工作流、系统通知与会话内卡片 | `/intelligence`、`/proactive` |
| 设置 | 五种语言、主题、本地新手偏好；搜索/地图/主动偏好完全服务端持久化 | 本机 UI 设置 + `/intelligence`、`/proactive` |
| 清空数据 | 固定确认词 `DELETE`；不清除个人资料 | `/reset`、`/reset-files` |

## 本轮修复

1. 定位请求补齐精度、采集时间、WGS84、十分钟新鲜度与失败状态；网络/GPS/被动 Provider 并行竞争首个可信结果。
2. `browser_location_request` 变成可持久恢复的逻辑重试；拒绝、超时或不可用时仍把原问题交给 dev 继续澄清。
3. 澄清答案改为 `interaction_mode + activity + source_message_id + answers[]`，并支持服务端下发的自定义地点输入。
4. 路线 UI 复用 dev 的 Section 投影：跨城/市内层级、混合交通颜色、视口焦点、非当前段置灰、步行点线和旧 Provider 快照分段兼容；不重算路线。
5. 搜索与图片偏好移出全局 DataStore，避免跨账号旧值；只显示 dev 回读的服务端状态。
6. 切换会话改为对焦最后一次用户提问；显式停止/切换造成的协程取消不会误入自动恢复。
7. PDF 上传后的客户端提示通过公开 `/conversation` 写入 Maker，会话切换和重启后仍可恢复。
8. API 集合、定位/澄清协议和路线投影新增单元测试；Android 单测、Lint、Debug APK 加入 CI。

## 验收门槛

- `./gradlew :app:testDebugUnitTest :app:lintDebug :app:assembleDebug`
- `node --test cloud-functions/mobile-contract.test.js`
- `node --test cloud-functions/platform-reuse.test.js`
- dev 在线冒烟：游客基础聊天、登录富搜索、来源与图片、刷新恢复、停止与队列、定位澄清、跨城混合路线、路线转日程、Skills、PDF 助读、个人资料、偏好和主动提醒。
- 真机验收：邮箱验证码、Token 恢复、系统权限、语音、定位、腾讯地图、通知、文件、相册与后台恢复。

2026-08-07 已完成自动验收：Android 127 个单元测试零失败、Lint 零错误、Debug APK 构建成功；跨端/平台复用 Contract 19 项零失败；`floris-dev.jlutx.com` 游客会话、会话恢复、run、Skills 目录、工作区、个性化与一次完整聊天 SSE 均返回成功且包含 `[DONE]`。登录富搜索和系统能力仍按上面的真机验收项执行。
