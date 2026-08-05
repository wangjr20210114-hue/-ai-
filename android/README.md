# Floris Android

Floris 原生 Android 客户端。Kotlin + Jetpack Compose + Material 3 + Coroutines + Retrofit/OkHttp。

客户端只实现界面、系统权限、通知、文件选择与本地缓存；聊天编排、搜索、Skills、地图、路线、日程、论文、权益与多租户持久化全部复用 Floris Maker 后端（见 `../contracts/` 与 `/contracts/*.json`）。

跨端接入、全部 API、SSE、刷新恢复、严格图片绑定与安全边界见 [`../docs/mobile-client-v1.md`](../docs/mobile-client-v1.md)；机器可读契约见 [`../contracts/mobile-client.v1.json`](../contracts/mobile-client.v1.json)。

## 构建

```bash
cd android
echo 'sdk.dir=<你的 Android SDK 路径>' > local.properties
./gradlew :app:assembleDebug
```

可选配置（写入 `local.properties`）：

| 键 | 用途 |
|---|---|
| `cloudbasePublishableKey` | CloudBase Auth Publishable Key（邮箱登录必需，见仓库根 `.env.edgeone` 的 `VITE_CLOUDBASE_PUBLISHABLE_KEY`） |
| `tencentMapKey` | 腾讯地图 GL JS Key（开启地图页 WebView 渲染，可选） |

## 测试

```bash
./gradlew :app:testDebugUnitTest
```

覆盖：SSE 帧切分与事件分发、未知事件忽略、搜索/图片乱序合并、严格来源图片绑定、
五种响应语言注入，以及 CloudBase 登录/刷新/交换 Floris Bearer 全链路。

## 架构

```
core/
  auth/        CloudBaseAuthApi（GoTrue 兼容 OTP/refresh）、AuthManager、TokenStore(DataStore)
  network/     FlorisApi(Retrofit)、FlorisClient(OkHttp SSE)、sse/(SseParser、ChatEventDispatcher)
  data/        FlorisRepository（纯转发，零业务逻辑）
  chat/        SSE → UI reducer、活动请求/等待队列持久化、严格来源图片绑定
ui/
  chat/ skills/ calendar/ maps/ papers/ profile/ settings/ history/ auth/
  components/  MarkdownText、ProgressBar、SearchSourcesRow、MediaGrid、PaperListCard、
               WorkspaceActionCard、ClarificationForm、FollowUpChips
```

## 契约纪律

- 所有业务请求携带 `Authorization: Bearer <floris token>` 与稳定的 `makers-conversation-id`。
- 所有 JSON 指令由网络 Adapter 统一补充当前 `response_language`。
- Floris Bearer 1 小时有效；401 时由 OkHttp Authenticator 自动刷新 CloudBase 并重新交换（仅重试一次）。
- `POST /chat` 按空行切分 SSE 帧，按 `type` 分发；未知事件忽略，未知组件降级为文本。
- 刷新或切回对话通过 `/messages` + `/run` 恢复同一个 Maker run，不重新请求普通模型。
- 富搜索来源与媒体按 ID 增量合并；图片只按审核后的确定性 `source_id` 绑定显示，没有兜底图。
- 日程/地图/会议操作仅渲染后端返回的 `status`，确认/取消/重试全部走 `POST /workspace`（带 `version` 乐观锁）。
- 未在客户端重写搜索规划、聊天编排、Skills 决策、路线规划、权益或多租户逻辑。
