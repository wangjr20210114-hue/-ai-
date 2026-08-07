# Floris 跨端客户端接入文档（v1）

这份文档是网页、Android、鸿蒙与 iOS 共用的客户端边界。客户端只负责原生界面与设备能力；身份、权益、多租户隔离、聊天编排、富搜索、图片审核、路线、日程、Skills、记忆和持久化全部由 Floris Maker 后端负责。

机器可读词表见 [`contracts/mobile-client.v1.json`](../contracts/mobile-client.v1.json)。Android 的可运行参考实现位于 [`android/app/src/main/java/com/floris/android`](../android/app/src/main/java/com/floris/android)。

## 1. 接入原则

1. 除 CloudBase 登录外，业务客户端只访问一个 Floris Base URL。
2. 每个业务请求携带 Floris Bearer；会话相关请求再携带稳定的 `makers-conversation-id`。
3. 客户端不得复制权益、Skill 依赖、搜索规划、路线计算或多租户规则，直接渲染服务端投影。
4. JSON 指令携带 `response_language`。合法值为 `zh-CN`、`zh-TW`、`en`、`cat-cute`、`cat-cold`。
5. 未识别的响应字段忽略；未识别的 SSE 事件忽略；未识别的组件显示通用文本，不猜测副作用。

## 2. 身份与会话

### 2.1 游客

调用 `GET /auth/session`。服务端通过 `Set-Cookie: floris_session=<jwt>` 返回游客会话；原生客户端取出 JWT，作为后续 `Authorization: Bearer <jwt>` 使用。游客能力由服务端 entitlement/Skill 投影决定，客户端不能维护另一份白名单。

### 2.2 CloudBase 邮箱登录

流程为：

```text
CloudBase 发送/校验邮箱验证码
        ↓ CloudBase access_token
POST /auth/mobile/session
        ↓ Floris access_token + identity + contract_version
所有 Floris 业务 API
```

交换请求：

```http
POST /auth/mobile/session
Content-Type: application/json

{"access_token":"<cloudbase_access_token>","response_language":"zh-CN"}
```

客户端可以在 Floris token 未过期时直接恢复界面，不必每次启动联网。收到一次 `401` 时，正式账号刷新 CloudBase token 后重新交换；游客重新领取游客会话；同一请求最多自动重试一次。退出登录清除本机 token、活动请求和本账号的内存投影，不删除服务端数据。

## 3. 通用请求头

```http
Authorization: Bearer <floris_access_token>
makers-conversation-id: <stable-client-uuid>
Content-Type: application/json
```

`makers-conversation-id` 是客户端生成的稳定 UUID，不是用户 ID。服务端会用可信身份再次做租户命名空间隔离，客户端绝不能拼接或猜测服务器存储键。

## 4. 聊天、队列、停止与恢复

发送：

```http
POST /chat
Accept: text/event-stream
makers-conversation-id: 6f1b...

{
  "message":"最近 AI 有什么进展？",
  "client_message_id":"b665...",
  "reference_images":[],
  "response_language":"zh-CN"
}
```

同一次用户请求和助手回答共用一个 `client_message_id`。客户端从用户点击发送时开始计时。最多三张参考图；定位只有获得系统授权后才能加入 `current_location`。

定位对象必须包含 `latitude`、`longitude`、真实 `accuracy_meters`、毫秒时间戳 `captured_at` 和 `coordinate_type=wgs84`，且采集时间不得超过十分钟。收到 `browser_location_request` 后，用新的 `client_message_id` 重放原问题并带 `_location_retry=true`；无论成功、拒绝、超时、不可用还是失败，都通过 `location_request={state,attempted_at}` 明确回传，不能静默丢弃问题。

澄清卡提交体固定为：

```json
{
  "interaction_mode":"clarification",
  "activity":"clarification_answered",
  "clarification_response":{
    "id":"clarification-id",
    "source_message_id":"assistant-message-id",
    "answers":[{"id":"origin","label":"从哪里出发","value":"北京南站"}]
  }
}
```

单选字段的 `allow_custom_input/custom_placeholder` 由服务端决定，客户端只渲染并原样提交。

活动请求的恢复顺序：

1. `POST /messages` 恢复持久消息、工作区与当前 run/presentation。
2. 若 run 仍在运行，轮询 `POST /run`，只恢复该 Maker checkpoint，绝不重新发起普通模型请求。
3. 收到 `answer_complete` 后再把完整助手结果视为已提交。
4. 用户停止时立即移除本地临时回答并调用 `POST /stop`，请求体必须包含同一个 `client_message_id`。刷新后继续确认停止，已停止内容不得进入记忆。

客户端等待队列只是设备侧交互状态：每个对话最多 5 条，支持编辑、删除和打断上一条。只有轮到某条时才发送给 Maker。

### 4.1 SSE 事件

| 事件 | 客户端行为 |
|---|---|
| `progress_event` | 合并 `stage:activity`，展示公开进度，不展示思维链 |
| `stage_timing` | 合并服务端阶段耗时 |
| `ai_response` | 原样追加文本 |
| `ai_response_reset` | 清空本轮临时文本 |
| `search_results` | 增量合并来源，不覆盖已到达图片 |
| `search_media` | 增量合并审核图片，不覆盖已到达来源 |
| `paper_results` | 渲染论文结果 |
| `clarification_action` | 渲染主动询问表单，提交后销毁表单 |
| `map_action` / `calendar_action` / `side_effect_action` / `image_action` | 渲染版本化组件；副作用必须再次确认 |
| `experience_hint` | 在回答后显示短提示 |
| `follow_ups` | 渲染“猜你想问”，点击只填入输入框 |
| `browser_location_request` | 请求系统定位权限；拒绝后继续降级回答 |
| `error_message` | 结束本轮并显示精简错误 |
| `answer_complete` | 结束流，提交本轮呈现 |
| `ping` / 未知事件 | 忽略 |

## 5. 富搜索与图片

`search_results` 与 `search_media` 是两个可乱序到达的独立投影，必须按 ID 增量合并。客户端不能把候选图片直接放到答案顶部或末尾。

一张图片只有同时满足以下条件才可显示：

- `vision_reviewed == true`；
- `source_id` 在本轮来源中唯一存在；
- `media.source_url` 与该来源 `url` 完全一致；
- 回答正文含该来源的精确 Markdown 链接 `](source.url)`。

图片放在首次引用该来源的段落后。任何条件不满足时不显示图片，没有封面图或末尾兜底。旧的 `[[YUANBAO_MEDIA]]` 标记只清理，不参与定位。

搜索数量、候选图片数量和并行审图通过 `POST /intelligence` 的 `update_search_preferences` 持久化，不能只保存在本机。

## 6. 功能 API

| 能力 | API | 说明 |
|---|---|---|
| 会话列表/置顶/改名/删除 | `GET/POST/DELETE /conversations` | `touch_pointer` 与 `rename` 使用服务端元数据 |
| 消息/活动 run 恢复 | `POST /messages`, `POST /run` | 页面刷新、切对话与进程恢复的唯一依据 |
| 日程/地图/会议/图片组件 | `POST /workspace` | 所有动作带 `action_id` 与 `version` |
| 地点与路线 | `POST /places`, `POST /routes` | 腾讯地图 Provider 在服务端；客户端只绘制结果 |
| Skills 目录 | `POST /skill_marketplace` | 分类、描述、依赖、冲突、资格由服务端投影 |
| Skills 偏好/连接/私人 Skill | `POST /intelligence` | 启用、禁用、令牌连接和用户 Skill 均在此持久化 |
| Skill 审核 | `GET/POST /skill-uploads` | 私人安装与提交广场审核是两个状态 |
| 论文搜索与保存 | `GET/POST /papers` | 搜索结果可保存到阅读库 |
| PDF/文档助读 | `POST /reader`, `POST /document-text` | 后端按 `file_id` 提取，客户端无需内置 PDF 文本解析 |
| 阅读库 | `GET/POST/DELETE /library` | 文件夹、移动、自动整理、助读结果保存 |
| 文件 | `POST/HEAD/GET/DELETE /files` | 使用 Maker presigned upload 与 makers-parts-v1 |
| 个人信息/头像 | `GET/POST /profile` | 头像上传复用 Maker Blob，客户端只缓存显示副本 |
| 记忆与偏好 | `POST /intelligence` | 确认、拒绝、回滚、删除和清空由服务端执行 |
| 主动提醒/长期计划 | `POST /proactive` | 通知、推迟、忽略、工作流与步骤均由服务端状态机执行 |
| 用量 | `GET /provider_usage` | 客户端只展示服务端计量 |
| 清除数据 | `POST /reset`, `POST /reset-files` | 固定确认词 `DELETE`；保留账号与个人信息 |

## 7. 文件上传与下载

上传使用三步：向 Maker 申请上传地址、对预签名 HTTPS URL 直接 `PUT`、再向业务 API 注册/完成。对预签名 URL 绝不能携带 Floris Bearer。

下载先 `HEAD /files?key=...` 读取 `X-Floris-Part-Count`。多分片文件按 `GET /files?key=...&part=0..N-1` 顺序合并；`Accept-Ranges: makers-parts` 不是 HTTP Range，不得发送 `Range` 请求。先写 `.part` 临时文件，完整后原子改名，取消或失败时删除临时文件。

## 8. 原生平台 Adapter

可以按平台替换、但不能侵入业务 Contract 的能力：

- Android：系统 SpeechRecognizer、通知栏、文件选择器、FileProvider、定位权限。
- 鸿蒙：系统语音、通知、文件选择、定位权限。
- iOS：Speech、UserNotifications、DocumentPicker、CoreLocation。

语音只把识别文本写入输入框，用户确认后才发送。地图缩放可以决定客户端展示城市级、分段级或站点级路线，但路线与交通组合必须来自 `/routes`，客户端不得自己规划。

## 9. 禁止的“客户端开后门”

- 不直接调用模型 Provider、SearchPro、地图路线 Provider 或数据库。
- 不在客户端判断会员等级能否使用某 Skill。
- 不在客户端生成来源、伪造最新信息或补一张未审核图片。
- 不把 PDF 全文当作跨端契约要求客户端自行提取。
- 不把尚未结束或已经停止的助手临时回答写入历史/记忆。
- 不用本地设置冒充服务端偏好。
- 不向预签名 Blob URL 泄露 Floris Bearer。

## 10. 最小 Kotlin 调用示例

```kotlin
val body = buildJsonObject {
    put("message", "帮我规划杭州一日游")
    put("client_message_id", UUID.randomUUID().toString())
    put("response_language", "zh-CN")
}

client.streamChat(conversationId, body).collect { event ->
    when (event) {
        is ChatEvent.AiResponse -> renderDelta(event.content)
        is ChatEvent.SearchResults -> mergeSearch(event.payload)
        is ChatEvent.SearchMedia -> mergeSearch(event.payload)
        is ChatEvent.AnswerComplete -> commitRenderedTurn()
        is ChatEvent.Error -> finishWithError(event.content)
        else -> Unit
    }
}
```

上线前至少验证：游客普通问答、登录恢复、富搜索来源和严格图片绑定、刷新恢复、停止后不复活、5 条排队、Skills 启停与连接、跨城混合交通、日程写入、PDF 上传助读、记忆确认、主动提醒、头像缓存、退出登录隔离，以及另一个账号无法看到前一账号的内存态。
