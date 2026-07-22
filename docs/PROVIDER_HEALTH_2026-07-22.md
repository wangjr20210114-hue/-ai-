# Provider 与环境变量存活性快照（2026-07-22）

> 这是一次脱敏的 Preview 实测快照，不是永久 SLA。仓库、日志和验收站均不得保存 Token、Cookie、签名 URL 或完整 Provider 响应。

## 结论

| 能力 | 环境变量/入口 | 真实结果 | 当前处理 |
| --- | --- | --- | --- |
| 主对话模型 | `AI_GATEWAY_API_KEY` + `AI_GATEWAY_BASE_URL` | HTTP 429，约 1.8 秒；当前网关额度不可用 | 保留 Makers 原生入口；运行时使用 DeepSeek 直连降级，健康页分别展示主、备状态 |
| 模型降级 | `DEEPSEEK_API_KEY` | HTTP 200，约 1.2 秒 | 可用 |
| 联网搜索 | `WSA_API_KEY` | HTTP 200，约 1.6 秒；返回有效搜索响应 | 可用；单轮只调用一次 SearchPro，并保留持久缓存 |
| 混元视觉 | `HUNYUAN_IMAGE_API_KEY` | 320px 真实公网图片约 23.4 秒后 HTTP 400，Provider code `400001` | 当前不适合作为 7 秒富搜索同步审核；搜索仍可使用可追溯网页原图，视觉审核失败不阻断正文 |
| 混元生图 | `HUNYUAN_IMAGE_API_KEY` | HTTP 200，约 14.5 秒并返回真实图片 | 可用，继续作为默认生图 Provider |
| Cloudflare Token | `CLOUDFLARE_WORKERS_AI_TOKEN` | Token 校验 HTTP 200、状态 active | Token 有效，仅限 Preview；生产前轮换已暴露的测试 Token |
| Cloudflare 多模态理解 | Account ID + Token | HTTP 403，错误码 5016 | Token 有效，但当前 Meta 视觉模型要求账号接受模型许可；未经用户明确同意不代为接受，保持外部阻塞 |
| Cloudflare LLaVA 视觉备选 | Account ID + Token | 官方字节数组格式、320px 小图仍 HTTP 400，错误码 3010 | 已排除原图过大；Beta 模型当前账号调用仍失败，不切换默认模型 |
| Cloudflare 文生图 | Account ID + Token | HTTP 200，约 2.0 秒，返回真实图片数据 | 可用作免费降级 |
| 腾讯地点服务端 | `TENCENT_MAP_SERVER_KEY` | HTTP 200、Provider status=0、返回 3 个地点 | 可用 |
| 腾讯地图浏览器 Key | `VITE_TENCENT_MAP_KEY` | HTTP 200、Provider status=0 | 可用 |
| 腾讯会议个人 Skill | `TENCENT_MEETING_TOKEN` | MCP `tools/list` HTTP 200，21 个工具且包含 `schedule_meeting` | 可用；业务只保留个人官方 MCP 路径 |

Cloudflare 5016 的含义与许可要求见官方 [Workers AI 错误文档](https://developers.cloudflare.com/workers-ai/platform/errors/) 和 [Llama 3.2 Vision 模型页](https://developers.cloudflare.com/workers-ai/models/llama-3.2-11b-vision-instruct/)。LLaVA 的字节数组契约见官方 [LLaVA 模型页](https://developers.cloudflare.com/workers-ai/models/llava-1.5-7b-hf/)。接受第三方模型条款是账号级外部操作，不属于普通代码测试。

## 已配置但当前代码未使用的变量

控制台仍存在下列历史变量，但当前 Makers 运行时没有读取它们：

- `CODEX_ENV_PROBE`
- `PLACE_API_TOKEN`
- `DATABASE_URL`
- `DATABASE_SSL`
- `EDGEONE_BLOB_STORE`
- `LEGACY_BACKEND_URL`
- `HUNYUAN_API_KEY`（当前统一使用 `HUNYUAN_IMAGE_API_KEY`/`HUNYUAN_VISION_API_KEY`）

它们不影响运行；为避免误删外部配置，本次只从代码和文档中移除引用，没有自动删除 Makers 控制台变量。确认没有其他 Deployment 使用后可由项目所有者手工删除。

## 可复现的安全探测

仓库提供 `tools/probe-providers.mjs`。它只输出 Provider、HTTP 状态、耗时、非敏感响应形状和错误码，不输出密钥或响应正文。密钥文件必须放在仓库外、权限设为 `0600`；脚本读取后会在发起网络请求前立即删除该文件。

```bash
node tools/probe-providers.mjs --env-json /private/tmp/yuanbao-provider-env.json
node tools/probe-providers.mjs --env-json /private/tmp/yuanbao-provider-env.json --only cloudflare_image
node tools/probe-providers.mjs --env-json /private/tmp/yuanbao-provider-env.json --only cloudflare_vision_llava
```

不要把 `.env`、临时 JSON、探测响应、Preview 签名或 Token 加入 Git。
