# 动效与视觉模型降级

## 前端动效基线

本项目采用短、明确、可打断的微交互，不使用长时间装饰动画：

| 场景 | 时长 | 效果 |
| --- | ---: | --- |
| 按钮按下 | 70–120ms | 轻微缩放到 `0.97`，松开立即恢复 |
| 按钮悬停 | 180ms | 上移 `1px`，极轻的亮度变化 |
| 消息进入 | 280ms | 透明度、`7px` 位移与 `0.985` 缩放共同过渡 |
| 卡片/图片出现 | 240–320ms | 小幅淡入；图片附带短暂轻模糊消退 |
| 输入框聚焦 | 180–240ms | 边框与低强度聚焦环过渡 |

动效遵循 Apple 的 [Motion](https://developer.apple.com/design/human-interface-guidelines/motion) 和
[Accessibility](https://developer.apple.com/design/human-interface-guidelines/accessibility) 指导：反馈要短且有目的；当系统开启
“减弱动态效果”时，页面通过 `prefers-reduced-motion` 关闭位移、模糊、平滑滚动和非必要动画。

## 混元主链路

- `hy-image-v3.0`：使用 TokenHub 官方异步接口 `/v1/api/image/submit`，随后轮询 `/v1/api/image/query`。
- `hy-image-lite`：使用 `/v1/api/image/lite`；V3 失败时可作为同供应商快速降级。
- `hy-vision-2.0-instruct`：每次请求只传一张图片；新闻图片候选最多审核 4 张，并发执行，不增加 SearchPro 搜索次数。
- 一个可访问所有模型的 TokenHub Key 可同时配置为 `HUNYUAN_IMAGE_API_KEY`；未单独设置
  `HUNYUAN_VISION_API_KEY` 时，程序会复用它。

## Cloudflare Workers AI 降级

生产使用前先轮换任何曾在聊天或截图中暴露的 Token。然后在 Cloudflare 创建仅允许 Workers AI 调用的 API Token，
并在 Makers 的 **Preview 环境变量**中配置：

```text
CLOUDFLARE_ACCOUNT_ID=<Cloudflare Account ID>
CLOUDFLARE_WORKERS_AI_TOKEN=<新的最小权限 Token>
CLOUDFLARE_VISION_MODEL=@cf/meta/llama-3.2-11b-vision-instruct
CLOUDFLARE_IMAGE_MODEL=@cf/black-forest-labs/flux-1-schnell
```

默认顺序不需要额外配置：混元优先、Cloudflare 降级。仅在 Preview 专门验证降级时临时增加：

```text
VISION_PROVIDER_ORDER=cloudflare,hunyuan
IMAGE_PROVIDER_ORDER=cloudflare,hunyuan
```

验证后删除这两项，恢复混元优先。若 Cloudflare 视觉模型返回许可类错误，先在 Workers AI 控制台打开模型页并接受
Meta 模型许可；生图 Flux 与视觉模型是两条独立链路，一个可用不代表另一个也已授权。

## 安全验证

可使用仓库中的一次性探针。探针读取 JSON 后会在发起网络请求前删除文件，输出只包含状态码、耗时和响应结构，
不会输出密钥或图片地址：

```bash
node tools/probe-providers.mjs --env-json /private/tmp/provider-env.json \
  --only hunyuan_image,hunyuan_image_lite,hunyuan_vision,cloudflare_token,cloudflare_image,cloudflare_vision
```

混元两项生图探针各消耗一张额度；不要把真实密钥写入仓库或测试证据。
