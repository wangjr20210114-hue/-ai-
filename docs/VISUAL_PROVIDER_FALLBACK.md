# 视觉 Provider 降级链

更新时间：2026-07-21。

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

- 新闻图片审核：在一个共享 7 秒视觉预算内按顺序尝试已配置 Provider，并记录 `vision_diagnostics.provider_*`，不会把密钥或原始错误返回前端。Cloudflare 适配器使用官方 `/ai/run/@cf/meta/llama-3.2-11b-vision-instruct` REST 契约，将文本放入 `messages`、首张待审图片放入顶层 `image`；不把只明确支持文本生成的 OpenAI 兼容端点当作多模态接口。
- 新闻图片保底：如果所有视觉 Provider 均未配置、超时或暂时不可用，但 SearchPro 已返回文章主图，则保留去重后的 HTTPS 文章主图；只有视觉模型明确判断“不相关”时才丢弃。这样“最近 AI 有什么进展”不会仅因视觉密钥缺失退化为纯文字。
- 用户附图理解：发送前端压缩后的图片后，服务端先做一次多模态描述，再把事实描述交给 LLM 规划和回答；原始 Base64 不进入文本提示。
- 文生图：混元失败后，Cloudflare 使用 `FLUX.1 Schnell`。
- 图生图：混元失败后，Cloudflare 使用 img2img；当前降级适配器使用第一张参考图，混元仍支持最多三张参考图。
- 所有成功生成图片都复制到 Makers Blob；Provider 临时 URL 不是历史记录的唯一来源。

当前 Makers 项目的测试 `CLOUDFLARE_WORKERS_AI_TOKEN` 与 `CLOUDFLARE_ACCOUNT_ID` 均已收紧并核验为“预览”，生产环境不继承。多模态理解真实调用已正确识别合成测试图；Flux 英文文生图已正确生成白底、蓝围巾橘猫；`dpmnthmfw7fx` 的图生图日志真实显示 `provider=cloudflare`、`model=@cf/runwayml/stable-diffusion-v1-5-img2img`、`reference_count=1`、`fallback=False`，因此三条能力的接口可用性均已有 Preview 证据。中文翻译预处理使用 `@cf/zai-org/glm-4.7-flash`，但最终图生图实测仍返回不可用的翻译结果；适配器现在把翻译当可选步骤，失败后继续用原提示词调用图片模型。该次确实出图并保存为图片工坊新版本，但颜色、构图和“不要文字”的跟随效果有限，所以 Cloudflare 只作为免费可用性降级，不宣称与混元质量等价。

## 无破坏 Preview 验收

不要改 Production 密钥，也不要覆盖混元密钥。创建专用 Preview，只在 Preview 添加 Cloudflare 两项凭据和两个顺序变量：

1. 先不设置顺序变量，验证正常输出仍优先使用 `hunyuan`。
2. 临时把 `VISION_PROVIDER_ORDER` 和 `IMAGE_PROVIDER_ORDER` 设为 `cloudflare,hunyuan`。
3. 执行文生图、基于上一版本修改和上传图片问答。
4. 验证三项仍成功、生成图进入 Makers Blob、应用无密钥泄露；日志应显示 Cloudflare Provider 被采用。
5. 删除两个顺序变量并重新部署 Preview，确认恢复混元优先。不得把顺序变量带到 Production。
