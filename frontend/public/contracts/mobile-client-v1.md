# Floris 跨端客户端 API v1

这份文档是 Web、Android、HarmonyOS 和 iOS 的统一接入说明，对应 OpenAPI `1.5.0`。客户端只负责界面、系统权限、通知、文件选择和本地缓存；聊天编排、搜索、Skills、地图、日程、论文、权益、身份隔离和持久化均由 Floris 后端提供。

## 1. 契约文件

开发环境：`https://floris-dev.jlutx.com`

| 文件 | 用途 |
| --- | --- |
| `/contracts/floris-client-v1.openapi.json` | 全部 HTTP/SSE 接口、请求与响应类型，可用于生成客户端代码 |
| `/contracts/chat-events-v1.schema.json` | 聊天、论文助读和图片编辑的流式事件 |
| `/contracts/floris-components-v1.schema.json` | 搜索来源、图片、论文、日程、地图、路线和操作卡片 |

客户端必须遵守以下兼容规则：

- 未知 SSE 事件直接忽略。
- 未知组件保留正文，显示“客户端版本较旧”即可，不能中断会话。
- `source_id` 是搜索来源与图片的确定性绑定，客户端不得自行猜测或重新配对。
- `publisher_domain` 是跨客户端统一的发布者边界；同一域的多篇内容可以互补，但不能统计为多个独立来源。
- 日程、地图、会议和图片操作以服务端返回的 `WorkspaceAction.status` 为准。
- 新增可选字段属于 v1 兼容更新；删除字段或改变含义会发布新的主版本。

## 2. 最小接入流程

1. 使用 CloudBase SDK 完成当前已启用的登录方式，并由 CloudBase 刷新自己的凭据。
2. 原生 App 调用 `POST /auth/mobile/session`，换取有效期一小时的 Floris Bearer。
3. 为每个会话生成稳定、不透明的 `makers-conversation-id`。
4. 调用 `POST /messages` 恢复界面，再调用 `POST /chat` 发送问题。
5. 按 SSE `type` 逐条渲染正文、来源、图片和卡片。
6. 所有确认、取消或状态变更都调用 `/workspace`，不要在客户端伪造成功状态。

原生请求统一携带：

```http
Authorization: Bearer <floris-access-token>
makers-conversation-id: yb7_<opaque-id>
```

Web 使用 `HttpOnly + Secure + SameSite=Lax` Cookie，不读取 Cookie 内容。登录账号会话有效期为 30 天，并在临近过期时由服务端滚动续期；原生 App 的长期登录由 CloudBase refresh token 负责。

## 3. 接口总览

| 范围 | 接口 |
| --- | --- |
| 登录与账号 | `GET /auth/session`、`POST /auth/cloudbase/session`、`POST /auth/mobile/session`、`POST /auth/logout`、`GET/HEAD/POST /profile` |
| 聊天与会话 | `POST /chat`、`POST /messages`、`POST /conversation`、`GET/POST /conversations`、`POST /stop` |
| 文件 | `POST/GET/HEAD/DELETE /files`、`POST /document-text`（通常由 `/reader` 内部使用） |
| 日程与地图状态 | `POST /workspace`、`POST /image` |
| 个性化 | `POST /intelligence`、`POST /proactive`、`GET /provider_usage` |
| Skills | `POST /skill_marketplace`、`GET/POST /skill-uploads` |
| 地图 | `POST /places`、`POST /routes` |
| 论文 | `GET/POST /papers`、`GET/POST/DELETE /library`、`POST /reader` |
| 数据维护 | `POST /reset-files`、`POST /reset` |

富搜索不是一条需要客户端自行组合的独立链路。客户端只向 `/chat` 提问，后端决定是否搜索，并流式返回 `progress_event`、`search_results`、`search_media` 和正文。

## 4. 登录与个人资料

### GET /auth/session

读取身份、会员权益和当前可用登录方式。

```bash
curl "$BASE/auth/session" \
  -H "Authorization: Bearer $TOKEN"
```

### POST /auth/cloudbase/session

Web 在 CloudBase 邮箱登录成功后建立浏览器会话。

```bash
curl -X POST "$BASE/auth/cloudbase/session" \
  -H "Content-Type: application/json" \
  -d '{"access_token":"<cloudbase-access-token>"}'
```

### POST /auth/mobile/session

Android、HarmonyOS 和 iOS 用当前 CloudBase access token 换取短期 Floris Bearer。

```bash
curl -X POST "$BASE/auth/mobile/session" \
  -H "Content-Type: application/json" \
  -d '{"access_token":"<cloudbase-access-token>"}'
```

响应示例：

```json
{
  "access_token": "<floris-token>",
  "token_type": "Bearer",
  "expires_in": 3600,
  "contract_version": "1",
  "identity": {
    "id": "user-id",
    "display_name": "Floris 用户",
    "avatar_url": "/profile?avatar_key=..."
  }
}
```

### POST /auth/logout

退出当前 Web 会话。

```bash
curl -X POST "$BASE/auth/logout" \
  -H "Cookie: floris_session=<browser-cookie>"
```

### GET /profile

读取登录用户的个人资料。

```bash
curl "$BASE/profile" \
  -H "Authorization: Bearer $TOKEN"
```

### HEAD /profile

在下载头像前读取头像类型和缓存信息。

```bash
curl -I "$BASE/profile?avatar_key=<server-issued-key>" \
  -H "Authorization: Bearer $TOKEN"
```

### POST /profile

先创建头像上传地址，再把文件 `PUT` 到返回的 `url`，最后提交昵称与 `avatar_key`。

```bash
curl -X POST "$BASE/profile" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"operation":"create_avatar_upload","content_type":"image/webp","size":123456}'
```

```bash
curl -X POST "$BASE/profile" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"operation":"update","display_name":"小花","avatar_key":"<server-issued-key>"}'
```

原生客户端更新资料后若响应包含新的 `access_token`，应原子替换旧 Bearer。

## 5. 聊天、搜索与会话

### POST /messages

这是聊天界面的统一恢复接口，一次返回消息、搜索来源与图片、论文、日程、地图、待处理操作和当前运行状态。

```bash
curl -X POST "$BASE/messages" \
  -H "Authorization: Bearer $TOKEN" \
  -H "makers-conversation-id: $CID" \
  -H "Content-Type: application/json" \
  -d "{\"conversation_id\":\"$CID\"}"
```

### POST /chat

发送一个问题并读取 SSE。

```bash
curl -N -X POST "$BASE/chat" \
  -H "Authorization: Bearer $TOKEN" \
  -H "makers-conversation-id: $CID" \
  -H "Content-Type: application/json" \
  -d '{"message":"最近 AI 有什么新进展？","client_message_id":"msg_01"}'
```

典型事件顺序：

```text
progress_event
search_results
ai_response (重复增量)
search_media (审核完成后渐进补入)
answer_complete
data: [DONE]
```

`ai_response.content` 是增量文本。图片审核不阻塞正文首字，`search_media` 可以与多条 `ai_response` 交错到达；`search_results` 和 `search_media` 也可能多次到达或先后互换。客户端必须按 `source_id` 合并，不能先放一个最终占位卡再删除，也不能因为媒体稍后到达而重置正文或计时。`search_media.media` 只包含 `vision_reviewed=true` 的图片；视觉审核达到本轮截止时间时保留已经完成且通过的部分结果，未完成、失败或未通过的候选一律不显示。

图片位置由回答中的自然来源引用决定：客户端只把审核图片插入其 `source_id/source_url` 对应的精确链接段落之后。回答没有引用该来源时不显示图片，禁止把未引用图片集中放在开头或结尾，也没有“文章主图”兜底。

需要渲染结构化组件的事件可能额外携带 `payload.component_api`。其中每项只有 `version`、`action` 和业务 `payload`；`tenant_id`、`user_id`、`request_id` 等身份范围只在服务端可信 Adapter 内存在，不会交给模型或客户端。客户端按 `action` 选择组件，遇到未知 action 时保留正文并忽略该项。

```json
{
  "component_api": {
    "version": "2026-08-04",
    "publications": [
      {
        "version": "2026-08-04",
        "action": "search.evidence.publish",
        "payload": {
          "source_id": "source-01",
          "title": "已核验来源",
          "url": "https://example.com/source"
        }
      }
    ]
  }
}
```

#### 每会话发送队列与网络恢复

客户端为每个会话维护独立 FIFO，可以在当前回答生成时继续接收用户消息。队列属于客户交互状态；服务端通过 Makers 会话运行状态保证同一会话同时只准入一轮，不要自建 Redis/Celery 队列。

1. 为每次发送生成稳定 `client_message_id`，立即显示用户消息并加入该会话队列。
2. 只有队首调用 `POST /chat`；收到 `[DONE]` 或可核验终态后再处理下一条。
3. 连接中断时调用 `POST /messages`读取同一 `client_message_id` 的 Maker run。`running` 时继续等待，`completed` 时恢复检查点结果；只有确认请求未被准入时才使用原 ID 重发。
4. 显式停止必须调用 `POST /stop` 并携带队首 `client_message_id`。立即删除当前 AI 回答，不保留部分文本、来源或卡片，也不新增“已停止”提示消息。
5. 断网或停止请求超时时暂停后续队列，先用 `POST /messages` 核对同一 `client_message_id`；若 Maker run 已为 `cancelled` 就直接确认，只有尚未取消时才重试同一停止请求。过期停止不得中止新队首。
6. 队首在 Maker 终态或精确停止确认前必须继续保存在本地 FIFO；切换会话或刷新只分离传输。重新进入时先用 `POST /messages` 对账同一 `client_message_id`，确认终态后才出队，不能在发起 `POST /chat` 时提前删除。

`POST /stop` 返回 2xx 时仍须核对响应体的 `client_message_id` 与当前队首一致，匹配后才可放行下一条；客户端应给 Maker 原生会话状态留出合理的读写时间，不要用激进的短超时提前中断取消写入。

### POST /conversation

需要单独保存消息时，通过服务端会话存储追加，不在客户端复制持久化逻辑。

```bash
curl -X POST "$BASE/conversation" \
  -H "Authorization: Bearer $TOKEN" \
  -H "makers-conversation-id: $CID" \
  -H "Content-Type: application/json" \
  -d '{"role":"user","content":"帮我规划杭州一日游","metadata":{"id":"msg_01"}}'
```

### GET /conversations

读取当前账号的会话列表。

```bash
curl "$BASE/conversations" \
  -H "Authorization: Bearer $TOKEN"
```

### POST /conversations

创建或更新侧栏中的会话指针。

```bash
curl -X POST "$BASE/conversations" \
  -H "Authorization: Bearer $TOKEN" \
  -H "makers-conversation-id: $CID" \
  -H "Content-Type: application/json" \
  -d "{\"operation\":\"touch_pointer\",\"conversation_id\":\"$CID\",\"title\":\"杭州一日游\",\"message_count\":2}"
```

### POST /stop

取消并彻底丢弃当前生成。`client_message_id` 用于防止断网后延迟到达的停止请求误伤下一轮。

`POST /stop` 与网络恢复是两个不同操作：停止会永久丢弃该轮的正文、来源、图片、卡片和派生记忆，不创建提示卡，也不得被恢复逻辑重新拉起；网络恢复只通过 `POST /messages` 查询同一个 Maker run，不新建第二次生成。

```bash
curl -X POST "$BASE/stop" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"conversation_id\":\"$CID\",\"client_message_id\":\"msg_01\"}"
```

## 6. 文件

### POST /files

创建私有文件上传地址。

```bash
curl -X POST "$BASE/files" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"conversation_id\":\"$CID\",\"name\":\"paper.pdf\",\"content_type\":\"application/pdf\",\"size\":245760}"
```

响应中的 `url` 仅用于上传；`content_url` 用于登录后的读取。客户端不能自行拼接存储 key。

上传意图按内容能力校验：PDF 使用论文助读权益，图片使用视觉理解或图片工坊权益。读取、HEAD 与删除只校验登录身份和 Makers Blob 的租户前缀，不会因为用户后来关闭某个 Skill 而让既有私有文件失联。

### HEAD /files

读取文件大小与分片大小。

```bash
curl -I "$BASE/files?key=<server-issued-key>" \
  -H "Authorization: Bearer $TOKEN"
```

以 `X-Floris-File-Size`、`X-Floris-Part-Size`、`X-Floris-Part-Count` 和 `X-Floris-Part-Protocol: makers-parts-v1` 为准。旧网页兼容期内仍可能看到 `X-Yuanbao-*` 别名。

### GET /files

读取完整文件；大文件按 `part=0`、`part=1` 顺序获取并合并。

```bash
curl "$BASE/files?key=<server-issued-key>&part=0" \
  -H "Authorization: Bearer $TOKEN" \
  --output part-0.bin
```

这不是 HTTP Range：服务端不会返回 `Accept-Ranges: bytes`，客户端也不要发送 `Range`。每个 `part=N` 都是状态码 200 的 Floris 查询分片，边界来自 `X-Floris-Part-Start` 与 `X-Floris-Part-End`。

### DELETE /files

删除当前账号空间中的一个文件。

```bash
curl -X DELETE "$BASE/files?key=<server-issued-key>" \
  -H "Authorization: Bearer $TOKEN"
```

## 7. 日程、地图状态与图片版本

### POST /workspace

读取整个工作区：

```bash
curl -X POST "$BASE/workspace" \
  -H "Authorization: Bearer $TOKEN" \
  -H "makers-conversation-id: $CID" \
  -H "Content-Type: application/json" \
  -d '{"operation":"get"}'
```

确认一个服务端操作：

```bash
curl -X POST "$BASE/workspace" \
  -H "Authorization: Bearer $TOKEN" \
  -H "makers-conversation-id: $CID" \
  -H "Content-Type: application/json" \
  -d '{"operation":"confirm_action","action_id":"action_01","version":1}'
```

客户端必须回传拿到的 `version`。若返回 `409`，重新读取 `/workspace` 后再显示最新状态。

### POST /image

基于已成功的图片 Action 创建新版本，并流式接收进度。

```bash
curl -N -X POST "$BASE/image" \
  -H "Authorization: Bearer $TOKEN" \
  -H "makers-conversation-id: $CID" \
  -H "Content-Type: application/json" \
  -d '{"prompt":"保持构图，把天空改成黄昏","parent_action_id":"action_01"}'
```

事件为 `image_progress`、`image_action`、`ping`，最后是 `[DONE]`。

## 8. 个性化与主动服务

### POST /intelligence

读取记忆、搜索设置、地图设置和 Skill 状态。

```bash
curl -X POST "$BASE/intelligence" \
  -H "Authorization: Bearer $TOKEN" \
  -H "makers-conversation-id: $CID" \
  -H "Content-Type: application/json" \
  -d '{"operation":"get"}'
```

修改搜索偏好：

```bash
curl -X POST "$BASE/intelligence" \
  -H "Authorization: Bearer $TOKEN" \
  -H "makers-conversation-id: $CID" \
  -H "Content-Type: application/json" \
  -d '{"operation":"update_search_preferences","preferences":{"result_limit":8,"image_limit":3,"parallel_image_search":true}}'
```

这三个值必须发送到 `/intelligence` 并采用服务端返回的新投影。它们不是客户端本地显示设置：`result_limit` 控制后端候选来源上限，`image_limit` 控制视觉审核上限，`parallel_image_search` 控制后端候选抓取并发。仅写入 DataStore、UserDefaults、Preferences 或 LocalStorage 不会改变检索行为。

地图偏好的八个字段为：`service_mode`、`place_result_limit`、`route_stop_limit`、`search_timeout_seconds`、`preferred_route_mode`、`route_strategy`、`near_time_tolerance_minutes`、`learn_route_preferences`。更新时同样调用 `update_map_preferences`，不要只在客户端改变选择器。

### POST /proactive

读取提醒、工作流与主动服务设置。

```bash
curl -X POST "$BASE/proactive" \
  -H "Authorization: Bearer $TOKEN" \
  -H "makers-conversation-id: $CID" \
  -H "Content-Type: application/json" \
  -d '{"operation":"get"}'
```

提醒对象的网络字段统一使用 snake_case，尤其是 `action_prompt` 和 `snoozed_until`。Kotlin/Swift/ArkTS 若在模型层使用 `actionPrompt`、`snoozedUntil`，必须通过序列化注解映射，不能依赖成员名自动推断。例如 Kotlinx Serialization 使用 `@SerialName("action_prompt")` 和 `@SerialName("snoozed_until")`。“帮我处理”直接把 `action_prompt` 作为下一轮用户请求；推迟提醒显示 `snoozed_until` 的 Unix 时间。

### GET /provider_usage

读取当前账号在 Floris 中记录的用量。

```bash
curl "$BASE/provider_usage" \
  -H "Authorization: Bearer $TOKEN" \
  -H "makers-conversation-id: $CID"
```

## 9. Skills

### POST /skill_marketplace

读取 Skill 分类、描述、依赖/冲突关系、启用状态与公开组件接口。

```bash
curl -X POST "$BASE/skill_marketplace" \
  -H "Authorization: Bearer $TOKEN" \
  -H "makers-conversation-id: $CID" \
  -H "Content-Type: application/json" \
  -d '{"operation":"catalog"}'
```

### GET /skill-uploads

读取当前账号的私有 Skill 和审核状态。

```bash
curl "$BASE/skill-uploads" \
  -H "Authorization: Bearer $TOKEN"
```

### POST /skill-uploads

解析公开仓库中的 `SKILL.md`。仓库白名单、URL 归一化、下载大小和文本格式均由服务端校验；客户端不能直接抓取 GitHub 或 GitLab：

```bash
curl -X POST "$BASE/skill-uploads" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"operation":"resolve_url","source_url":"https://github.com/example/floris-skill"}'
```

响应中的 `skill` 是标准 `SkillDraft`。将它原样作为 `skill` 调用 `/intelligence` 的 `install_user_skill`，才会保存到当前账号：

```bash
curl -X POST "$BASE/intelligence" \
  -H "Authorization: Bearer $TOKEN" \
  -H "makers-conversation-id: $CID" \
  -H "Content-Type: application/json" \
  -d '{"operation":"install_user_skill","skill":{"name":"Research helper","description":"","instructions":"Prefer primary sources.","source_type":"url","source_url":"https://github.com/example/floris-skill"}}'
```

创建 ZIP 上传：

```bash
curl -X POST "$BASE/skill-uploads" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"operation":"create","name":"my-skill.zip","content_type":"application/zip","size":2048}'
```

提交声明式 Skill 审核：

```bash
curl -X POST "$BASE/skill-uploads" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"operation":"publish_declarative","source_skill_id":"user-example-01","name":"My Skill","description":"简短说明","instructions":"执行说明"}'
```

“保存到我的 Skills”和“提交到广场审核”是两个状态，客户端不能把私有保存显示成已进入广场审核。

## 10. 地图

### POST /places

搜索经过服务端核验的地点。

```bash
curl -X POST "$BASE/places" \
  -H "Authorization: Bearer $TOKEN" \
  -H "makers-conversation-id: $CID" \
  -H "Content-Type: application/json" \
  -d '{"query":"灵隐寺","city":"杭州","limit":6}'
```

### POST /routes

规划推荐地点之间的真实路线。

```bash
curl -X POST "$BASE/routes" \
  -H "Authorization: Bearer $TOKEN" \
  -H "makers-conversation-id: $CID" \
  -H "Content-Type: application/json" \
  -d '{
    "places":[
      {"place_id":"a","name":"灵隐寺","address":"杭州","latitude":30.2403,"longitude":120.1022},
      {"place_id":"b","name":"西湖","address":"杭州","latitude":30.2507,"longitude":120.1438}
    ],
    "mode":"transit",
    "strategy":"least_cost",
    "optimize":false
  }'
```

`route.legs` 表示推荐地点之间的路段；`leg.scope` 区分 `intercity`、`local` 与 `unknown`，每个 `leg.sections` 可包含步行、公交、轨道、骑行或驾车等多种交通方式。`route.transit.modes` 由 Provider 返回的 `sections/vehicle` 归一化得到，客户端不得按城市或线路名称猜测交通方式。客户端应为不同 `section.mode` 使用一致且可辨认的颜色，并根据地图缩放级别自然调整路线细节。

## 11. 论文与阅读

### GET /papers

搜索论文。

```bash
curl "$BASE/papers?topic=transformer" \
  -H "Authorization: Bearer $TOKEN"
```

### POST /papers

核验并保存一篇公开论文。

```bash
curl -X POST "$BASE/papers" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"arxiv_id":"1706.03762","title":"Attention Is All You Need","source_url":"https://arxiv.org/abs/1706.03762"}'
```

### GET /library

读取“我的阅读”、文件夹与自动整理设置。

```bash
curl "$BASE/library" \
  -H "Authorization: Bearer $TOKEN"
```

### POST /library

创建一个阅读文件夹。

```bash
curl -X POST "$BASE/library" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"operation":"create_folder","name":"Transformer"}'
```

### DELETE /library

删除一个阅读条目。

```bash
curl -X DELETE "$BASE/library?id=<paper-id>" \
  -H "Authorization: Bearer $TOKEN"
```

### POST /reader

流式翻译、总结、解释、分析或问答。

```bash
curl -N -X POST "$BASE/reader" \
  -H "Authorization: Bearer $TOKEN" \
  -H "makers-conversation-id: $CID" \
  -H "Content-Type: application/json" \
  -d '{"action":"summarize","text":"Attention mechanisms improve contextual representation.","response_language":"zh-CN"}'
```

事件为 `paper_delta`、`paper_done`、`ping`、`error_message`，最后是 `[DONE]`。

## 12. 数据维护

### POST /reset-files

先预览将被清理的会话：

```bash
curl -X POST "$BASE/reset-files" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"confirmation":"DELETE","operation":"inspect"}'
```

再次调用并把 `operation` 改为 `clear` 才会清理文件和会话。个人资料与头像始终保留。

### POST /reset

清理对应会话的应用状态；个人资料不在该接口范围内。

```bash
curl -X POST "$BASE/reset" \
  -H "Authorization: Bearer $TOKEN" \
  -H "makers-conversation-id: $CID" \
  -H "Content-Type: application/json" \
  -d '{"confirmation":"DELETE","conversation_ids":["yb7_example"]}'
```

## 13. 四端最小代码

### Web / TypeScript

```ts
const response = await fetch('/messages', {
  method: 'POST',
  credentials: 'same-origin',
  headers: {
    'Content-Type': 'application/json',
    'makers-conversation-id': conversationId,
  },
  body: JSON.stringify({ conversation_id: conversationId }),
});
const bootstrap = await response.json();
```

### Android / Kotlin

```kotlin
val request = Request.Builder()
  .url("$base/messages")
  .header("Authorization", "Bearer $token")
  .header("makers-conversation-id", conversationId)
  .post("""{"conversation_id":"$conversationId"}"""
    .toRequestBody("application/json".toMediaType()))
  .build()
```

### HarmonyOS / ArkTS

```ts
const request = http.createHttp();
const result = await request.request(`${base}/messages`, {
  method: http.RequestMethod.POST,
  header: {
    Authorization: `Bearer ${token}`,
    'Content-Type': 'application/json',
    'makers-conversation-id': conversationId,
  },
  extraData: JSON.stringify({ conversation_id: conversationId }),
});
```

### iOS / Swift

```swift
var request = URLRequest(url: URL(string: "\(base)/messages")!)
request.httpMethod = "POST"
request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
request.setValue(conversationId, forHTTPHeaderField: "makers-conversation-id")
request.setValue("application/json", forHTTPHeaderField: "Content-Type")
request.httpBody = try JSONEncoder().encode(["conversation_id": conversationId])
```

四端使用同一份 OpenAPI 生成 DTO 和基础请求代码即可。客户端不实现搜索规划、Skill 决策、租户前缀、文件 key、权益判断或操作状态机。

## 14. 可直接交给客户端开发 AI 的提示词

```text
请基于 Floris 现有后端实现原生客户端，开发环境是
https://floris-dev.jlutx.com。

先完整读取：
/contracts/floris-client-v1.openapi.json
/contracts/chat-events-v1.schema.json
/contracts/floris-components-v1.schema.json
/contracts/mobile-client-v1.md

把这些文件作为唯一网络、事件与组件协议。使用 CloudBase 官方 SDK 完成登录
和 token 刷新，再调用 POST /auth/mobile/session 获取短期 Floris Bearer。
所有业务请求携带 Authorization: Bearer 和稳定、不透明的
makers-conversation-id。

客户端只实现原生界面、系统权限、通知、文件选择和本地缓存。不要重写聊天编排、
富搜索、Skills、地图、路线、日程、论文、权益、多租户或副作用状态机。按 SSE
type 流式渲染；未知事件忽略，未知组件保留正文。搜索图片必须使用 source_id
与来源确定性绑定；未经服务端确认的操作不能显示为成功。
```

## 15. 网页端边界审计结论

当前网页端与其他客户端共用同一个业务边界：所有需要展示的服务端状态都来自本 OpenAPI、SSE 事件 Contract 或组件 Contract。网页端没有直接读取 Makers Store、LangGraph Checkpoint、Makers Blob 索引、CloudBase 数据库，也没有直接调用大模型、搜索、地图路线或论文 Provider。

网页端的调用分为以下三类：

| 类型 | 是否属于 Floris 业务 API | 规则 |
| --- | --- | --- |
| `/chat`、`/messages`、`/workspace` 等同源请求 | 是 | 必须在 OpenAPI 中发布，并经统一 Session Transport 调用 |
| 服务端返回的短期上传 URL | 是，上传数据面 | 只允许 `PUT` 到 `/files`、`/profile` 或 `/skill-uploads` 返回的 URL；客户端不能拼接 Blob key 或上传域名 |
| CloudBase、系统定位、地图绘制、PDF 渲染、文件选择、通知、剪贴板 | 否，属于客户端平台 Adapter | 可以使用对应系统官方 SDK，但不能替代 Floris 的鉴权交换、地点核验、路线规划、持久化或权益判断 |

以下自动化门禁持续保证这个结论：

- 每个网页端业务路径都必须存在于 `floris-client-v1.openapi.json`。
- Feature 和 Component 不能直接使用 `fetch`、`XMLHttpRequest`、`WebSocket` 或 `EventSource` 绕过共享 Transport。
- 跨域写入只允许三个服务端签发上传 URL 的客户端：头像、聊天文件和 Skill ZIP。
- 仓库 Skill 由 `/skill-uploads` 的 `resolve_url` 解析，网页端不再直接抓取 GitHub/GitLab。
- 浏览器地图 SDK 只画服务端返回的地点和路线几何；真实地点与路线仍由 `/places`、`/routes` 或 `/chat` 决定。

本结论不表示客户端完全没有本地逻辑。动画、布局、Markdown、PDF 页面渲染、地图缩放层级、草稿、主题、最近会话缓存属于表现层，可以按系统重写；它们不能产生服务端成功状态。

## 16. 状态所有权

| 状态 | 权威所有者 | 客户端可做什么 |
| --- | --- | --- |
| 身份、会员、权益 | `/auth/session` 或移动 Bearer | 缓存只用于启动占位，最终必须服从服务端 |
| 会话列表 | `/conversations` | 本地保存最近列表用于瞬时启动，联网后合并并以服务端为准 |
| 消息、来源、图片、卡片 | `/messages` 与 `/chat` SSE | 未完成流式行只保存在运行内存，不写本地持久缓存；恢复后按服务端消息和 Action ID 合并 |
| 搜索来源与媒体 | `search_results`、`search_media` | 只能按 `source_id` 合并；不能猜测、重排来源绑定 |
| 日程、地图、路线、图片版本 | `/workspace` | 可以做视图排序和动画；不能自行把待确认 Action 标成成功 |
| 个人资料与头像 | `/profile` | 可保存头像的本地二进制缓存，资料更新以服务端响应为准 |
| Skill 状态与依赖 | `/skill_marketplace`、`/intelligence`、`/skill-uploads` | 可以筛选分类；启用、禁用、安装和审核状态由服务端决定 |
| 记忆、偏好、主动提醒 | `/intelligence`、`/proactive` | 可以做本地表单草稿；保存后以返回的 `revision`/投影为准 |
| 论文与阅读库 | `/papers`、`/library`、`/reader` | PDF 显示和文字选区可本地实现；目录、文件和助读结果持久化走服务端 |

客户端本地数据全部应视为缓存。换账号时必须清理上一身份的会话 ID、消息缓存、头像缓存索引和临时操作状态，不能把一个账号的本地缓存合并给另一个账号。

## 17. 客户端启动与登录生命周期

### 17.1 App 启动

1. 从安全存储读取 CloudBase Provider Session；不要读取或复制其 refresh token。
2. 若 Provider 能恢复会话，取得当前 CloudBase access token，调用 `POST /auth/mobile/session`。
3. 将 Floris Bearer 保存到系统 Keychain/Keystore；它只有短期有效期。
4. 调用 `GET /auth/session`，取得当前 `identity`、`entitlements` 和登录配置。
5. 创建或恢复一个客户端自己的不透明会话 ID，调用 `POST /messages`。
6. 并行加载 `/conversations`；按当前产品页面按需加载 `/workspace`、`/intelligence`、`/proactive`、`/library`，不要启动时无条件读取所有页面。
7. 第一屏可先显示本地缓存，但收到服务端投影后必须完成一次确定性合并。

### 17.2 Bearer 过期

- 业务请求返回 `401` 时，最多执行一次 CloudBase Session 恢复和 `/auth/mobile/session` 交换，然后重放安全的读取请求。
- 不要自动重放 `/chat`、`confirm_action`、文件完成、审核提交等可能产生副作用的请求；先通过 `/messages` 或对应读取接口核对状态。
- CloudBase 无法恢复时清除 Floris Bearer，进入游客模式或显示登录入口。

### 17.3 退出

Web 调用 `/auth/logout` 清理 HttpOnly Cookie。原生客户端清除本地 Floris Bearer，并按产品选择退出 CloudBase Provider Session。退出不删除服务端个人资料、会话和文件；数据删除只能走第 12 节的确认流程。

## 18. 聊天 SSE 状态机

每次用户发送消息只建立一次 `POST /chat` 流。它不是需要永久保持的 WebSocket。客户端应在用户点击发送时开始总计时，在 `[DONE]`、明确错误或用户停止时结束，不能因规划、搜索或媒体事件重置计时。

推荐的客户端 Reducer：

```text
send(message, client_message_id)
  -> append optimistic user row
  -> append one streaming assistant row
  -> POST /chat

ai_response           append content to the same assistant row
ai_response_reset     clear only that assistant row's generated text
progress_event        upsert progress step; never replace answer text
search_results        merge source records by source_id
search_media          accept media only when its source_id exists and source_url matches
paper_results         upsert paper cards
clarification_action  attach clarification card to the current assistant row
map/calendar/side_effect_action
                      upsert WorkspaceAction by action.id
experience_hint       attach a small optional capability hint
follow_ups            replace follow-up suggestions for this answer
answer_complete       mark answer text complete; continue accepting late media
error_message         mark stream failed without inventing a successful action
ping/usage            update liveness/diagnostics; do not render as answer
[DONE]                settle the transport and persist the final local cache
```

必须遵守：

- `ai_response.content` 是增量，不是累计全文。
- `search_results`、`search_media` 与正文可以交错到达，也可能多次到达。
- `answer_complete` 不等于连接立即结束；图片审查可能稍晚，但不得改写正文或计时起点。
- `follow_ups` 通常在 `answer_complete` 之后、`[DONE]` 之前到达；客户端不能在正文完成时提前销毁当前消息 Reducer。
- 同一 `action.id` 只渲染一张卡；后到的版本覆盖旧版本。
- 收到未知事件时忽略该事件并继续读流。
- 网络裸 EOF 且没有 `[DONE]` 时自动查询并恢复同一个 Maker run，但不自动新建或重复生成。
- 用户点击停止时先中断本地读取，再调用 `/stop`；页面刷新只断开页面，不应自动取消服务端任务。

服务端把 LangGraph 检查点视为运行态暂存。只有 `run.status=completed` 后，当前回答才会一次性进入 `/messages` 的正式投影和后续模型上下文；`running`、`cancel_requested`、`failed` 或 `cancelled` 的回答片段都不能跨会话切换、刷新或客户端同步边界。客户端可以实时渲染 SSE，但必须在内存中维护临时行，收到停止后直接删除。

## 19. 公开操作表

OpenAPI 描述 HTTP 方法和基础 Schema；以下表描述具有 `operation` 的多态接口。未列出的操作视为服务端内部能力，客户端不能调用。

### 19.1 `/workspace`

所有请求携带 `makers-conversation-id`。返回值始终是最新 `WorkspaceProjection`，可能额外包含 `action`、`changed`、`travel_plan` 等本轮结果。

| operation | 主要输入 | 用途 |
| --- | --- | --- |
| `get` | 无 | 读取日程、活动地图、路线、旅行计划和可继续 Action |
| `save_travel_plan` | `plan` | 保存旅行计划正文与预算、目的地等结构化字段 |
| `delete_travel_plan` | `plan_id` | 删除旅行计划 |
| `activate_map` | `action_id`, `version` | 激活经过服务端核验的地图 Action |
| `deactivate_map` | 无 | 关闭当前活动地图 |
| `direct_calendar_changes` | `changes[]` | 直接提交用户在日历界面编辑的变更 |
| `update_meeting_action` | `action_id`, `version`, 时间与主题 | 编辑仍待确认的会议 Action |
| `confirm_action` | `action_id`, `version` | 确认日程、会议或其他待确认副作用 |
| `cancel_action` | `action_id`, `version` | 取消未结束 Action |
| `generate_image` | `prompt`, `parent_action_id?` | 创建新的图片版本；新客户端优先使用流式 `/image` |

`TravelPlan.markdown_content` 同时承载完整行程和目的地介绍。服务端没有独立百科生产者，因此契约不提供 `baike_info`、`highlights` 或 `best_season`；客户端也不要为这些历史占位字段保留空 UI。

`version` 是乐观并发控制字段。收到 `409` 或版本错误时重新调用 `get`，不能覆盖服务端的新版本。

### 19.2 `/intelligence`

| operation | 主要输入 | 用途 |
| --- | --- | --- |
| `get` / `export` | 无 | 读取公开个性化投影 |
| `confirm_memory` / `reject_memory` | `proposal_id`, `version` | 处理记忆提案 |
| `delete_memory` | `memory_id` | 删除一条记忆 |
| `rollback_memory` | `memory_id`, `target_version` | 回滚记忆版本 |
| `confirm_rule` / `reject_rule` | `rule_id`, `version` | 处理自动规则提案 |
| `update_usage_preferences` | `preferences` | 设置用量提醒与执行方式 |
| `update_memory_preferences` | `preferences.enabled` | 开关长期记忆 |
| `update_search_preferences` | `preferences.{result_limit,image_limit,parallel_image_search}` | 修改并持久化后端富搜索行为；不能只存客户端本地 |
| `update_map_preferences` | `preferences` 中八个 `MapPreferences` 字段 | 修改路线模式、结果数量、超时、策略和学习开关 |
| `update_skill_preferences` | `preferences: {skill_id: boolean}` | 启用或禁用系统 Skill；依赖由服务端原子处理，每项结果见 `skill_preference_results[]` |
| `configure_skill_connection` | `skill_id`, `token` | 保存用户连接的外部 Skill 凭据 |
| `disconnect_skill_connection` | `skill_id` | 断开外部 Skill |
| `install_user_skill` | `skill: SkillDraft` | 安装声明式私有 Skill，不接受可执行 Adapter |
| `set_user_skill_enabled` | `skill_id`, `enabled` | 禁用或重新启用私有 Skill |
| `remove_user_skill` | `skill_id` | 删除私有 Skill |
| `clear_memories` | 无 | 清空记忆；不清理资料、会话或 Skills |

### 19.3 `/proactive`

| operation | 主要输入 | 用途 |
| --- | --- | --- |
| `get` | 无 | 读取提醒、工作流、偏好和检查点 |
| `page_open` / `refresh` / `memory_refresh` | 无 | 页面进入、一般刷新或只刷新记忆提醒 |
| `update_preferences` | `preferences` | 修改主动服务与安静时段等设置 |
| `propose_workflow` | `title`, `reason`, `steps[]` | 创建待确认工作流 |
| `confirm_workflow` / `reject_workflow` | `workflow_id`, `version` | 决定工作流 |
| `cancel_workflow` | `workflow_id`, `version` | 取消工作流 |
| `complete_workflow_step`、`skip_workflow_step`、`fail_workflow_step`、`retry_workflow_step`、`compensate_workflow_step` | `workflow_id`, `step_id` | 推进工作流步骤 |
| `mark_read` / `dismiss` / `snooze` | `notification_id`, `until?` | 处理提醒；提醒响应字段为 `action_prompt`、`snoozed_until` |
| `ingest_signal` | `signal_type`, `dedup_key`, `payload` | 上报客户端真实系统事件，例如获准定位后的城市级天气、文件上传或图片完成 |

`tick` 只用于 Makers Schedule，不是客户端接口。

### 19.4 `/skill_marketplace` 与 `/skill-uploads`

| 接口/operation | 用途 |
| --- | --- |
| `/skill_marketplace` `catalog`/默认 | 获取分类、说明、依赖、冲突、当前状态和组件 API |
| `/skill_marketplace` `package` | 下载已安装系统 Skill 的可移植声明包 |
| `/skill-uploads` `resolve_url` | 由服务端安全读取 GitHub/GitLab `SKILL.md` 并返回 `SkillDraft` |
| `/skill-uploads` `create` | 创建私有 ZIP 的短期上传意图 |
| `/skill-uploads` `complete` | 上传完成后登记 Blob 元数据 |
| `/skill-uploads` `publish` | 将私有 ZIP 显式提交广场审核 |
| `/skill-uploads` `publish_declarative` | 将已安装声明式 Skill 显式提交广场审核 |

安装、启用与审核是三个独立状态。`resolve_url` 只解析，`install_user_skill` 才安装，`publish*` 才进入审核。

### 19.5 `/library`

| operation | 主要输入 | 用途 |
| --- | --- | --- |
| `register`/默认 | 文件信息、`storage_key` | 把已上传 PDF 登记到“我的阅读” |
| `settings` | `auto_organize` | 修改自动整理 |
| `create_folder` | `name` | 创建文件夹 |
| `rename_folder` | `folder_id`, `name` | 重命名文件夹 |
| `move_item` | `item_id`, `folder_id` | 移动阅读项目 |
| `touch` | `id` | 更新最近打开时间 |
| `save_assistant_result` | `storage_key`, `action`, `content` | 保存任一种受支持的助读结果 |

删除条目或文件夹使用 `DELETE /library?id=...` 或 `DELETE /library?folder_id=...`。

`/papers`、`/library`、`/reader` 和 `/document-text` 属于论文助读能力。游客只有核心能力与主动服务，因此这些接口返回 403 是预期权限边界；客户端应显示登录/开启能力入口，而不是把它解释为网络故障。已经登录且有 free 权益的账号可以读取资料；关闭论文助读后，既有 Makers Blob 文件不会被删除。

`POST /papers` 成功响应同时返回 `file_id` 与 `storage_key`，两者当前是同一个不透明服务端 key；新客户端以 `storage_key` 为持久化字段，并保留 `file_id` 兼容。新论文在写入时就通过共享的阅读库领域服务分配 `folder_id`；`/library` 的读取时整理只保留给历史数据迁移。

### 19.6 `/reader` 与服务端 PDF 提取

段落级操作仍可直接传 `text`。全文分析、问答以及原生客户端上传后的助读可以只传 `file_id`：

```bash
curl -N -X POST "$BASE/reader" \
  -H "Authorization: Bearer $TOKEN" \
  -H "makers-conversation-id: $CID" \
  -H "Content-Type: application/json" \
  -d '{"action":"qa","file_id":"<server-issued-key>","question":"论文的主要局限是什么？","response_language":"zh-CN"}'
```

后端会通过 Makers Blob 读取当前租户的 PDF，再由服务端 PDF.js Adapter 提取最多 120,000 字；客户端无需集成 PDF 文本提取库。流首先可能给出 `paper_source`（`preview/page_count/truncated`），随后是 `paper_delta`、`paper_done` 与 `[DONE]`。扫描件没有可选择文本时返回 422，不会让模型猜测正文。`POST /document-text` 暴露同一底层 Adapter，主要用于诊断或只需要文本预览的客户端。

`save_assistant_result.action` 与 `/reader` 一致，支持 `translate`、`summarize`、`explain`、`formula`、`analyze`、`full-translate`、`terms`、`qa`，不再要求客户端维护较窄白名单。

批量更新系统 Skill 时，HTTP 200 表示请求已完成，不代表每项都被接受。客户端读取每个 `skill_preference_results[]` 的 `applied/code/effective_enabled`；一个 `LOGIN_REQUIRED`、`MEMBERSHIP_REQUIRED`、`SKILL_LOCKED` 或 `DEPENDENCY_REQUIRED` 不会回滚其他合法修改，也不需要逐项重试。

## 20. 文件、地图和系统 Adapter

### 20.1 文件上传

标准流程统一为：

1. 向 Floris 请求上传意图。
2. 只向返回的短期 URL 执行一次 `PUT`。
3. 对需要登记的资源调用完成或注册接口。
4. 后续读取只使用服务端返回的 `content_url` 或 `/files?key=...`，不保存可推导的租户前缀。

原生客户端可用系统上传 API，但不得给预签名请求附加 Floris Bearer、CloudBase token 或 Cookie。

### 20.2 PDF

网页端使用 PDF.js 在本地完成页面绘制、文字提取、段落选区和高亮；Android、HarmonyOS、iOS 应使用各自成熟的 PDF 组件实现同一个 `LocalDocumentAdapter`。把选中或提取的文本发送给 `/reader`，把需要持久化的文件与结果交给 `/files` 和 `/library`。PDF 解析结果不是账号权威数据，无需复制到另一套后端。

### 20.3 地图与定位

系统定位必须由用户授权，建议只保存在内存并设置短有效期。客户端可以把新鲜坐标作为 `/chat` 的 `current_location` 或路线起点；服务端负责地点歧义、真实路线、费用与交通方式。地图 SDK 只负责底图、Marker、Polyline、缩放和视口动画。

路线展示应读取 `route.legs[].sections[]`：城市概览、推荐地点之间的路段和每段交通方式均来自服务端。客户端可以随缩放级别切换总览、路段和细分 Section，但不能重新计算一条与服务端不同的路线后冒充 Floris 结果。

## 21. 错误、重试与幂等

| 状态 | 客户端处理 |
| --- | --- |
| `400` | 请求字段错误；保留用户输入并显示可理解提示 |
| `401` | 尝试一次 Provider Session 恢复和 Bearer 交换 |
| `403 LOGIN_REQUIRED` | 打开登录入口；不要把它显示成 Skill 安装错误 |
| `403 SKILL_DISABLED` / 权益错误 | 保留基础回答或当前页面，提示可选能力状态 |
| `404` | 刷新对应列表；不要继续使用本地旧对象 |
| `409` | 重新读取 Workspace/文件状态，不盲目重放副作用 |
| `413` | 在客户端压缩或选择更小文件；服务端限制不能绕过 |
| `429` | 尊重 `Retry-After`，采用指数退避 |
| `5xx` / 网络异常 | 读取请求可退避重试；生成和写入请求先核对服务端状态 |

客户端为每次用户发送生成稳定 `client_message_id`。同一 UI 动作在网络不确定时不要换 ID 自动重发。Action 使用服务端 `action.id + version`；信号使用稳定 `dedup_key`；上传使用一次性 `upload_id/storage_key`。这些标识都不包含用户 ID、租户 ID或密钥。

## 22. 跨端功能对齐验收清单

一个新客户端只有通过以下项目，才可以声称与网页端功能对齐：

- [ ] 游客可以聊天；不可用 Skill 自动降级且正文不被技术提示替代。
- [ ] CloudBase 登录可以恢复，Bearer 过期只刷新一次，退出后不会串账号缓存。
- [ ] 会话列表、消息、搜索来源、图片和卡片刷新后可以从服务端恢复。
- [ ] SSE 正文、来源、媒体和组件可交错流式渲染，计时不会重置。
- [ ] 图片必须同时满足 `vision_reviewed=true` 且 `source_id/source_url` 一致，只插入回答实际引用的对应来源段落；没有审核通过的图片就不显示。
- [ ] 搜索与地图偏好修改后重新读取服务端投影，并能实际改变下一轮后端请求。
- [ ] 主动提醒从真实 JSON 的 `action_prompt`、`snoozed_until` 反序列化，“帮我处理”和推迟时间无需手工 JSON 映射即可工作。
- [ ] 清空数据只接受大写 `DELETE`；个人资料和头像不在清空范围内。
- [ ] 澄清卡、地图卡、日程卡、会议卡和图片卡按 `action.id/version/status` 更新。
- [ ] 日程编辑、确认、取消和冲突处理全部走 `/workspace`。
- [ ] 地图使用 `/places` 与 `/routes`，能展示跨城、城市内和多交通方式 Section。
- [ ] 论文搜索、保存、分片下载、阅读、助读和结果保存全部可用。
- [ ] Skills 能分类展示、启禁用、配置依赖、导入文本/文件/仓库、保存私有状态和显式提交审核。
- [ ] 头像上传、头像本地缓存和个人资料更新不会泄露预签名 URL 或跨账号显示。
- [ ] 主动提醒、记忆、搜索/地图偏好和使用量可以读取与修改。
- [ ] 清理应用数据时保留个人资料和头像，并在执行前显示明确范围。
- [ ] 未知 SSE 事件和新增可选字段不会导致崩溃；未知组件保留正文降级。

推荐把这份清单做成每个平台的自动化 Contract Test，并让测试读取同一份 OpenAPI 与 JSON Schema，而不是复制一份平台私有 DTO 规范。
