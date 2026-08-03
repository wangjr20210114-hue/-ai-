from agents._tests.support.workspace_environment import *  # noqa: F401,F403


class SearchMediaReviewTests(unittest.IsolatedAsyncioTestCase):
    async def test_message_restore_rehydrates_image_versions_from_current_workspace(self):
        workspace = empty_workspace()
        first = new_action(
            "image_generate", {"prompt": "黄围巾", "group_id": "cat-group"},
            requires_confirmation=False,
        )
        second = new_action(
            "image_generate",
            {"prompt": "红围巾", "group_id": "cat-group", "parent_action_id": first["id"]},
            requires_confirmation=False,
        )
        for created_at, action, url in (
            (1, first, "https://example.com/yellow.png"),
            (2, second, "https://example.com/red.png"),
        ):
            action["created_at"] = created_at
            action["status"] = "succeeded"
            action["result"] = {"ok": True, "image_url": url}
            put_action(workspace, action)
        store_data = FakeStore()
        await save_workspace(store_data, TEST_USER_ID, workspace)
        checkpoint_action = {**first, "result": {**first["result"], "versions": image_versions(workspace, "cat-group")[:1]}}
        messages = [
            {"type": "human", "content": "画一只猫", "id": "u-image"},
            {"type": "tool", "content": json.dumps({"ui_action": "side_effect_action", "action": checkpoint_action})},
            {"type": "ai", "content": "图片已经生成", "id": "a-image"},
        ]
        store = SimpleNamespace(
            langgraph_checkpointer=FakeCheckpointer(messages),
            langgraph_store=store_data,
        )
        response = await messages_handler(authenticated_namespace(conversation_id="restore-image", store=store))
        action = next(item for item in response["messages"] if item["role"] == "ai")["workspaceActions"][0]
        self.assertEqual(
            [item["image_url"] for item in action["result"]["versions"]],
            ["https://example.com/yellow.png", "https://example.com/red.png"],
        )

    def test_all_structured_actions_keep_public_answer_streaming(self):
        self.assertFalse(should_buffer_public_answer({"needs_route": True}))
        self.assertFalse(should_buffer_public_answer({
            "needs_route": False,
            "needs_calendar_action": True,
        }))
        self.assertFalse(should_buffer_public_answer({
            "needs_image_generation": True,
        }))
        self.assertFalse(should_buffer_public_answer({
            "needs_route": False,
            "needs_calendar_action": False,
            "needs_image_generation": False,
        }))

    def test_semantic_web_search_makes_media_available_without_keyword_rules(self):
        self.assertTrue(media_enabled_for_plan({
            "needs_web_search": True,
            "needs_images": False,
        }, 2))
        self.assertFalse(media_enabled_for_plan({
            "needs_web_search": False,
            "needs_images": False,
        }, 2))
        self.assertFalse(media_enabled_for_plan({
            "needs_web_search": True,
            "needs_images": True,
        }, 0))
        self.assertTrue(media_enabled_for_plan({
            "needs_web_search": False,
            "needs_images": False,
        }, 2, planner_timed_out=True))

    def test_search_media_is_progressive_except_when_generation_needs_references(self):
        self.assertTrue(progressive_media_for_plan({
            "needs_web_search": True,
            "needs_images": True,
            "needs_image_generation": False,
        }))
        self.assertFalse(progressive_media_for_plan({
            "needs_web_search": True,
            "needs_images": True,
            "needs_image_generation": True,
        }))
        self.assertTrue(progressive_media_for_plan(
            {"needs_web_search": False},
            planner_timed_out=True,
        ))

    def test_searchpro_html_passage_exposes_provider_article_image(self):
        pages = _parse_pages({"Response": {"Pages": [{
            "url": "https://news.example/item",
            "title": "大会新闻",
            "passage": "<p>正文</p><img src='http://qqpublic.qpic.cn/news.jpg' width='700'>",
            "pics": [{
                "caption": "大会现场",
                "origin_url": "http://qqpublic.qpic.cn/provider-news.jpg",
            }],
        }, {
            "url": "https://news.example/embedded",
            "title": "摘要内图片",
            "passage": "<p>正文</p><img src='http://qqpublic.qpic.cn/embedded.jpg'>",
        }]}}, 8)
        self.assertEqual(pages[0]["image"], "https://qqpublic.qpic.cn/provider-news.jpg")
        self.assertEqual(pages[0]["provider_images"][0]["caption"], "大会现场")
        self.assertEqual(pages[1]["image"], "https://qqpublic.qpic.cn/embedded.jpg")
        ranked = _rank_source_results([{
            "url": "https://travel.example/guide",
            "title": "北京故宫旅游攻略，性价比高的导游与预算",
            "snippet": "旅行社报名优惠",
        }, {
            "url": "https://www.dpm.org.cn/visit.html",
            "title": "故宫博物院参观信息",
            "snippet": "开放时间、票务与参观路线公告",
        }], "北京故宫有哪些值得玩的地方")
        self.assertEqual(ranked[0]["url"], "https://www.dpm.org.cn/visit.html")

    def test_rich_search_handoff_keeps_media_out_of_model_authored_markdown(self):
        metadata = {
            "results": [{
                "id": "source-1", "source": "wsa", "title": "故宫",
                "snippet": "明清宫殿", "url": "https://example.com/palace",
            }],
            "media": [{
                "id": "media-1", "source_id": "source-1",
                "caption": "故宫太和殿建筑",
                "url": "https://cdn.example.com/palace.jpg",
            }],
        }
        evidence = evidence_for_model(metadata)
        self.assertIn("source_id=source-1", evidence)
        self.assertIn("不要自行输出图片 Markdown", evidence)
        self.assertNotIn("![故宫太和殿建筑]", evidence)
        self.assertNotIn("[[image:", evidence)
        self.assertNotIn("[[card:", evidence)

    def test_planner_preferred_media_is_required_when_reviewed(self):
        metadata = {
            "results": [],
            "media_pending": False,
            "media": [{
                "caption": "发布会现场",
                "url": "https://cdn.example.com/launch.jpg",
            }],
        }
        evidence = evidence_for_model(metadata, require_relevant_image=True)
        self.assertIn("必须引用它对应的网页来源", evidence)
        self.assertIn("不要自行输出图片 Markdown", evidence)

    async def test_progressive_rich_search_caches_only_completed_reviewed_media(self):
        store = FakeStore()
        background_tasks = []
        published = []
        media_gate = asyncio.Event()
        base = {
            "query": "AI 新闻", "results": [], "media": [], "images": [],
            "total": 0, "media_pending": True,
        }
        enriched = {
            **base,
            "media": [{
                "id": "media-1", "url": "https://example.com/news.jpg",
                "caption": "新闻现场", "source_title": "示例来源",
            }],
            "images": ["https://example.com/news.jpg"],
            "media_pending": False,
        }

        async def provider(*_args, media_callback=None, background_tasks=None, **_kwargs):
            async def finish_media():
                await media_gate.wait()
                await media_callback(enriched)
            background_tasks.append(asyncio.create_task(finish_media()))
            return base

        async def publish(metadata):
            published.append(metadata)

        with patch("agents._infrastructure.skills.builtin_operations.provider_rich_search", new=AsyncMock(side_effect=provider)) as mocked:
            tools = build_system_skill_tools(
                None, store=store, conversation_id="progressive-search",
                user_id=TEST_USER_ID, env={},
                media_enabled=True, progressive_media=True, media_callback=publish,
                background_tasks=background_tasks, planned_search_query="AI 新闻",
            )
            tool = next(item for item in tools if item.name == "rich_search")
            first = json.loads(await tool.ainvoke({"query": "AI 新闻"}))
            self.assertTrue(first["search_results"]["media_pending"])
            self.assertFalse(background_tasks[0].done())
            media_gate.set()
            await asyncio.gather(*background_tasks)
            self.assertEqual(published[0]["images"], enriched["images"])

            next_background_tasks = []
            media_gate.clear()
            next_turn_tools = build_system_skill_tools(
                None, store=store, conversation_id="progressive-search-2",
                user_id=TEST_USER_ID, env={},
                media_enabled=True, progressive_media=True, media_callback=publish,
                background_tasks=next_background_tasks, planned_search_query="AI 新闻",
            )
            next_turn_tool = next(item for item in next_turn_tools if item.name == "rich_search")
            reused = json.loads(await next_turn_tool.ainvoke({"query": "不同措辞"}))
            media_gate.set()
            await asyncio.gather(*next_background_tasks)
            self.assertEqual(mocked.await_count, 1)
            self.assertEqual(next_background_tasks, [])
            self.assertTrue(reused["search_results"]["cache"]["hit"])
            self.assertFalse(reused["search_results"]["cache"]["answer_cached"])
            self.assertEqual(reused["search_results"]["images"], enriched["images"])

    def test_pending_search_media_never_promises_image_generation(self):
        prompt = evidence_for_model({
            "results": [], "media": [], "media_pending": True,
        })
        self.assertIn("图片正在后台审核", prompt)
        self.assertIn("不要声称正在生成图片", prompt)
        self.assertIn("不要输出任何媒体占位符", prompt)
        self.assertNotIn("[[YUANBAO_MEDIA]]", prompt)

    def test_required_pending_search_media_never_uses_a_model_protocol_slot(self):
        prompt = evidence_for_model({
            "results": [],
            "media": [],
            "preview_media": [{
                "url": "https://img.example.com/provider-preview.jpg",
            }],
            "media_pending": True,
        }, require_relevant_image=True)
        self.assertIn("图片正在后台审核", prompt)
        self.assertIn("不要输出任何媒体占位符", prompt)
        self.assertNotIn("[[YUANBAO_MEDIA", prompt)

    def test_reviewed_search_media_is_bound_to_a_source_for_frontend_placement(self):
        prompt = evidence_for_model({
            "results": [], "media_pending": False,
            "media": [{
                "id": "media-1", "caption": "大会现场",
                "url": "https://img.example.com/conference.jpg",
                "source_id": "source-1",
                "source_title": "AI 新闻", "source_url": "https://news.example.com/ai",
            }],
        })
        self.assertIn("source_id=source-1", prompt)
        self.assertIn("前端会按 source_id", prompt)
        self.assertNotIn("![大会现场]", prompt)
        self.assertNotIn("[[YUANBAO_MEDIA]]", prompt)

    async def test_search_preferences_allow_eight_images_and_clamp_larger_values(self):
        store = FakeStore()
        state = empty_intelligence_state()
        state["search_preferences"]["image_limit"] = 99
        await save_intelligence_state(store, state, "image-limit-user")
        restored = await load_intelligence_state(store, "image-limit-user")
        self.assertEqual(restored["search_preferences"]["image_limit"], 8)

    async def test_legacy_two_image_default_migrates_once_without_overriding_new_choice(self):
        store = FakeStore()
        legacy = empty_intelligence_state()
        legacy["schema_version"] = 1
        legacy["search_preferences"]["image_limit"] = 2
        await save_intelligence_state(store, legacy, "legacy-image-limit-user")
        stored = next(iter(store.values.values()))
        stored["schema_version"] = 1
        migrated = await load_intelligence_state(store, "legacy-image-limit-user")
        self.assertEqual(migrated["schema_version"], 2)
        self.assertEqual(migrated["search_preferences"]["image_limit"], 8)

        migrated["search_preferences"]["image_limit"] = 2
        await save_intelligence_state(store, migrated, "legacy-image-limit-user")
        restored = await load_intelligence_state(store, "legacy-image-limit-user")
        self.assertEqual(restored["search_preferences"]["image_limit"], 2)

    def test_image_versions_are_grouped_and_ordered(self):
        state = empty_workspace()
        first = new_action("image_generate", {"prompt": "初版", "group_id": "group-1"}, requires_confirmation=False)
        second = new_action("image_generate", {"prompt": "日落版", "group_id": "group-1", "parent_action_id": first["id"]}, requires_confirmation=False)
        ignored = new_action("image_generate", {"prompt": "其他组", "group_id": "group-2"}, requires_confirmation=False)
        first["created_at"] = 1
        second["created_at"] = 2
        for action, url in ((first, "https://example.com/1.png"), (second, "https://example.com/2.png"), (ignored, "https://example.com/3.png")):
            action["status"] = "succeeded"
            action["result"] = {"ok": True, "image_url": url}
            put_action(state, action)
        versions = image_versions(state, "group-1")
        self.assertEqual([item["prompt"] for item in versions], ["初版", "日落版"])
        self.assertEqual(versions[1]["parent_action_id"], first["id"])

    def test_vision_review_uses_multimodal_model_and_dedicated_tokenhub_key(self):
        response = {"choices": [{"message": {"content": '{"description":"发布会现场","relevant":true}'}}]}
        with patch("agents._infrastructure.providers.rich_search._json_request", return_value=response) as request:
            description, outcome = _review_image(
                {"HUNYUAN_IMAGE_API_KEY": "vision-key"},
                {"url": "https://example.com/news.jpg", "context": "AI 发布会"},
                "AI 最新进展",
            )
        self.assertEqual((description, outcome), ("发布会现场", "approved"))
        url, payload, headers, _timeout = request.call_args.args
        self.assertEqual(url, "https://tokenhub.tencentmaas.com/v1/chat/completions")
        self.assertEqual(payload["model"], "hy-vision-2.0-instruct")
        self.assertEqual(headers["Authorization"], "Bearer vision-key")

    async def test_vision_batch_reviews_candidates_as_parallel_single_image_calls(self):
        responses = [
            (json.dumps({"description": "发布会现场", "relevant": True}, ensure_ascii=False), {"provider": "hunyuan"}),
            (json.dumps({"description": "广告", "relevant": False}, ensure_ascii=False), {"provider": "hunyuan"}),
        ]
        candidates = [
            {"url": "https://example.com/1.jpg", "source_url": "https://source.example/1", "source_title": "一", "context": "现场"},
            {"url": "https://example.com/2.jpg", "source_url": "https://source.example/2", "source_title": "二", "context": "广告"},
        ]
        with patch(
            "agents._infrastructure.providers.rich_search.vision_completion",
            new=AsyncMock(side_effect=responses),
        ) as request:
            reviewed, diagnostics = await _vision_filter({"HUNYUAN_IMAGE_API_KEY": "vision-key"}, "AI 新闻", candidates)
        self.assertEqual([item["url"] for item in reviewed], ["https://example.com/1.jpg"])
        self.assertEqual(diagnostics["reviewed"], 2)
        self.assertEqual(request.call_count, 2)
        for call in request.call_args_list:
            content = call.args[1]
            self.assertEqual(sum(block.get("type") == "image_url" for block in content), 1)
            self.assertEqual(content[0]["type"], "image_url")
        self.assertEqual(diagnostics["provider_hunyuan"], 2)

    async def test_vision_batch_obeys_user_image_limit(self):
        response = json.dumps({"description": "相关图片", "relevant": True}, ensure_ascii=False)
        candidates = [
            {"url": f"https://example.com/{index}.jpg", "source_url": f"https://source.example/{index}", "source_title": str(index)}
            for index in range(1, 7)
        ]
        with patch(
            "agents._infrastructure.providers.rich_search.vision_completion",
            new=AsyncMock(return_value=(response, {"provider": "hunyuan"})),
        ) as request:
            reviewed, diagnostics = await _vision_filter(
                {"HUNYUAN_IMAGE_API_KEY": "vision-key"}, "AI 新闻", candidates, 2,
            )
        self.assertEqual(len(reviewed), 2)
        self.assertEqual(diagnostics["reviewed"], 2)
        self.assertEqual(request.call_count, 2)

    async def test_vision_batch_supports_eight_image_setting(self):
        response = json.dumps({
            "description": "相关图片",
            "relevant": True,
            "promotional": False,
        }, ensure_ascii=False)
        candidates = [
            {
                "url": f"https://example.com/editorial-{index}.jpg",
                "source_url": f"https://source.example/{index}",
                "source_title": str(index),
            }
            for index in range(1, 11)
        ]
        with patch(
            "agents._infrastructure.providers.rich_search.vision_completion",
            new=AsyncMock(return_value=(response, {"provider": "hunyuan"})),
        ) as request:
            reviewed, diagnostics = await _vision_filter(
                {"HUNYUAN_IMAGE_API_KEY": "vision-key"},
                "需要多张配图的查询",
                candidates,
                8,
            )
        self.assertEqual(len(reviewed), 8)
        self.assertEqual(diagnostics["reviewed"], 8)
        self.assertEqual(request.call_count, 8)

    async def test_vision_rejects_promotional_image_even_when_semantically_relevant(self):
        candidates = [{
            "url": "https://example.com/news-image.jpg",
            "source_url": "https://source.example/story",
            "source_title": "产品发布",
        }]
        response = json.dumps({
            "description": "带购买卖点的产品宣传图",
            "relevant": True,
            "promotional": True,
        }, ensure_ascii=False)
        with patch(
            "agents._infrastructure.providers.rich_search.vision_completion",
            new=AsyncMock(return_value=(response, {"provider": "hunyuan"})),
        ):
            reviewed, diagnostics = await _vision_filter(
                {"HUNYUAN_IMAGE_API_KEY": "vision-key"},
                "产品发布新闻",
                candidates,
                2,
            )
        self.assertEqual(reviewed, [])
        self.assertEqual(diagnostics["promotional"], 1)

    async def test_vision_budget_prioritizes_editorial_images_over_avatars_and_banners(self):
        candidates = [
            {
                "url": "https://img.example.com/banner.png?w=1600&h=200&size=20",
                "source_url": "https://source.example/banner",
                "source_title": "横幅",
            },
            {
                "url": "https://profile.example.com/avatar_user.png",
                "source_url": "https://source.example/avatar",
                "source_title": "头像",
            },
            *[
                {
                    "url": f"https://img.example.com/editorial-{index}.jpg?w=1200&h=800&size={200 + index}",
                    "source_url": f"https://source.example/story-{index}",
                    "source_title": f"正文图片 {index}",
                    "context": "这是一段与报道正文相邻的具体事件说明。" * 6,
                }
                for index in range(1, 5)
            ],
        ]
        response = json.dumps(
            {"description": "新闻现场", "relevant": True},
            ensure_ascii=False,
        )
        with patch(
            "agents._infrastructure.providers.rich_search.vision_completion",
            new=AsyncMock(return_value=(response, {"provider": "hunyuan"})),
        ) as request:
            reviewed, diagnostics = await _vision_filter(
                {"HUNYUAN_IMAGE_API_KEY": "vision-key"},
                "一项需要真实配图的查询",
                candidates,
                4,
            )
        reviewed_urls = [
            call.args[1][0]["image_url"]["url"]
            for call in request.call_args_list
        ]
        self.assertEqual(diagnostics["reviewed"], 4)
        self.assertEqual(len(reviewed), 4)
        self.assertTrue(all("editorial-" in url for url in reviewed_urls))
        self.assertEqual(diagnostics["prefilter_profile_or_brand_asset"], 1)
        self.assertEqual(diagnostics["prefilter_banner_geometry"], 1)

    async def test_vision_budget_uses_query_context_before_unrelated_large_image(self):
        candidates = [
            {
                "url": "https://img.example.com/unrelated.jpg?w=1800&h=1200&size=900",
                "source_url": "https://source.example/unrelated",
                "source_title": "综合资讯",
                "context": "足球赛况与球队转会消息",
            },
            *[
                {
                    "url": f"https://img.example.com/relevant-{index}.jpg?w=900&h=600&size=120",
                    "source_url": f"https://source.example/relevant-{index}",
                    "source_title": "综合资讯",
                    "context": "人工智能产品发布会现场展示新的推理模型",
                }
                for index in range(1, 5)
            ],
        ]
        response = json.dumps({
            "description": "发布会现场",
            "relevant": True,
            "promotional": False,
        }, ensure_ascii=False)
        with patch(
            "agents._infrastructure.providers.rich_search.vision_completion",
            new=AsyncMock(return_value=(response, {"provider": "hunyuan"})),
        ) as request:
            await _vision_filter(
                {"HUNYUAN_IMAGE_API_KEY": "vision-key"},
                "人工智能模型发布会",
                candidates,
                4,
            )
        reviewed_urls = [
            call.args[1][0]["image_url"]["url"]
            for call in request.call_args_list
        ]
        self.assertEqual(len(reviewed_urls), 4)
        self.assertTrue(all("relevant-" in url for url in reviewed_urls))

    async def test_image_retries_share_one_turn_group(self):
        store = FakeStore()
        tools = build_system_skill_tools(
            None, store=store, conversation_id="image-turn",
            user_id=TEST_USER_ID, env={},
        )
        tool = next(item for item in tools if item.name == "propose_image")
        failed = {"ok": False, "error": "temporary provider failure", "image_url": ""}
        with patch("agents._infrastructure.skills.builtin_operations.provider_generate_image", new=AsyncMock(return_value=failed)):
            first = json.loads(await tool.ainvoke({"prompt": "first"}))["action"]
            second = json.loads(await tool.ainvoke({"prompt": "retry"}))["action"]
        self.assertEqual(first["payload"]["group_id"], second["payload"]["group_id"])

    async def test_uploaded_reference_image_is_handed_to_image_provider_without_model_copying_data(self):
        reference = "data:image/jpeg;base64,ZmFrZQ=="
        tools = build_system_skill_tools(
            None, store=FakeStore(), conversation_id="image-reference", env={},
            user_id=TEST_USER_ID,
            initial_visual_references=[reference],
        )
        tool = next(item for item in tools if item.name == "propose_image")
        result = {"ok": True, "image_url": "https://example.com/generated.png"}
        with patch("agents._infrastructure.skills.builtin_operations.provider_generate_image", new=AsyncMock(return_value=result)) as provider:
            action = json.loads(await tool.ainvoke({"prompt": "按参考图生成卡通版"}))["action"]
        self.assertEqual(action["payload"]["reference_image_urls"], [reference])
        provider.assert_awaited_once_with(
            {},
            "按参考图生成卡通版",
            [reference],
            user_id=TEST_USER_ID,
        )

    async def test_rich_search_falls_back_to_traceable_provider_image_when_vision_is_unavailable(self):
        page = {
            "url": "https://example.com/news",
            "title": "AI 发布会",
            "passage": "<p>报道</p><img src='http://img.example.com/hero.jpg'>",
        }
        with (
            patch("agents._infrastructure.providers.rich_search._json_request", return_value={"Pages": [page]}) as search_request,
            patch("agents._infrastructure.providers.rich_search.collect_page_media", new=AsyncMock(return_value=[])),
        ):
            result = await run_rich_search(
                {"WSA_API_KEY": "test"}, "AI 新闻", "AI 发布会现场", "basic", image_limit=2,
            )
        self.assertEqual(result["images"], ["https://img.example.com/hero.jpg"])
        self.assertEqual(result["results"][0]["image"], "https://img.example.com/hero.jpg")
        self.assertEqual(result["preview_media"][0]["url"], "https://img.example.com/hero.jpg")
        self.assertTrue(result["preview_media"][0]["preview"])
        self.assertEqual(result["media"][0]["url"], "https://img.example.com/hero.jpg")
        self.assertFalse(result["media"][0]["vision_reviewed"])
        self.assertTrue(result["media"][0]["vision_fallback"])
        self.assertTrue(result["media"][0]["source_bound_fallback"])
        self.assertEqual(result["vision_diagnostics"]["missing_api_key"], 1)
        self.assertEqual(result["vision_diagnostics"]["provider_fallback"], 1)
        provider_query = search_request.call_args.args[1]["Query"]
        self.assertIn("官方 权威原始信息", provider_query)
        self.assertEqual(search_request.call_args.args[1]["Cnt"], 20)

    async def test_strict_today_filter_also_excludes_old_article_media(self):
        pages = [{
            "url": "https://example.com/old",
            "title": "旧消息",
            "date": "2026-07-28",
            "image": "https://img.example.com/old.jpg",
            "passage": "昨天发布",
        }, {
            "url": "https://example.com/today",
            "title": "今日消息",
            "date": "2026-07-29",
            "image": "https://img.example.com/today.jpg",
            "passage": "今天发布",
        }]
        with (
            patch("agents._infrastructure.providers.rich_search._json_request", return_value={"Pages": pages}),
            patch("agents._infrastructure.providers.rich_search.collect_page_media", new=AsyncMock(return_value=[])),
        ):
            result = await run_rich_search(
                {"WSA_API_KEY": "test"},
                "今天 AI 有什么新消息",
                "AI 新闻现场",
                "basic",
                target_date="2026-07-29",
                strict_date=True,
                image_limit=2,
            )
        self.assertEqual(
            [item["url"] for item in result["results"]],
            ["https://example.com/today"],
        )
        self.assertEqual(result["images"], ["https://img.example.com/today.jpg"])
        self.assertNotIn("https://img.example.com/old.jpg", json.dumps(result))

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

