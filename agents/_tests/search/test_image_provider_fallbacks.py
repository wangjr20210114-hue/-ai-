from agents._tests.support.workspace_environment import *  # noqa: F401,F403


class ImageProviderFallbackTests(unittest.IsolatedAsyncioTestCase):
    def test_free_vision_fallback_chain_keeps_hunyuan_primary(self):
        providers = vision_providers({
            "HUNYUAN_IMAGE_API_KEY": "hy",
            "CLOUDFLARE_ACCOUNT_ID": "account",
            "CLOUDFLARE_WORKERS_AI_TOKEN": "cf",
            "DASHSCOPE_API_KEY": "qwen",
            "GEMINI_API_KEY": "gemini",
        })
        self.assertEqual([item.name for item in providers], [
            "hunyuan", "cloudflare", "dashscope", "gemini",
        ])
        self.assertEqual(
            providers[1].endpoint,
            "https://api.cloudflare.com/client/v4/accounts/account/ai/run/@cf/meta/llama-3.2-11b-vision-instruct",
        )

    def test_preview_can_force_cloudflare_vision_first_without_changing_default_order(self):
        providers = vision_providers({
            "HUNYUAN_IMAGE_API_KEY": "hy",
            "CLOUDFLARE_ACCOUNT_ID": "account",
            "CLOUDFLARE_WORKERS_AI_TOKEN": "cf",
            "VISION_PROVIDER_ORDER": "cloudflare,hunyuan",
        })
        self.assertEqual([item.name for item in providers], ["cloudflare", "hunyuan"])

    def test_cloudflare_vision_uses_official_run_schema(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _limit):
                return json.dumps({
                    "success": True,
                    "result": {"response": "一只戴红围巾的猫"},
                }).encode("utf-8")

        provider = VisionProvider(
            "cloudflare",
            "https://api.cloudflare.com/client/v4/accounts/account/ai/run/@cf/meta/llama-3.2-11b-vision-instruct",
            "token",
            "@cf/meta/llama-3.2-11b-vision-instruct",
        )
        content = [
            {"type": "text", "text": "描述图片"},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,ZmFrZQ=="}},
        ]
        with patch(
            "agents._infrastructure.providers.vision.urllib.request.urlopen",
            return_value=Response(),
        ) as urlopen:
            result = _post_completion(provider, content, 200, 2)
        request = urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(result, "一只戴红围巾的猫")
        self.assertEqual(payload["messages"], [{"role": "user", "content": "描述图片"}])
        self.assertEqual(payload["image"], "data:image/jpeg;base64,ZmFrZQ==")
        self.assertNotIn("model", payload)

    async def test_user_reference_image_uses_multimodal_provider_once(self):
        with patch(
            "agents._infrastructure.providers.vision.vision_completion",
            new=AsyncMock(return_value=("一只戴红围巾的猫", {"provider": "cloudflare"})),
        ) as completion:
            description, diagnostics = await describe_reference_images(
                {}, ["data:image/jpeg;base64,ZmFrZQ=="], "描述图片",
            )
        self.assertEqual(description, "一只戴红围巾的猫")
        self.assertEqual(diagnostics["provider"], "cloudflare")
        self.assertEqual(completion.await_count, 1)

    async def test_multiple_reference_images_use_one_hy_vision_request_each(self):
        with patch(
            "agents._infrastructure.providers.vision.vision_completion",
            new=AsyncMock(side_effect=[
                ("第一张图片", {"provider": "hunyuan"}),
                ("第二张图片", {"provider": "hunyuan"}),
            ]),
        ) as completion:
            description, diagnostics = await describe_reference_images(
                {}, ["https://example.com/1.jpg", "https://example.com/2.jpg"], "比较图片",
            )
        self.assertIn("附图 1：第一张图片", description)
        self.assertIn("附图 2：第二张图片", description)
        self.assertEqual(diagnostics["provider"], "hunyuan")
        self.assertEqual(completion.await_count, 2)
        for call in completion.call_args_list:
            content = call.args[1]
            self.assertEqual(sum(block.get("type") == "image_url" for block in content), 1)

    async def test_image_generation_falls_back_to_cloudflare_workers_ai(self):
        env = {
            "CLOUDFLARE_ACCOUNT_ID": "account",
            "CLOUDFLARE_WORKERS_AI_TOKEN": "token",
        }
        persisted = {"storage_key": "generated/test.jpg", "image_url": "/files?key=generated/test.jpg"}
        with patch(
            "agents._infrastructure.providers.side_effects._cloudflare_image_prompt",
            return_value="an orange cat",
        ) as translator, patch(
            "agents._infrastructure.providers.side_effects._post_cloudflare_image",
            return_value=(b"jpeg", "image/jpeg"),
        ) as provider, patch(
            "agents._infrastructure.providers.side_effects._persist_generated_bytes",
            new=AsyncMock(return_value=persisted),
        ):
            result = await generate_image(
                env, "一只猫", user_id=TEST_USER_ID,
            )
        self.assertTrue(result["ok"])
        self.assertEqual(result["provider"], "cloudflare")
        self.assertTrue(result["prompt_translated"])
        self.assertEqual(result["storage_key"], "generated/test.jpg")
        translator.assert_called_once_with(
            "account", "token", "@cf/zai-org/glm-4.7-flash", "一只猫",
        )
        self.assertEqual(provider.call_count, 1)

    async def test_preview_can_force_cloudflare_image_generation_first(self):
        env = {
            "HUNYUAN_IMAGE_API_KEY": "hunyuan-key",
            "CLOUDFLARE_ACCOUNT_ID": "account",
            "CLOUDFLARE_WORKERS_AI_TOKEN": "token",
            "IMAGE_PROVIDER_ORDER": "cloudflare,hunyuan",
        }
        with patch(
            "agents._infrastructure.providers.side_effects._cloudflare_image_prompt",
            return_value="an orange cat",
        ), patch(
            "agents._infrastructure.providers.side_effects._post_cloudflare_image",
            return_value=(b"jpeg", "image/jpeg"),
        ) as cloudflare, patch(
            "agents._infrastructure.providers.side_effects._post_image",
        ) as hunyuan, patch(
            "agents._infrastructure.providers.side_effects._persist_generated_bytes",
            new=AsyncMock(return_value={"storage_key": "generated/test.jpg", "image_url": "/files?key=generated/test.jpg"}),
        ):
            result = await generate_image(
                env, "一只猫", user_id=TEST_USER_ID,
            )
        self.assertEqual(result["provider"], "cloudflare")
        self.assertFalse(result["fallback"])
        self.assertEqual(cloudflare.call_count, 1)
        hunyuan.assert_not_called()

    async def test_cloudflare_image_generation_continues_when_prompt_translation_fails(self):
        env = {
            "CLOUDFLARE_ACCOUNT_ID": "account",
            "CLOUDFLARE_WORKERS_AI_TOKEN": "token",
            "IMAGE_PROVIDER_ORDER": "cloudflare,hunyuan",
        }
        with patch(
            "agents._infrastructure.providers.side_effects._cloudflare_image_prompt",
            side_effect=RuntimeError("translation response shape changed"),
        ), patch(
            "agents._infrastructure.providers.side_effects._post_cloudflare_image",
            return_value=(b"png", "image/png"),
        ) as cloudflare, patch(
            "agents._infrastructure.providers.side_effects._persist_generated_bytes",
            new=AsyncMock(return_value={
                "storage_key": "generated/result.png",
                "image_url": "/files?key=result",
            }),
        ):
            result = await generate_image(
                env,
                "一只戴紫色围巾的橘猫",
                user_id=TEST_USER_ID,
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["provider"], "cloudflare")
        self.assertFalse(result["prompt_translated"])
        self.assertEqual(cloudflare.call_args.args[3], "一只戴紫色围巾的橘猫")

    def test_cloudflare_translates_chinese_image_prompt_with_current_multilingual_model(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _limit):
                return json.dumps({
                    "success": True,
                    "result": {
                        "choices": [{
                            "message": {
                                "content": "An orange cat wearing a blue scarf on a white background, no text."
                            }
                        }],
                    },
                }).encode("utf-8")

        with patch(
            "agents._infrastructure.providers.side_effects.urllib.request.urlopen",
            return_value=Response(),
        ) as urlopen:
            translated = _cloudflare_image_prompt(
                "account", "token", "@cf/zai-org/glm-4.7-flash",
                "一只戴蓝色围巾的橘猫，白色背景，不要文字",
            )
        request = urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertTrue(request.full_url.endswith("/ai/run/@cf/zai-org/glm-4.7-flash"))
        self.assertEqual(payload["temperature"], 0)
        self.assertIn("一只戴蓝色围巾的橘猫", payload["messages"][1]["content"])
        self.assertEqual(
            translated,
            "An orange cat wearing a blue scarf on a white background, no text.",
        )

    def test_cloudflare_semantically_normalizes_english_image_prompt_too(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _limit):
                return json.dumps({
                    "result": {"response": "An orange cat wearing a blue scarf."},
                }).encode("utf-8")

        with patch(
            "agents._infrastructure.providers.side_effects.urllib.request.urlopen",
            return_value=Response(),
        ) as urlopen:
            prompt = "An orange cat wearing a blue scarf."
            self.assertEqual(
                _cloudflare_image_prompt(
                    "account", "token", "@cf/zai-org/glm-4.7-flash", prompt,
                ),
                prompt,
            )
        urlopen.assert_called_once()

    def test_cloudflare_flux_uses_official_image_schema(self):
        class Response:
            headers = {"Content-Type": "application/json"}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _limit):
                return json.dumps({
                    "success": True,
                    "result": {"image": base64.b64encode(b"jpeg").decode("ascii")},
                }).encode("utf-8")

        with patch(
            "agents._infrastructure.providers.side_effects.urllib.request.urlopen",
            return_value=Response(),
        ) as urlopen:
            body, content_type = _post_cloudflare_image(
                "account", "token", "@cf/black-forest-labs/flux-1-schnell", "一只猫",
            )
        request = urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertTrue(request.full_url.endswith("/ai/run/@cf/black-forest-labs/flux-1-schnell"))
        self.assertEqual(payload, {"prompt": "一只猫", "steps": 4})
        self.assertEqual((body, content_type), (b"jpeg", "image/jpeg"))

    def test_cloudflare_img2img_uses_official_byte_array_reference(self):
        class Response:
            headers = {"Content-Type": "image/png"}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _limit):
                return b"png"

        with patch(
            "agents._infrastructure.providers.side_effects._reference_bytes",
            return_value=(b"source", "image/jpeg"),
        ), patch(
            "agents._infrastructure.providers.side_effects.urllib.request.urlopen",
            return_value=Response(),
        ) as urlopen:
            body, content_type = _post_cloudflare_image(
                "account", "token", "@cf/runwayml/stable-diffusion-v1-5-img2img",
                "改成水彩", ["data:image/jpeg;base64,c291cmNl"],
            )
        request = urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["image"], list(b"source"))
        self.assertEqual(payload["num_steps"], 12)
        self.assertEqual(payload["strength"], 0.72)
        self.assertNotIn("width", payload)
        self.assertNotIn("height", payload)
        self.assertEqual((body, content_type), (b"png", "image/png"))

    def test_cloudflare_img2img_retries_base64_for_legacy_rest_gateway(self):
        class Response:
            headers = {"Content-Type": "image/png"}

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _limit):
                return b"png"

        failed = urllib.error.HTTPError("https://example.com", 422, "schema", {}, None)
        with patch(
            "agents._infrastructure.providers.side_effects._reference_bytes",
            return_value=(b"source", "image/jpeg"),
        ), patch(
            "agents._infrastructure.providers.side_effects.urllib.request.urlopen",
            side_effect=[failed, Response()],
        ) as urlopen:
            body, content_type = _post_cloudflare_image(
                "account", "token", "@cf/runwayml/stable-diffusion-v1-5-img2img",
                "改成水彩", ["data:image/jpeg;base64,c291cmNl"],
            )
        self.assertEqual(urlopen.call_count, 2)
        retry_payload = json.loads(urlopen.call_args.args[0].data.decode("utf-8"))
        self.assertEqual(retry_payload["image_b64"], base64.b64encode(b"source").decode("ascii"))
        self.assertEqual((body, content_type), (b"png", "image/png"))

    def test_cloudflare_img2img_retries_when_schema_error_uses_http_200_envelope(self):
        class Response:
            headers = {"Content-Type": "application/json"}

            def __init__(self, payload):
                self.payload = payload

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _limit):
                return json.dumps(self.payload).encode("utf-8")

        rejected = Response({"success": False, "errors": [{"code": 1001, "message": "schema"}]})
        succeeded = Response({
            "success": True,
            "result": base64.b64encode(b"jpeg").decode("ascii"),
        })
        with patch(
            "agents._infrastructure.providers.side_effects._reference_bytes",
            return_value=(b"source", "image/jpeg"),
        ), patch(
            "agents._infrastructure.providers.side_effects.urllib.request.urlopen",
            side_effect=[rejected, succeeded],
        ) as urlopen:
            body, content_type = _post_cloudflare_image(
                "account", "token", "@cf/runwayml/stable-diffusion-v1-5-img2img",
                "green scarf", ["data:image/jpeg;base64,c291cmNl"],
            )

        self.assertEqual(urlopen.call_count, 2)
        first_payload = json.loads(urlopen.call_args_list[0].args[0].data.decode("utf-8"))
        retry_payload = json.loads(urlopen.call_args_list[1].args[0].data.decode("utf-8"))
        self.assertIn("image", first_payload)
        self.assertIn("image_b64", retry_payload)
        self.assertEqual((body, content_type), (b"jpeg", "image/jpeg"))
