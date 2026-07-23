# 视觉 Provider 降级链

更新时间：2026-07-22。

## 结论

当前实现保留混元为第一优先级，并只在主 Provider 未配置或调用失败时进入外部降级。长期免费方案首选 Cloudflare Workers AI：官方 Free allocation 是每天 10,000 Neurons，00:00 UTC 重置；同一套 REST API 可使用 Llama 3.2 Vision、FLUX 文生图和 img2img 模型。

Provider 顺序：

1. 混元视觉/混元生图。
2. Cloudflare Workers AI：视觉理解、文生图、图生图。
3. 阿里百炼 Qwen-VL：仅视觉理解后备。
4. Gemini API Free Tier：仅视觉理解后备。

图像生成链当前只包含混元与 Cloudflare。百炼虽然给新用户 Qwen-VL 100 万 Token、Qwen Image/编辑各 100 张等额度，但有效期通常是开通后 90 天，不属于每日永久重置；Gemini 免费层可用于部分视觉模型，而官方图像生成定价页当前把图像生成列为 Paid Tier。

官方依据：

- [Cloudflare Workers AI 定价](https://developers.cloudflare.com/workers-ai/platform/pricing/)
- [Cloudflare Llama 3.2 Vision](https://developers.cloudflare.com/workers-ai/models/llama-3.2-11b-vision-instruct/)
- [Cloudflare FLUX.1 Schnell](https://developers.cloudflare.com/workers-ai/models/flux-1-schnell/)
- [Cloudflare Stable Diffusion img2img](https://developers.cloudflare.com/workers-ai/models/stable-diffusion-v1-5-img2img/)
- [Gemini API Billing](https://ai.google.dev/gemini-api/docs/billing/)
- [Gemini API Pricing](https://ai.google.dev/gemini-api/docs/pricing/)
- [阿里百炼新人免费额度](https://help.aliyun.com/zh/model-studio/new-free-quota)
- [阿里百炼模型价格与免费额度](https://help.aliyun.com/zh/model-studio/model-pricing)

## 配置 Cloudflare Workers AI

1. 登录 Cloudflare Dashboard，打开 Workers AI。
2. 点击 `Use REST API`，创建 Workers AI API Token；自定义 Token 时至少授予 Workers AI Read/Edit。
3. 复制 Account ID 和只显示一次的 Token。
4. 在 EdgeOne Makers 项目 Preview 环境添加：

```text
CLOUDFLARE_ACCOUNT_ID=<Account ID>
CLOUDFLARE_WORKERS_AI_TOKEN=<API Token>
```

正常环境不需要配置 Provider 顺序，默认始终是混元优先、Cloudflare 失败降级。只为专用 Preview 做真实降级取证时，可以临时增加：

```text
VISION_PROVIDER_ORDER=cloudflare,hunyuan
IMAGE_PROVIDER_ORDER=cloudflare,hunyuan
```

这两个变量只改变已配置托管 Provider 的调用顺序，不开启本地推理、不绕过安全过滤，也不应配置到 Production。取证完成后删除它们即可恢复默认顺序。

模型变量已有安全默认值，通常不需要填写。第一次使用 Llama 3.2 11B Vision 前，需要按 Cloudflare 官方模型页接受 Meta License；未完成时该 Provider 会失败并继续尝试后续视觉 Provider。

不要把 Token 写进仓库、验收备注、截图或浏览器前端变量。这里只从 Makers Agent 服务端读取。

## 运行行为

- 新闻图片审核：每张候选图只发起一个单图请求，最多并发审核 4 张，并记录 `vision_diagnostics.provider_*`，不会把密钥或原始错误返回前端。HY-Vision 官方限制一次只能传一张图；Cloudflare 适配器使用官方 `/ai/run/@cf/meta/llama-3.2-11b-vision-instruct` REST 契约，将文本放入 `messages`、首张待审图片放入顶层 `image`。
- 新闻图片审核：候选图最多 4 张并发审核，整个视觉 Provider 链共享最多 7 秒的硬预算；环境变量只能把它调低，不能放大。提示词只要求判断相关性并排除广告、促销、二维码、Logo、UI、占位图和无关图，不进行深度画面推理。视觉 Provider 缺失、失败或超时的图片不会作为最终媒体发布；此时宁可返回纯文字，也不把未经核实的文章主图插入回答。
- 用户附图理解：发送前端压缩后的图片后，服务端先做一次多模态描述，再把事实描述交给 LLM 规划和回答；原始 Base64 不进入文本提示。
- 文生图：混元失败后，Cloudflare 使用 `FLUX.1 Schnell`。
- 图生图：混元失败后，Cloudflare 使用 img2img；当前降级适配器使用第一张参考图，混元仍支持最多三张参考图。
- 所有成功生成图片都复制到 Makers Blob；Provider 临时 URL 不是历史记录的唯一来源。

当前 Makers 项目的测试 `CLOUDFLARE_WORKERS_AI_TOKEN` 与 `CLOUDFLARE_ACCOUNT_ID` 只配置在 Preview，生产环境不继承。2026-07-22 重新脱敏探测后，Token 本身仍为 active，Flux 文生图 HTTP 200（约 2 秒），历史 Preview 的 img2img 日志也真实显示 `provider=cloudflare`、`model=@cf/runwayml/stable-diffusion-v1-5-img2img`、`reference_count=1`、`fallback=False`；这两条生成降级仍可用。

2026-07-22 按当前官方接口重新实测：`hy-image-v3.0` 的 `submit → query` 链路 HTTP 200，约 14 秒完成；`hy-image-lite` HTTP 200，约 2.6 秒；用 Lite 生成的腾讯托管图片立即调用 `hy-vision-2.0-instruct`，HTTP 200，端到端约 6.8 秒。因此混元视觉模型和密钥均已确认可用。单独使用境外公共测试图曾返回 `400001` 或超时，说明远程图片的可访问性仍会影响审核；代码在视觉 Provider 失败时保留 SearchPro 已返回且可追溯的 HTTPS 文章主图，避免新闻回答无图。

Cloudflare 侧，Meta Llama 3.2 Vision 返回 HTTP 403 / 5016 时需要账号接受模型许可；这不影响 Flux 生图降级。中文翻译预处理仍是可选步骤，失败后图片生成会继续使用原提示词；Cloudflare 只作为免费可用性降级，不宣称与混元质量等价。

## 无破坏 Preview 验收

不要改 Production 密钥，也不要覆盖混元密钥。创建专用 Preview，只在 Preview 添加 Cloudflare 两项凭据和两个顺序变量：

1. 先不设置顺序变量，验证正常输出仍优先使用 `hunyuan`。
2. 临时把 `VISION_PROVIDER_ORDER` 和 `IMAGE_PROVIDER_ORDER` 设为 `cloudflare,hunyuan`。
3. 执行文生图、基于上一版本修改和上传图片问答。
4. 验证三项仍成功、生成图进入 Makers Blob、应用无密钥泄露；日志应显示 Cloudflare Provider 被采用。
5. 删除两个顺序变量并重新部署 Preview，确认恢复混元优先。不得把顺序变量带到 Production。
