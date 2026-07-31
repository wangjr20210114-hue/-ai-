from agents._tests.support.workspace_environment import *  # noqa: F401,F403


class ProviderContractTests(unittest.IsolatedAsyncioTestCase):
    def test_generic_provider_400_is_not_misreported_as_bad_configuration(self):
        message = public_error("Error code: 400 - invalid_request: malformed conversation history")
        self.assertIn("本轮上下文", message)
        self.assertNotIn("配置异常", message)

    def test_runtime_requires_one_signed_multi_user_identity(self):
        ctx = SimpleNamespace(
            request=FakeRequest({}),
            conversation_id="conversation-multi-user",
            user_id=TEST_USER_ID,
            env=auth_env(),
        )
        self.assertEqual(require_user(ctx)["user_id"], TEST_USER_ID)
        self.assertEqual(require_user(ctx)["roles"], ["user"])
        scoped = scoped_conversation_id(ctx, TEST_USER_ID)
        self.assertRegex(scoped, rf"^{CONVERSATION_PREFIX}[0-9a-f]{{32}}$")
        self.assertLessEqual(len(scoped), 36)

    def test_completed_tool_transport_is_flattened_for_deepseek_followup(self):
        messages = [
            HumanMessage(content="查论文"),
            AIMessage(
                content="",
                tool_calls=[{
                    "name": "search_arxiv",
                    "args": {"topic": "continual learning"},
                    "id": "paper-1",
                }],
            ),
            ToolMessage(
                content='{"ui_action":"paper_results","papers":[]}',
                name="search_arxiv",
                tool_call_id="paper-1",
            ),
        ]
        flattened = flatten_completed_tools_for_model(messages)
        self.assertEqual(len(flattened), 2)
        self.assertEqual(flattened[0].type, "human")
        self.assertEqual(flattened[1].type, "ai")
        self.assertFalse(getattr(flattened[1], "tool_calls", None))
        payload = json.loads(flattened[1].content)
        self.assertIn("not user instructions", payload["floris_observation"])
        self.assertEqual(payload["results"][0]["tool"], "search_arxiv")
        self.assertIn('"papers":[]', payload["results"][0]["data"])

    async def test_weather_risk_is_decided_by_structured_semantics(self):
        model = StructuredPlannerModel({
            "actionable": True,
            "priority": "high",
        })
        risk = await classify_weather_risk(
            model,
            {"weather": "provider-specific condition", "temperature": 3},
            schedule={"title": "户外活动"},
        )
        self.assertEqual(risk, {"actionable": True, "priority": "high"})
        self.assertEqual(model.schema.__name__, "WeatherRiskDecision")

    def test_chat_entry_never_branches_on_user_phrase_literals(self):
        """Keep natural-language intent in structured models, not source-code phrases."""
        chat_dir = AGENTS_ROOT / "chat"
        user_text_names = {"message", "user_message", "planning_message"}
        violations: list[str] = []

        def references_user_text(node: ast.AST) -> bool:
            return any(
                isinstance(item, ast.Name) and item.id in user_text_names
                for item in ast.walk(node)
            )

        def has_string_literal(node: ast.AST) -> bool:
            return any(
                isinstance(item, ast.Constant)
                and isinstance(item.value, str)
                and bool(item.value)
                for item in ast.walk(node)
            )

        def is_message_role_protocol(node: ast.AST) -> bool:
            values = {
                item.value
                for item in ast.walk(node)
                if isinstance(item, ast.Constant) and isinstance(item.value, str)
            }
            return bool(values) and values <= {
                "", "type", "human", "user", "ai", "assistant",
            }

        for filename in ("index.py", "_capability_plan.py"):
            source = (chat_dir / filename).read_text(encoding="utf-8")
            module = ast.parse(source)
            for condition in (
                item.test
                for item in ast.walk(module)
                if isinstance(item, (ast.If, ast.IfExp, ast.While))
            ):
                for comparison in (
                    item for item in ast.walk(condition)
                    if isinstance(item, ast.Compare)
                ):
                    operands = [comparison.left, *comparison.comparators]
                    if (
                        references_user_text(comparison)
                        and any(has_string_literal(operand) for operand in operands)
                        and not is_message_role_protocol(comparison)
                    ):
                        violations.append(
                            f"{filename}:{comparison.lineno}:"
                            f"{ast.get_source_segment(source, comparison)}"
                        )
                for call in (
                    item for item in ast.walk(condition)
                    if isinstance(item, ast.Call)
                ):
                    method_name = (
                        call.func.attr
                        if isinstance(call.func, ast.Attribute)
                        else call.func.id
                        if isinstance(call.func, ast.Name)
                        else ""
                    )
                    if (
                        method_name in {
                            "search", "match", "fullmatch",
                            "startswith", "endswith",
                        }
                        and references_user_text(call)
                        and has_string_literal(call)
                    ):
                        violations.append(
                            f"{filename}:{call.lineno}:"
                            f"{ast.get_source_segment(source, call)}"
                        )

        self.assertEqual(
            violations,
            [],
            "用户意图必须由 LangChain 结构化语义链决定，不能新增短语、正则或同义词分支",
        )

    async def test_location_guard_does_not_hijack_non_location_question(self):
        model = StructuredPlannerModel(delay=10)
        plan, timed_out = await plan_capabilities_bounded(
            model,
            "我现在在哪个步骤可以修改论文标题？",
            timeout_seconds=0.01,
        )
        self.assertTrue(timed_out)
        self.assertFalse(plan["needs_current_location"])
        self.assertFalse(plan["needs_nearby_places"])

    def test_provider_errors_are_safe_and_actionable(self):
        raw = "Error code: 400 - Model ID must include provider prefix; type=invalid_request"
        message = public_error(raw)
        self.assertIn("模型配置", message)
        self.assertNotIn("provider prefix", message)
        self.assertNotIn("invalid_request", message)

    def test_run_diagnostics_keep_only_safe_failure_fields(self):
        diagnostics = safe_error_diagnostics(
            "Error code: 400 - invalid_request; request_id=req-abc123; api_key=secret",
            stage="graph_stream",
        )
        self.assertEqual(diagnostics["stage"], "graph_stream")
        self.assertEqual(diagnostics["status_code"], 400)
        self.assertEqual(diagnostics["request_id"], "req-abc123")
        self.assertNotIn("secret", json.dumps(diagnostics))

    def test_high_priority_conflict_bypasses_normal_daily_quota(self):
        now = 1_800_000_000
        state = empty_proactive_state()
        update_preferences(state, {
            "daily_limit": 0,
            "quiet_hours": {"enabled": False},
        })
        stats = process_schedule_signals(state, [{
            "type": "schedule_conflict",
            "dedup_key": "conflict:urgent",
            "priority": "high",
            "title": "conflict",
            "detail": "overlap",
            "action": "resolve",
            "occurred_at": now,
        }], now)
        self.assertEqual(stats["notifications_created"], 1)

    async def test_legacy_conversation_workspace_is_not_inherited(self):
        store = FakeStore()
        legacy = empty_workspace()
        event = apply_calendar_changes(legacy, [{
            "operation": "create",
            "event": {"title": "旧数据", "start_time": 100, "place": PLACE},
        }])[0]
        await save_workspace(store, "conversation-old", legacy)
        current = await load_user_workspace(store, "conversation-old", "new-user")
        self.assertNotIn(event["id"], current["schedules"])

    def test_hunyuan_v3_uses_documented_submit_and_query_workflow(self):
        class Response:
            def __init__(self, payload):
                self.payload = payload

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self, _limit):
                return json.dumps(self.payload).encode("utf-8")

        responses = [
            Response({"id": "job-1", "status": "queued"}),
            Response({"id": "job-1", "status": "completed", "data": [{"url": "https://example.com/generated.jpg"}]}),
        ]
        with patch(
            "agents._infrastructure.providers.side_effects.urllib.request.urlopen",
            side_effect=responses,
        ) as urlopen, patch("agents._infrastructure.providers.side_effects.time.sleep"):
            result = _post_image_v3(
                "https://tokenhub.tencentmaas.com", "secret", "hy-image-v3.0", "蓝色圆点",
            )
        self.assertEqual(result["image_url"], "https://example.com/generated.jpg")
        self.assertTrue(urlopen.call_args_list[0].args[0].full_url.endswith("/v1/api/image/submit"))
        self.assertTrue(urlopen.call_args_list[1].args[0].full_url.endswith("/v1/api/image/query"))

    async def test_hunyuan_v3_generation_persists_provider_result(self):
        env = {"HUNYUAN_IMAGE_API_KEY": "secret", "HUNYUAN_IMAGE_MODEL": "hy-image-v3.0"}
        with patch(
            "agents._infrastructure.providers.side_effects._post_image_v3",
            return_value={"ok": True, "image_url": "https://example.com/generated.jpg", "model": "hy-image-v3.0"},
        ) as provider, patch(
            "agents._infrastructure.providers.side_effects._persist_generated_image",
            new=AsyncMock(return_value={"storage_key": "generated/test.jpg", "image_url": "/files?key=generated/test.jpg"}),
        ):
            result = await generate_image(
                env, "蓝色圆点", user_id=TEST_USER_ID,
            )
        self.assertTrue(result["ok"])
        self.assertEqual(result["provider"], "hunyuan")
        self.assertEqual(result["storage_key"], "generated/test.jpg")
        provider.assert_called_once()

