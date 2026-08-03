from agents._tests.support.workspace_environment import *  # noqa: F401,F403
from agents.chat._graph import TOOL_FAILURE_MESSAGE
from agents._infrastructure.providers.rich_search import _json_request


class SearchPipelineTests(unittest.IsolatedAsyncioTestCase):
    def test_provider_json_transport_uses_direct_https_connection(self):
        calls = []

        class Response:
            status = 200
            reason = "OK"
            headers = {}

            @staticmethod
            def read(_limit):
                return b'{"Response":{"Pages":[]}}'

        class Connection:
            def request(self, method, target, *, body, headers):
                calls.append((method, target, json.loads(body), headers))

            @staticmethod
            def getresponse():
                return Response()

            @staticmethod
            def close():
                return None

        with patch(
            "agents._infrastructure.providers.rich_search.http.client.HTTPSConnection",
            return_value=Connection(),
        ) as connection_type:
            result = _json_request(
                "https://api.wsa.cloud.tencent.com/SearchPro",
                {"Query": "最近 AI 有什么新进展"},
                {"Authorization": "Bearer test"},
                10,
            )

        connection_type.assert_called_once_with(
            "api.wsa.cloud.tencent.com",
            port=None,
            timeout=10,
        )
        self.assertEqual(result, {"Response": {"Pages": []}})
        self.assertEqual(calls[0][0:2], ("POST", "/SearchPro"))
        self.assertEqual(calls[0][2], {"Query": "最近 AI 有什么新进展"})

    def test_rich_search_failure_never_claims_a_confirmation_card(self):
        content = tool_failure_fallback([
            HumanMessage(content="最近 AI 有什么新进展"),
            ToolMessage(
                content=json.dumps({"tool_error": {
                    "kind": "runtime",
                    "detail": TOOL_FAILURE_MESSAGE,
                    "retry_same_call": False,
                }}, ensure_ascii=False),
                name="rich_search",
                tool_call_id="rich-search-failed",
            ),
        ])
        self.assertIn("实时搜索这次没有完成", content)
        self.assertNotIn("确认卡", content)
        self.assertNotIn("工具", content)

    async def test_message_restore_keeps_rich_search_metadata(self):
        metadata = {"total": 1, "results": [{"title": "故宫", "url": "https://example.com"}], "media": []}
        messages = [
            {"type": "human", "content": "故宫历史", "id": "u1"},
            {"type": "tool", "content": json.dumps({"ui_action": "rich_search_results", "search_results": metadata})},
            {"type": "ai", "content": "## 故宫历史", "id": "a1"},
        ]
        langgraph_store = FakeStore()
        from agents._infrastructure.makers.data_version import namespace as data_namespace
        await langgraph_store.aput(
            data_namespace(
                "message_meta",
                scoped_conversation_id(
                    SimpleNamespace(),
                    TEST_USER_ID,
                    "restore-rich",
                ),
            ),
            "latest_extras",
            {
                "original_content": "## 故宫历史",
                "content": "## 故宫历史\n\n![太和殿](https://example.com/palace.jpg)",
                "follow_ups": ["太和殿是做什么的？"],
                "search_results": {**metadata, "media": [{"id": "media-1"}]},
            },
        )
        store = SimpleNamespace(
            langgraph_checkpointer=FakeCheckpointer(messages),
            langgraph_store=langgraph_store,
        )
        response = await messages_handler(authenticated_namespace(conversation_id="restore-rich", store=store))
        ai_message = next(item for item in response["messages"] if item["role"] == "ai")
        self.assertEqual(ai_message["searchResults"]["media"], [{"id": "media-1"}])
        self.assertIn("palace.jpg", ai_message["content"])
        self.assertEqual(ai_message["followUps"], ["太和殿是做什么的？"])
        self.assertNotIn("workspace_actions", response)

    def test_semantic_search_plan_requires_one_rich_search_first_step(self):
        self.assertEqual(required_tool_for_plan({"needs_web_search": True}), "rich_search")
        self.assertEqual(required_tool_for_plan({"needs_web_search": False}), "")

    def test_temporal_policy_is_derived_after_capability_planning(self):
        source = (
            AGENTS_ROOT
            / "_application"
            / "chat"
            / "turn_service.py"
        ).read_text(encoding="utf-8")
        planned = source.index("capability_plan, planner_timed_out = await plan_capabilities_bounded")
        strict_date = source.index('explicit_today = bool(capability_plan.get("strict_today_only"))')
        self.assertLess(planned, strict_date)

    async def test_rich_search_reuses_evidence_but_not_turn_response_state(self):
        store = FakeStore()
        metadata = {
            "query": "合并后的 AI 新闻查询", "results": [], "media": [], "images": [],
            "total": 0, "media_pending": False, "timings_ms": {"search": 1, "page_media": 0, "vision": 0, "total": 1},
        }
        provider = AsyncMock(return_value=metadata)
        with patch("agents._infrastructure.skills.builtin_operations.provider_rich_search", new=provider):
            tools = build_system_skill_tools(
                None, store=store, conversation_id="search-one",
                user_id=TEST_USER_ID, env={}, media_enabled=False,
                planned_search_query="合并后的 AI 新闻查询",
            )
            tool = next(item for item in tools if item.name == "rich_search")
            first = json.loads(await tool.ainvoke({"query": "第一次改写"}))
            second = json.loads(await tool.ainvoke({"query": "第二次改写"}))
            self.assertEqual(first["search_results"]["search_config"]["turn_tool_invocations"], 1)
            self.assertEqual(first["search_results"]["search_config"]["turn_provider_calls"], 1)
            self.assertEqual(second["search_results"]["search_config"]["turn_tool_invocations"], 2)
            self.assertEqual(second["search_results"]["search_config"]["turn_provider_calls"], 1)
            self.assertEqual(provider.await_count, 1)
            self.assertEqual(provider.await_args.args[1], "合并后的 AI 新闻查询")
            self.assertFalse(provider.await_args.kwargs["include_media"])
            self.assertEqual(provider.await_args.kwargs["result_limit"], 8)
            self.assertEqual(provider.await_args.kwargs["image_limit"], 8)
            self.assertTrue(provider.await_args.kwargs["parallel_queries"])

            next_turn_tools = build_system_skill_tools(
                None, store=store, conversation_id="search-two",
                user_id=TEST_USER_ID, env={}, media_enabled=False,
                planned_search_query="合并后的 AI 新闻查询",
            )
            next_tool = next(item for item in next_turn_tools if item.name == "rich_search")
            reused = json.loads(await next_tool.ainvoke({"query": "任意改写"}))
            self.assertEqual(provider.await_count, 1)
            self.assertEqual(reused["search_results"]["cache"], {
                "kind": "evidence_only",
                "hit": True,
                "coalesced": False,
                "ttl_seconds": 600,
                "answer_cached": False,
                "bypassed": False,
            })
            self.assertEqual(reused["search_results"]["search_config"]["turn_tool_invocations"], 1)
            self.assertEqual(reused["search_results"]["search_config"]["turn_provider_calls"], 0)

    async def test_rich_search_audit_matrix_never_duplicates_provider_calls(self):
        scenarios = [
            ("最近 AI 有什么新进展", "AI 行业最近进展；多个独立事件、日期、来源", "AI 新闻现场"),
            ("找三篇智能体论文", "智能体系统近期论文、作者、发表时间", "论文架构图"),
            ("推荐三里屯附近餐厅", "北京三里屯附近餐厅评价和营业信息", "三里屯餐厅"),
        ]
        for index, (_question, planned_query, image_query) in enumerate(scenarios):
            with self.subTest(question=_question):
                provider = AsyncMock(return_value={
                    "query": planned_query, "results": [], "media": [], "images": [],
                    "total": 0, "media_pending": False,
                })
                with patch("agents._infrastructure.skills.builtin_operations.provider_rich_search", new=provider):
                    tools = build_system_skill_tools(
                        None, store=FakeStore(), conversation_id=f"audit-{index}",
                        user_id=TEST_USER_ID, env={},
                        planned_search_query=planned_query, planned_image_query=image_query,
                    )
                    tool = next(item for item in tools if item.name == "rich_search")
                    await tool.ainvoke({"query": "模型第一次调用", "image_query": image_query})
                    audited = json.loads(await tool.ainvoke({"query": "模型重复调用", "image_query": image_query}))
                    config = audited["search_results"]["search_config"]
                    self.assertEqual(provider.await_count, 1)
                    self.assertEqual(config["turn_tool_invocations"], 2)
                    self.assertEqual(config["turn_provider_calls"], 1)

    async def test_search_use_case_tool_adapter_keeps_main_turn_local_dedupe(self):
        result = json.dumps({
            "ui_action": "rich_search_results",
            "search_results": {
                "query": "AI 近期重要进展",
                "results": [],
                "media": [],
                "total": 0,
                "search_config": {"turn_provider_calls": 1},
            },
            "evidence": "verified evidence",
        }, ensure_ascii=False)
        operation = AsyncMock(return_value=result)
        tools = build_system_skill_tools(
            None,
            store=FakeStore(),
            conversation_id="use-case-adapter",
            user_id=TEST_USER_ID,
            env={},
            media_enabled=False,
            rich_search_operation=operation,
        )
        tool = next(item for item in tools if item.name == "rich_search")

        await tool.ainvoke({"query": "planner query"})
        repeated = json.loads(await tool.ainvoke({"query": "rewritten query"}))

        self.assertEqual(operation.await_count, 1)
        self.assertEqual(
            repeated["search_results"]["search_config"]["turn_tool_invocations"],
            2,
        )

    def test_search_preferences_have_fast_balanced_defaults_and_public_state(self):
        state = empty_intelligence_state()
        self.assertEqual(state["search_preferences"], {
            "result_limit": 8,
            "image_limit": 8,
            "parallel_image_search": True,
        })
        self.assertEqual(public_intelligence_state(state)["search_preferences"], state["search_preferences"])

    def test_today_filter_requires_a_verifiable_matching_publication_date(self):
        results = [
            {"title": "今日北京新闻", "snippet": "7月16日发布", "date": "", "url": "https://example.com/1"},
            {"title": "旧闻", "snippet": "", "date": "2026-07-15", "url": "https://example.com/2"},
            {"title": "无日期", "snippet": "内容", "date": "", "url": "https://example.com/3"},
        ]
        kept, stats = _filter_for_target_date(results, "2026-07-16")
        self.assertEqual([item["url"] for item in kept], ["https://example.com/1"])
        self.assertEqual(stats, {"received": 3, "kept": 1, "undated": 1, "mismatched": 1})

    async def test_rich_search_merges_fact_and_visual_intent_into_one_provider_call(self):
        def request(*_args, **_kwargs):
            return {"Pages": []}

        with patch("agents._infrastructure.providers.rich_search._json_request", side_effect=request) as provider:
            result = await run_rich_search(
                {"WSA_API_KEY": "test"}, "factual query", "visual query", "basic",
            )
        self.assertEqual(result["total"], 0)
        self.assertIn("timings_ms", result)
        self.assertEqual(provider.call_count, 1)
        payload = provider.call_args.args[1]
        self.assertIn("visual query", payload["Query"])
        self.assertEqual(set(payload), {"Query"})
        self.assertEqual(result["search_config"]["provider_request_count"], 1)
        self.assertTrue(result["search_config"]["visual_query_merged"])
        self.assertTrue(result["search_config"]["parallel_image_search"])

    async def test_rich_search_retries_one_transient_transport_failure(self):
        with patch(
            "agents._infrastructure.providers.rich_search._json_request",
            side_effect=[TimeoutError("transient"), {"Pages": []}],
        ) as provider, patch(
            "agents._infrastructure.providers.rich_search.asyncio.sleep",
            new=AsyncMock(),
        ):
            result = await run_rich_search(
                {"WSA_API_KEY": "test"},
                "factual query",
                depth="basic",
            )

        self.assertEqual(provider.call_count, 2)
        self.assertEqual(
            result["search_config"]["provider_request_count"],
            2,
        )

    def test_rich_search_visual_review_timeout_is_hard_bounded(self):
        self.assertEqual(_vision_review_timeout({}), 7.0)
        self.assertEqual(_vision_review_timeout({"RICH_SEARCH_VISION_TIMEOUT_SECONDS": "999"}), 7.0)
        self.assertEqual(_vision_review_timeout({"RICH_SEARCH_VISION_TIMEOUT_SECONDS": "1"}), 2.0)
        self.assertEqual(_vision_review_timeout({"RICH_SEARCH_VISION_TIMEOUT_SECONDS": "4"}), 4.0)

    async def test_exact_repeat_reuses_only_search_evidence_across_turns(self):
        store = FakeStore()
        metadata = {
            "query": "AI 新闻", "results": [], "media": [], "images": [],
            "total": 0, "media_pending": False,
        }
        with patch(
            "agents._infrastructure.skills.builtin_operations.provider_rich_search",
            new=AsyncMock(return_value=metadata),
        ) as provider:
            for conversation_id in ("cache-turn-1", "cache-turn-2"):
                tools = build_system_skill_tools(
                    None,
                    store=store,
                    conversation_id=conversation_id,
                    user_id=TEST_USER_ID,
                    env={},
                    planned_search_query="AI 近期重要进展",
                    media_enabled=False,
                )
                tool = next(item for item in tools if item.name == "rich_search")
                await tool.ainvoke({"query": "模型本次生成的不同搜索措辞"})
        self.assertEqual(provider.await_count, 1)

