# Floris 跨端客户端 API v1

这份文档是 Web、Android、HarmonyOS 和 iOS 的统一接入说明。客户端只负责界面、系统权限、通知、文件选择和本地缓存；聊天编排、搜索、Skills、地图、日程、论文、权益、身份隔离和持久化均由 Floris 后端提供。

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
| 文件 | `POST/GET/HEAD/DELETE /files` |
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

`ai_response.content` 是增量文本。图片审核不阻塞正文首字，`search_media` 可以与多条 `ai_response` 交错到达；`search_results` 和 `search_media` 也可能多次到达或先后互换。客户端必须按 `source_id` 合并，不能先放一个最终占位卡再删除，也不能因为媒体稍后到达而重置正文或计时。

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

取消当前生成。

```bash
curl -X POST "$BASE/stop" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"conversation_id\":\"$CID\"}"
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

### HEAD /files

读取文件大小与分片大小。

```bash
curl -I "$BASE/files?key=<server-issued-key>" \
  -H "Authorization: Bearer $TOKEN"
```

### GET /files

读取完整文件；大文件按 `part=0`、`part=1` 顺序获取并合并。

```bash
curl "$BASE/files?key=<server-issued-key>&part=0" \
  -H "Authorization: Bearer $TOKEN" \
  --output part-0.bin
```

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

### POST /proactive

读取提醒、工作流与主动服务设置。

```bash
curl -X POST "$BASE/proactive" \
  -H "Authorization: Bearer $TOKEN" \
  -H "makers-conversation-id: $CID" \
  -H "Content-Type: application/json" \
  -d '{"operation":"get"}'
```

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

`route.legs` 表示推荐地点之间的路段；每个 `leg.sections` 可包含步行、公交、轨道、骑行或驾车等多种交通方式。客户端应为不同 `section.mode` 使用一致且可辨认的颜色，并根据地图缩放级别自然调整路线细节。

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
