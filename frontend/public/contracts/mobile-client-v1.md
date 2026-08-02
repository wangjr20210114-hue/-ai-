# Floris 跨端客户端 Contract v1

Android、鸿蒙、iOS 与 Web 共享同一套 Floris Maker 后端。客户端只实现界面、系统权限、通知、文件选择和本地缓存；聊天编排、搜索、Skills、地图、日程、论文、权益和多租户持久化不得复制到客户端。

## 鉴权

Web 继续使用 `HttpOnly + Secure + SameSite=Lax` 的 `floris_session` Cookie。登录账号的 Cookie 有效期为 30 天，并在剩余 7 天内滚动续期；会话不绑定 IP，网络切换不会要求重新登录。

原生 App 直接使用 CloudBase HTTP API 完成邮箱、GitHub 或后续启用的身份源登录，并安全保存 CloudBase refresh token。拿到当前 CloudBase access token 后调用：

```http
POST /auth/mobile/session
Content-Type: application/json

{"access_token":"<cloudbase access token>"}
```

返回的 Floris Bearer token 有效期为 1 小时。客户端在过期前先通过 CloudBase 刷新，再重新交换；Floris 不签发第二份 refresh token。业务请求统一携带：

```http
Authorization: Bearer <floris access token>
makers-conversation-id: <opaque client id>
```

Bearer 是原生客户端的唯一 Floris 会话凭据；即使 WebView 中残留 Cookie，服务端也优先使用显式 Bearer。Bearer 失效时 `/auth/session` 返回 `401`，客户端通过 CloudBase 刷新并重新交换，不会被静默降级成游客。私有头像 URL 也必须带同一 Bearer 下载。

## 聊天与组件

`POST /chat` 返回 SSE。事件 schema 位于 `/contracts/chat-events-v1.schema.json`。客户端按 `type` 渲染已知事件；未知事件必须忽略，未知组件降级为文本，不能让会话崩溃。

地图、日程、会议与图片均由 `WorkspaceAction` 组件表达。客户端只展示后端返回的可信 payload，并通过 `/workspace` 执行确认或状态变更，不得自行伪造成功状态。

组件 schema 位于 `/contracts/floris-components-v1.schema.json`，覆盖进度、搜索来源与媒体、论文、主动澄清卡、Workspace Action 和低干扰体验提示。Android、鸿蒙和 iOS 只需要为这些 schema 实现原生 View；业务判断仍由 Maker 后端完成。

原生客户端的最小请求链路：

1. 让 CloudBase SDK/HTTP API 登录并刷新 CloudBase token。
2. 调用 `/auth/mobile/session` 换取 Floris Bearer。
3. 为会话生成稳定且不透明的 `makers-conversation-id`。
4. 调用 `/chat` 并按空行切分 SSE frame，再按 `type` 分发组件。
5. 收到未知事件时忽略；收到未知 Action kind 时保留文本答案并提示客户端升级。
6. 任何确认、取消、重试都调用 `/workspace`，不在本地复制副作用状态机。

## 兼容策略

- v1 允许新增可选字段和事件。
- 删除字段、改变含义或改变副作用语义必须发布新的 major contract。
- `makers-conversation-id` 是客户端不透明 ID；服务端负责结合登录身份生成 Maker 租户作用域。
- 完整 OpenAPI 位于 `/contracts/floris-client-v1.openapi.json`。

## 可直接交给客户端开发 AI

```text
请基于 Floris 现有后端实现原生客户端。开发环境为 https://floris-dev.jlutx.com。
先读取 /contracts/floris-client-v1.openapi.json、/contracts/chat-events-v1.schema.json
和 /contracts/floris-components-v1.schema.json，并以它们作为唯一网络与组件协议。

使用 CloudBase SDK/HTTP API 完成登录和 token 刷新，再调用
POST /auth/mobile/session 换取短期 Floris Bearer。所有 Floris 请求携带
Authorization: Bearer 和稳定、不透明的 makers-conversation-id。

客户端只实现原生界面、系统权限、通知、文件选择和本地缓存。不要在客户端重写
聊天编排、搜索、Skills、地图、路线、日程、论文、权益、多租户或副作用状态机；
这些全部调用现有 Floris Maker 后端。严格按 SSE type 分发组件，未知事件忽略，
未知组件降级显示文本。不得把未经后端确认的操作显示为成功。
```
