from agents._tests.support.workspace_environment import *  # noqa: F401,F403
from agents._domain.search.source_policy import (
    filter_preferred_recent_sources,
    source_domain,
)


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
            "site": "Example Publisher",
            "score": 0.87,
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
        self.assertEqual(pages[0]["publisher"], "Example Publisher")
        self.assertEqual(pages[0]["relevance_score"], 0.87)
        self.assertEqual(pages[0]["provider_images"][0]["caption"], "大会现场")
        self.assertEqual(pages[1]["image"], "https://qqpublic.qpic.cn/embedded.jpg")

    def test_source_ranking_keeps_a_second_publisher_when_relevant(self):
        self.assertEqual(
            source_domain("https://portal.example.co.uk?view=latest"),
            "example.co.uk",
        )
        ranked = rank_source_results([
            {
                "url": "https://gateway.example/news/1", "publisher": "Publisher A",
                "title": "AI 进展",
                "snippet": "AI 进展 官方公告",
            },
            {
                "url": "https://gateway.example/news/2", "publisher": "Publisher A",
                "title": "AI 进展补充",
                "snippet": "AI 进展 官方公告",
            },
            {
                "url": "https://gateway.example/news/3", "publisher": "Publisher B",
                "title": "AI 进展观察",
                "snippet": "AI 进展",
            },
        ], "AI 进展")
        self.assertEqual(
            [item["url"] for item in ranked[:2]],
            ["https://gateway.example/news/1", "https://gateway.example/news/3"],
        )
        ranked = rank_source_results([{
            "url": "https://feed.example/entry",
            "title": "System release notes",
            "snippet": "System release details",
        }, {
            "url": "https://research.example.edu/release",
            "title": "System release notes",
            "snippet": "System release details",
        }], "system release details")
        self.assertEqual(
            ranked[0]["url"], "https://research.example.edu/release"
        )

    def test_recent_source_ranking_prefers_verified_fresh_dates(self):
        ranked = rank_source_results([{
            "url": "https://example.com/old",
            "title": "AI 重要进展",
            "snippet": "人工智能行业消息",
            "date": "2024-05-06",
        }, {
            "url": "https://example.org/fresh",
            "title": "AI 最新进展",
            "snippet": "人工智能行业消息",
            "date": "2026-08-03",
        }], "最近 AI 有什么新进展", "2026-08-04", True)
        self.assertEqual(ranked[0]["url"], "https://example.org/fresh")
        self.assertEqual(ranked[0]["date"], "2026-08-03")

    def test_recent_source_filter_does_not_pad_with_stale_results(self):
        filtered, diagnostics = filter_preferred_recent_sources([{
            "url": "https://example.com/old",
            "title": "2024 年 AI 进展",
            "snippet": "旧消息",
            "date": "2024-05-06",
        }, {
            "url": "https://example.org/fresh",
            "title": "AI 最新进展",
            "snippet": "近期消息",
            "date": "2026-08-03",
        }, {
            "url": "https://example.net/undated",
            "title": "AI 观察",
            "snippet": "没有可核验日期",
            "date": "",
        }], "2026-08-04")

        self.assertEqual(
            [item["url"] for item in filtered],
            ["https://example.org/fresh"],
        )
        self.assertTrue(diagnostics["applied"])
        self.assertEqual(diagnostics["stale_or_undated"], 2)

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
        self.assertNotIn("经视觉模型审核、可由界面展示的图片素材", prompt)
        self.assertNotIn("无通过视觉筛选的图片", prompt)
        self.assertIn("不得评论图片是否存在、是否通过审核", prompt)
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
        self.assertNotIn("provider-preview.jpg", prompt)
        self.assertNotIn("经视觉模型审核、可由界面展示的图片素材", prompt)
        self.assertIn("不要输出任何媒体占位符", prompt)
        self.assertNotIn("[[YUANBAO_MEDIA", prompt)

    def test_recent_search_evidence_does_not_turn_recent_into_today(self):
        prompt = evidence_for_model({
            "query": "最近 AI 有什么新进展",
            "target_date": "2026-08-04",
            "strict_date": False,
            "search_config": {"prefer_recent": True},
            "results": [],
            "media": [],
            "media_pending": False,
        })
        self.assertIn("不是只问当天", prompt)
        self.assertIn("不要把“最近”改写成“今天”", prompt)
        self.assertIn("不要为了凑数量混入旧闻", prompt)

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

    async def test_rich_search_does_not_publish_provider_image_without_visual_review(self):
        page = {
            "url": "https://example.com/news",
            "title": "AI 发布会",
            "passage": "<p>报道</p><img src='http://img.example.com/hero.jpg'>",
        }
        with (
            patch("agents._infrastructure.providers.rich_search._searchpro_request_json", return_value={"Pages": [page]}) as search_request,
            patch("agents._infrastructure.providers.rich_search.collect_page_media", new=AsyncMock(return_value=[])),
        ):
            result = await run_rich_search(
                {"WSA_API_KEY": "test"}, "AI 新闻", "AI 发布会现场", "basic", image_limit=2,
            )
        self.assertEqual(result["images"], [])
        self.assertEqual(result["results"][0]["image"], "https://img.example.com/hero.jpg")
        self.assertEqual(result["preview_media"][0]["url"], "https://img.example.com/hero.jpg")
        self.assertTrue(result["preview_media"][0]["preview"])
        self.assertEqual(result["media"], [])
        self.assertEqual(result["vision_diagnostics"]["missing_api_key"], 1)
        provider_payload = search_request.call_args.args[1]
        self.assertIn("AI 新闻", provider_payload["Query"])
        self.assertEqual(set(provider_payload), {"Query"})

    async def test_rich_search_does_not_publish_page_media_without_visual_review(self):
        page = {
            "url": "https://example.com/forbidden-city",
            "title": "Forbidden City architecture guide",
            "passage": "Verified architecture guide.",
        }
        candidate = {
            "url": "https://img.example.com/hall.jpg?w=1200&h=800",
            "context": "Forbidden City architecture and ceremonial hall",
            "alt": "Forbidden City ceremonial hall",
        }
        with (
            patch("agents._infrastructure.providers.rich_search._searchpro_request_json", return_value={"Pages": [page]}),
            patch("agents._infrastructure.providers.rich_search.collect_page_media", new=AsyncMock(return_value=[candidate])),
        ):
            result = await run_rich_search(
                {"WSA_API_KEY": "test"},
                "Forbidden City architecture",
                "Forbidden City ceremonial hall",
                "basic",
                image_limit=2,
            )
        self.assertEqual(result["images"], [])
        self.assertEqual(result["media"], [])
        self.assertEqual(result["vision_diagnostics"]["missing_api_key"], 1)

    async def test_vision_deadline_keeps_completed_approved_images_only(self):
        candidates = [
            {"url": "https://img.example.com/approved.jpg?w=1200&h=800", "source_url": "https://example.com/approved", "source_title": "Approved source", "context": "AI launch event"},
            {"url": "https://img.example.com/pending.jpg?w=1200&h=800", "source_url": "https://example.com/pending", "source_title": "Pending source", "context": "AI launch event"},
        ]

        async def partial_review(_env, content, **_kwargs):
            url = content[0]["image_url"]["url"]
            if "pending" in url:
                await asyncio.sleep(2)
            return json.dumps({"description": "Verified launch photo", "relevant": True, "promotional": False}), {"provider": "vision-test"}

        with (
            patch("agents._infrastructure.providers.rich_search._vision_review_timeout", return_value=0.01),
            patch("agents._infrastructure.providers.rich_search.vision_completion", new=partial_review),
        ):
            reviewed, diagnostics = await _vision_filter(
                {"HUNYUAN_VISION_API_KEY": "test"}, "AI launch event", candidates, 2,
            )

        self.assertEqual([item["url"] for item in reviewed], [candidates[0]["url"]])
        self.assertEqual(diagnostics["approved"], 1)
        self.assertEqual(diagnostics["reviewed"], 1)
        self.assertEqual(diagnostics["timeout"], 1)

    async def test_explicit_vision_rejection_never_uses_source_bound_fallback(self):
        page = {
            "url": "https://example.com/architecture",
            "title": "Architecture guide",
            "passage": "Verified architecture guide.",
        }
        candidate = {
            "url": "https://img.example.com/unrelated.jpg?w=1200&h=800",
            "context": "Architecture guide illustration",
            "alt": "Architecture illustration",
        }
        rejection = json.dumps({
            "description": "Unrelated image",
            "relevant": False,
            "promotional": False,
        })
        with (
            patch("agents._infrastructure.providers.rich_search._searchpro_request_json", return_value={"Pages": [page]}),
            patch("agents._infrastructure.providers.rich_search.collect_page_media", new=AsyncMock(return_value=[candidate])),
            patch("agents._infrastructure.providers.rich_search.vision_completion", new=AsyncMock(return_value=(rejection, {"provider": "vision-test"}))),
        ):
            result = await run_rich_search(
                {"WSA_API_KEY": "test", "HUNYUAN_IMAGE_API_KEY": "vision-key"},
                "Architecture guide",
                "Architecture illustration",
                "basic",
                image_limit=2,
            )
        self.assertEqual(result["media"], [])
        self.assertEqual(result["vision_diagnostics"]["irrelevant"], 1)
        self.assertNotIn("source_bound_fallback", result["vision_diagnostics"])

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
            patch("agents._infrastructure.providers.rich_search._searchpro_request_json", return_value={"Pages": pages}),
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
        self.assertEqual(result["images"], [])
        self.assertEqual(
            [item["url"] for item in result["preview_media"]],
            ["https://img.example.com/today.jpg"],
        )
        self.assertNotIn("https://img.example.com/old.jpg", json.dumps(result))
