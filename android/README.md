# Floris Android

Floris 原生 Android 客户端。Kotlin + Jetpack Compose + Material 3 + Coroutines + Retrofit/OkHttp。

客户端只实现界面、系统权限、通知、文件选择与本地缓存；聊天编排、搜索、Skills、地图、路线、日程、论文、权益与多租户持久化全部复用 Floris Maker 后端（见 `../contracts/` 与 `/contracts/*.json`）。

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

覆盖：SSE 帧切分（`SseParserTest`）、SSE 事件分发与未知事件忽略（`ChatEventDispatcherTest`）、
CloudBase 登录/刷新/换 Floris Bearer 全链路（`AuthManagerTest`，MockWebServer）。

## 架构

```
core/
  auth/        CloudBaseAuthApi（GoTrue 兼容 OTP/refresh）、AuthManager、TokenStore(DataStore)
  network/     FlorisApi(Retrofit)、FlorisClient(OkHttp SSE)、sse/(SseParser、ChatEventDispatcher)
  data/        FlorisRepository（纯转发，零业务逻辑）
  chat/        SSE → UI 消息的纯函数 reducer
ui/
  chat/ search/ skills/ calendar/ maps/ papers/ profile/ settings/ history/ auth/
  components/  MarkdownText、ProgressBar、SearchSourcesRow、MediaGrid、PaperListCard、
               WorkspaceActionCard、ClarificationForm、FollowUpChips
```

## 契约纪律

- 所有业务请求携带 `Authorization: Bearer <floris token>` 与稳定的 `makers-conversation-id`。
- Floris Bearer 1 小时有效；401 时由 OkHttp Authenticator 自动刷新 CloudBase 并重新交换（仅重试一次）。
- `POST /chat` 按空行切分 SSE 帧，按 `type` 分发；未知事件忽略，未知组件降级为文本。
- 日程/地图/会议操作仅渲染后端返回的 `status`，确认/取消/重试全部走 `POST /workspace`（带 `version` 乐观锁）。
- 未在客户端重写搜索规划、聊天编排、Skills 决策、路线规划、权益或多租户逻辑。
