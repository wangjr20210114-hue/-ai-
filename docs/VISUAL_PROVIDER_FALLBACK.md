# 视觉 Provider 降级链

更新时间：2026-07-20。

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

模型变量已有安全默认值，通常不需要填写。第一次使用 Llama 3.2 11B Vision 前，需要按 Cloudflare 官方模型页接受 Meta License；未完成时该 Provider 会失败并继续尝试后续视觉 Provider。

不要把 Token 写进仓库、验收备注、截图或浏览器前端变量。这里只从 Makers Agent 服务端读取。

## 运行行为

- 新闻图片审核：在一个共享 7 秒视觉预算内按顺序尝试已配置 Provider，并记录 `vision_diagnostics.provider_*`，不会把密钥或原始错误返回前端。
- 用户附图理解：发送前端压缩后的图片后，服务端先做一次多模态描述，再把事实描述交给 LLM 规划和回答；原始 Base64 不进入文本提示。
- 文生图：混元失败后，Cloudflare 使用 `FLUX.1 Schnell`。
- 图生图：混元失败后，Cloudflare 使用 img2img；当前降级适配器使用第一张参考图，混元仍支持最多三张参考图。
- 所有成功生成图片都复制到 Makers Blob；Provider 临时 URL 不是历史记录的唯一来源。

## 无破坏 Preview 验收

不要改 Production 密钥。创建专用 Preview，只在该 Preview 配置 Cloudflare 两项变量：

1. 正常保留混元：验证输出结果的 `provider` 为 `hunyuan`。
2. 在另一个专用故障 Preview 把 `HUNYUAN_IMAGE_API_KEY` 设为字面值 `invalid-for-acceptance`，不要复制真实值。
3. 执行文生图、基于上一版本修改和上传图片问答。
4. 验证三项仍成功、生成图进入 Makers Blob、应用无密钥泄露；日志应显示 Cloudflare Provider 被采用。
5. 删除专用故障 Preview。不得把无效值带到 Production。

