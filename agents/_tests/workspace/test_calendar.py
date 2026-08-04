from agents._tests.support.workspace_environment import *  # noqa: F401,F403
from agents._application.i18n import text
from agents.chat._graph import TOOL_FAILURE_MESSAGE


class CalendarWorkspaceTests(unittest.IsolatedAsyncioTestCase):
    async def test_single_plan_preserves_dependent_route_calendar_chain(self):
        model = StructuredPlannerModel(
            args={
                "needs_route": True,
                "needs_calendar_context": True,
                "needs_calendar_action": True,
                "route_stops": [
                    {"query": "北京站"},
                    {"query": "北京西站"},
                ],
                "prompt_topics": ["maps", "calendar"],
            },
        )
        plan, timed_out = await plan_capabilities_bounded(
            model,
            "一种没有固定短语的跨能力行程请求",
            timeout_seconds=2,
        )
        self.assertFalse(timed_out)
        self.assertTrue(plan["needs_route"])
        self.assertTrue(plan["needs_calendar_context"])
        self.assertTrue(plan["needs_calendar_action"])
        self.assertEqual(
            required_tools_for_plan(plan),
            ("plan_route_between_places", "propose_calendar_changes"),
        )

    def test_calendar_place_plan_looks_up_place_before_proposal(self):
        self.assertEqual(
            required_tools_for_plan({"needs_places": True, "needs_calendar_action": True}),
            ("search_places", "propose_calendar_changes"),
        )

    def test_schedule_collector_emits_deterministic_opportunities(self):
        now = 1_800_000_000
        schedules = [
            {"id": "a", "title": "会议", "start_time": now + 600, "duration_minutes": 60, "location": "国贸"},
            {"id": "b", "title": "晚餐", "start_time": now + 1800, "duration_minutes": 60, "location": "望京"},
        ]
        signals = collect_schedule_signals(schedules, now)
        self.assertEqual([item["type"] for item in signals].count("schedule_upcoming"), 2)
        self.assertEqual([item["type"] for item in signals].count("schedule_conflict"), 1)
        self.assertEqual(len({item["dedup_key"] for item in signals}), len(signals))

    def test_schedule_collector_detects_conflict_with_an_ongoing_event(self):
        now = 1_800_000_000
        schedules = [
            {"id": "ongoing", "title": "ongoing", "start_time": now - 600, "duration_minutes": 30},
            {"id": "next", "title": "next", "start_time": now + 300, "duration_minutes": 30},
        ]
        signals = collect_schedule_signals(schedules, now)
        self.assertEqual([item["type"] for item in signals].count("schedule_conflict"), 1)
        self.assertEqual([item["type"] for item in signals].count("schedule_upcoming"), 1)

    async def test_scheduled_tick_runs_without_chat_and_persists_inbox(self):
        store = FakeStore()
        now = 1_800_000_000
        workspace = empty_workspace()
        workspace["schedules"]["next"] = {
            "id": "next", "title": "参观故宫", "start_time": now + 3600,
            "duration_minutes": 120, "location": "故宫", "done": False,
        }
        await save_workspace(store, TEST_USER_ID, workspace)
        state, stats = await run_proactive_tick(
            store, now, user_id=TEST_USER_ID,
        )
        repeated, repeated_stats = await run_proactive_tick(
            store, now + 60, user_id=TEST_USER_ID,
        )
        self.assertEqual(stats["notifications_created"], 1)
        self.assertEqual(repeated_stats["notifications_created"], 0)
        public = public_proactive_state(repeated, now)
        self.assertEqual(public["notifications"][0]["title"], "即将开始")
        self.assertEqual(public["checkpoints"]["schedule_collector"]["schedule_count"], 1)

    async def test_calendar_change_immediately_refreshes_proactive_notifications(self):
        store = FakeStore()
        start = int(time.time()) + 3600
        response = await handler(FakeContext(store, {
            "operation": "direct_calendar_changes",
            "changes": [{
                "operation": "create",
                "event": {"title": "即将参观故宫", "start_time": start, "duration_minutes": 60, "place": PLACE},
            }],
        }))
        self.assertEqual(len(response["schedules"]), 1)
        proactive = public_proactive_state(await load_proactive_state(store, TEST_USER_ID))
        self.assertTrue(any(item["type"] == "schedule_upcoming" for item in proactive["notifications"]))

    async def test_calendar_changes_preserve_the_active_verified_map(self):
        store = FakeStore()
        state = empty_workspace()
        map_action = new_action(
            "map_recommendation",
            {
                "title": "已核实公共交通路线",
                "places": [PLACE],
                "route": {"provider": "tencent", "mode": "transit"},
                "show_route": True,
            },
            requires_confirmation=False,
        )
        put_action(state, map_action)
        state["active_map_action_id"] = map_action["id"]
        await save_workspace(store, TEST_USER_ID, state)

        start = int(time.time()) + 7200
        direct = await handler(FakeContext(store, {
            "operation": "direct_calendar_changes",
            "changes": [{"operation": "create", "event": {
                "title": "直接新增",
                "start_time": start,
                "duration_minutes": 30,
                "place": PLACE,
            }}],
        }))
        self.assertEqual(direct["map"]["route"]["mode"], "transit")

        restored = await load_user_workspace(store, user_id=TEST_USER_ID)
        calendar_action = new_action(
            "calendar_changes",
            {"changes": [{"operation": "create", "event": {
                "title": "确认新增",
                "start_time": start + 7200,
                "duration_minutes": 30,
                "place": PLACE,
            }}]},
            requires_confirmation=True,
        )
        put_action(restored, calendar_action)
        await save_workspace(store, TEST_USER_ID, restored)
        confirmed = await handler(FakeContext(store, {
            "operation": "confirm_action",
            "action_id": calendar_action["id"],
            "version": calendar_action["version"],
        }))
        self.assertEqual(confirmed["map"]["route"]["mode"], "transit")
        final = await load_user_workspace(store, user_id=TEST_USER_ID)
        self.assertEqual(final["active_map_action_id"], map_action["id"])

    def test_schedule_location_must_be_verified(self):
        with self.assertRaises(ValueError):
            normalize_schedule({"title": "参观", "start_time": 1, "place": {"name": "幻觉地点"}})
        event = normalize_schedule({"title": "参观", "start_time": 1, "place": PLACE})
        self.assertEqual(event["extra"]["place"]["place_id"], "poi-1")

    def test_calendar_create_update_delete(self):
        state = empty_workspace()
        created = apply_calendar_changes(state, [{
            "operation": "create",
            "event": {"title": "参观", "start_time": 100, "duration_minutes": 90, "place": PLACE},
        }])[0]
        updated = apply_calendar_changes(state, [{
            "operation": "update", "schedule_id": created["id"], "event": {"title": "参观故宫"},
        }])[0]
        self.assertEqual(updated["title"], "参观故宫")
        removed = apply_calendar_changes(state, [{"operation": "delete", "schedule_id": created["id"]}])[0]
        self.assertTrue(removed["deleted"])
        self.assertFalse(state["schedules"])

    def test_calendar_delete_does_not_duplicate_untouched_schedules(self):
        state = empty_workspace()
        palace, restaurant, lake = apply_calendar_changes(state, [
            {"operation": "create", "event": {"title": "故宫", "start_time": 1_900_000_000}},
            {"operation": "create", "event": {"title": "四季民福", "start_time": 1_900_007_200}},
            {"operation": "create", "event": {"title": "什刹海", "start_time": 1_900_014_400}},
        ])
        changed = apply_calendar_changes(state, [
            {"operation": "delete", "schedule_id": palace["id"]},
            {"operation": "create", "event": {
                "title": restaurant["title"],
                "start_time": restaurant["start_time"],
                "duration_minutes": restaurant["duration_minutes"],
            }},
            {"operation": "create", "event": {
                "title": lake["title"],
                "start_time": lake["start_time"],
                "duration_minutes": lake["duration_minutes"],
            }},
        ])
        self.assertEqual([item["title"] for item in changed], ["故宫"])
        self.assertEqual(
            sorted(item["title"] for item in state["schedules"].values()),
            ["什刹海", "四季民福"],
        )

    def test_calendar_mutation_repairs_exact_legacy_duplicates(self):
        state = empty_workspace()
        lake = apply_calendar_changes(state, [{
            "operation": "create",
            "event": {"title": "什刹海", "start_time": 1_900_014_400},
        }])[0]
        duplicate = dict(lake)
        duplicate["id"] = "legacy-duplicate"
        duplicate["created_at"] = lake["created_at"] + 1
        state["schedules"][duplicate["id"]] = duplicate
        apply_calendar_changes(state, [{
            "operation": "create",
            "event": {"title": "午餐", "start_time": 1_900_021_600},
        }])
        self.assertEqual(
            [item["title"] for item in state["schedules"].values()].count("什刹海"),
            1,
        )

    def test_calendar_mutations_before_beijing_today_are_rejected(self):
        state = empty_workspace()
        past = apply_calendar_changes(state, [{
            "operation": "create",
            "event": {"title": "历史日程", "start_time": 1_700_000_000, "place": PLACE},
        }])[0]
        now = 1_800_000_000
        with self.assertRaisesRegex(ValueError, "只供查看"):
            validate_calendar_change_window(
                state, [{"operation": "delete", "schedule_id": past["id"]}], now=now,
            )
        with self.assertRaisesRegex(ValueError, "今天之前"):
            validate_calendar_change_window(
                state, [{"operation": "create", "event": {"title": "补录", "start_time": 1_700_000_000}}],
                now=now,
            )

    def test_calendar_change_preview_reports_overlap(self):
        state = empty_workspace()
        existing = apply_calendar_changes(state, [{
            "operation": "create",
            "event": {"title": "已有会议", "start_time": 1_900_000_000, "duration_minutes": 60},
        }])[0]
        warnings = calendar_change_warnings(state, [{
            "operation": "create",
            "event": {"title": "冲突会议", "start_time": existing["start_time"] + 1800, "duration_minutes": 60},
        }])
        self.assertEqual(warnings, ["“已有会议”与“冲突会议”时间重叠"])

    def test_meeting_proposal_preserves_missing_times_for_structured_ui(self):
        payload = meeting_action_payload(empty_workspace(), "产品讨论", "", "")
        self.assertEqual(payload["subject"], "产品讨论")
        self.assertEqual(payload["missing_fields"], ["start_time", "end_time"])
        self.assertEqual(payload["validation_errors"], [])

    async def test_meeting_proposal_can_be_edited_and_rechecks_conflicts(self):
        store = FakeStore()
        state = empty_workspace()
        apply_calendar_changes(state, [{
            "operation": "create",
            "event": {"title": "已有日程", "start_time": 4_088_368_800, "duration_minutes": 60},
        }])
        action = new_action(
            "meeting_create",
            meeting_action_payload(state, "联调会", "", ""),
            requires_confirmation=True,
        )
        put_action(state, action)
        await save_workspace(store, TEST_USER_ID, state)

        updated = await handler(FakeContext(store, {
            "operation": "update_meeting_action",
            "action_id": action["id"],
            "version": action["version"],
            "subject": "联调会（修改）",
            "start_time": "2099-07-22T10:30:00+08:00",
            "end_time": "2099-07-22T11:30:00+08:00",
        }))

        edited = updated["action"]
        self.assertEqual(edited["version"], 2)
        self.assertEqual(edited["payload"]["missing_fields"], [])
        self.assertIn("时间重叠", edited["payload"]["warnings"][0])
        verify_action_snapshot((await load_workspace(store, TEST_USER_ID))["actions"][action["id"]])

    def test_calendar_context_exposes_current_user_schedule_ids_and_beijing_time(self):
        state = empty_workspace()
        state["schedules"]["cal-live"] = {
            "id": "cal-live", "title": "游览寒山寺", "start_time": 1784156400,
            "duration_minutes": 60, "location": "苏州市姑苏区",
        }
        context = json.loads(calendar_context(state))
        self.assertEqual(context[0]["id"], "cal-live")
        self.assertIn("+08:00", context[0]["start_time"])

    async def test_calendar_tool_accepts_flat_model_wire_shape(self):
        store = FakeStore()
        state = empty_workspace()
        state["place_candidates"][PLACE["place_id"]] = PLACE
        await save_workspace(store, TEST_USER_ID, state)
        tools = build_system_skill_tools(
            None, store=store, conversation_id="c-flat",
            user_id=TEST_USER_ID, env={},
        )
        calendar_tool = next(tool for tool in tools if tool.name == "propose_calendar_changes")
        result = json.loads(await calendar_tool.ainvoke({
            "summary": "北海公园行程",
            "changes": [{
                "operation": "create",
                "title": "游览北海公园",
                "start_time": "2099-07-16T09:00:00+08:00",
                "end_time": "2099-07-16T10:00:00+08:00",
                "place_id": PLACE["place_id"],
            }],
        }))
        self.assertEqual(result["ui_action"], "calendar_action")
        event = result["action"]["payload"]["changes"][0]["event"]
        self.assertEqual(event["title"], "游览北海公园")
        self.assertEqual(event["place"]["place_id"], PLACE["place_id"])

    async def test_calendar_tool_reuses_unique_verified_location_from_prior_route(self):
        store = FakeStore()
        state = empty_workspace()
        state["place_candidates"][PLACE["place_id"]] = PLACE
        await save_workspace(store, TEST_USER_ID, state)
        tools = build_system_skill_tools(
            None, store=store, conversation_id="calendar-route",
            user_id=TEST_USER_ID, env={},
        )
        calendar_tool = next(tool for tool in tools if tool.name == "propose_calendar_changes")
        result = json.loads(await calendar_tool.ainvoke({
            "summary": "沿用上一轮核实地点",
            "changes": [{
                "operation": "create",
                "event": {
                    "title": "前往北海公园",
                    "start_time": "2099-07-16T09:00:00+08:00",
                    "end_time": "2099-07-16T10:00:00+08:00",
                    "location": f"{PLACE['name']}（{PLACE['address']}）",
                },
            }],
        }))
        event = result["action"]["payload"]["changes"][0]["event"]
        self.assertEqual(event["place"]["place_id"], PLACE["place_id"])

    async def test_calendar_tool_skips_missing_target_without_creating_replacement(self):
        store = FakeStore()
        state = empty_workspace()
        existing = apply_calendar_changes(state, [{
            "operation": "create",
            "event": {
                "title": "真实存在",
                "start_time": 2_000_000_000,
                "duration_minutes": 60,
            },
        }])[0]
        await save_workspace(store, TEST_USER_ID, state)
        tools = build_system_skill_tools(
            None, store=store, conversation_id="calendar-partial",
            user_id=TEST_USER_ID, env={},
        )
        calendar_tool = next(
            tool for tool in tools if tool.name == "propose_calendar_changes"
        )
        result = json.loads(await calendar_tool.ainvoke({
            "summary": "尽力修改",
            "changes": [
                {
                    "operation": "update",
                    "schedule_id": existing["id"],
                    "event": {"title": "真实存在（已修改）"},
                },
                {
                    "operation": "delete",
                    "schedule_id": "does-not-exist",
                },
            ],
        }))
        self.assertEqual(result["ui_action"], "calendar_action")
        payload = result["action"]["payload"]
        self.assertEqual(len(payload["changes"]), 1)
        self.assertEqual(payload["changes"][0]["operation"], "update")
        self.assertEqual(payload["skipped_changes"][0]["operation"], "delete")
        self.assertEqual(payload["calendar_snapshot"]["schedule_count"], 1)

    async def test_calendar_tool_reports_all_missing_targets_without_action(self):
        tools = build_system_skill_tools(
            None, store=FakeStore(), conversation_id="calendar-missing",
            user_id=TEST_USER_ID, env={},
        )
        calendar_tool = next(
            tool for tool in tools if tool.name == "propose_calendar_changes"
        )
        result = json.loads(await calendar_tool.ainvoke({
            "summary": "删除不存在的日程",
            "changes": [{
                "operation": "delete",
                "schedule_id": "does-not-exist",
            }],
        }))
        self.assertEqual(result["ui_action"], "calendar_change_report")
        self.assertEqual(result["applied_count"], 0)
        self.assertEqual(result["skipped_changes"][0]["operation"], "delete")
        self.assertNotIn("action", result)

    async def test_calendar_online_location_uses_model_protocol_enum(self):
        store = FakeStore()
        await save_workspace(store, TEST_USER_ID, empty_workspace())
        tools = build_system_skill_tools(
            None,
            store=store,
            conversation_id="calendar-online",
            user_id=TEST_USER_ID,
            env={},
            enabled_skills={"calendar"},
        )
        calendar_tool = next(tool for tool in tools if tool.name == "propose_calendar_changes")
        result = json.loads(await calendar_tool.ainvoke({
            "summary": "远程评审",
            "changes": [{
                "operation": "create",
                "event": {
                    "title": "远程评审",
                    "start_time": "2099-07-16T09:00:00+08:00",
                    "end_time": "2099-07-16T10:00:00+08:00",
                    "location": "https://meeting.example/join/123",
                    "location_kind": "online",
                },
            }],
        }))
        event = result["action"]["payload"]["changes"][0]["event"]
        self.assertEqual(event["location_kind"], "online")
        self.assertEqual(event["location"], "https://meeting.example/join/123")
        self.assertNotIn("place", event)

    async def test_calendar_tool_resolves_explicit_location_when_planner_omits_place_step(self):
        store = FakeStore()
        await save_workspace(store, TEST_USER_ID, empty_workspace())
        tools = build_system_skill_tools(
            None,
            store=store,
            conversation_id="calendar-location-fallback",
            user_id=TEST_USER_ID,
            env={"TENCENT_MAP_SERVER_KEY": "test-key"},
            enabled_skills={"calendar", "maps"},
        )
        calendar_tool = next(tool for tool in tools if tool.name == "propose_calendar_changes")
        verified_place = {
            **PLACE,
            "place_id": "tiananmen-1",
            "name": "天安门",
            "address": "北京市东城区东长安街",
        }
        with patch(
            "agents._infrastructure.skills.builtin_operations.provider_search_places",
            AsyncMock(return_value=[verified_place]),
        ) as provider:
            result = json.loads(await calendar_tool.ainvoke({
                "summary": "7月26日早8点去天安门",
                "changes": [{
                    "operation": "create",
                    "event": {
                        "title": "前往天安门",
                        "start_time": "2099-07-26T08:00:00+08:00",
                        "location": "北京天安门",
                    },
                }],
            }))
        self.assertEqual(result["ui_action"], "calendar_action")
        event = result["action"]["payload"]["changes"][0]["event"]
        self.assertEqual(event["place"]["place_id"], "tiananmen-1")
        provider.assert_awaited_once()

    async def test_calendar_tool_updates_end_time_without_requiring_start_time_again(self):
        store = FakeStore()
        state = empty_workspace()
        created = apply_calendar_changes(state, [{
            "operation": "create",
            "event": {"title": "评审", "start_time": 1_800_000_000, "duration_minutes": 60, "place": PLACE},
        }])[0]
        await save_workspace(store, TEST_USER_ID, state)
        tools = build_system_skill_tools(
            None, store=store, conversation_id="calendar-end",
            user_id=TEST_USER_ID, env={},
        )
        calendar_tool = next(tool for tool in tools if tool.name == "propose_calendar_changes")
        end_iso = "2027-01-15T17:40:00+08:00"
        result = json.loads(await calendar_tool.ainvoke({
            "summary": "延长评审",
            "changes": [{"operation": "update", "schedule_id": created["id"], "event": {"end_time": end_iso}}],
        }))
        event = result["action"]["payload"]["changes"][0]["event"]
        self.assertGreater(event["duration_minutes"], 60)

    async def test_calendar_edit_refreshes_and_delete_retires_proactive_reminder(self):
        store = FakeStore()
        start = int(time.time()) + 3600
        created_response = await handler(FakeContext(store, {
            "operation": "direct_calendar_changes",
            "changes": [{"operation": "create", "event": {
                "title": "旧标题", "start_time": start, "duration_minutes": 60, "place": PLACE,
            }}],
        }))
        schedule_id = created_response["schedules"][0]["id"]
        await handler(FakeContext(store, {
            "operation": "direct_calendar_changes",
            "changes": [{"operation": "update", "schedule_id": schedule_id, "event": {"title": "新标题"}}],
        }))
        proactive = public_proactive_state(await load_proactive_state(store, TEST_USER_ID))
        upcoming = [item for item in proactive["notifications"] if item["type"] == "schedule_upcoming"]
        self.assertEqual(len(upcoming), 1)
        self.assertIn("新标题", upcoming[0]["body"])

        await handler(FakeContext(store, {
            "operation": "direct_calendar_changes",
            "changes": [{"operation": "delete", "schedule_id": schedule_id}],
        }))
        proactive = public_proactive_state(await load_proactive_state(store, TEST_USER_ID))
        self.assertFalse(any(item["type"] == "schedule_upcoming" for item in proactive["notifications"]))

    def test_failed_calendar_tool_never_claims_confirmation_card_exists(self):
        failed = ToolMessage(
            content=json.dumps({"tool_error": {
                "kind": "validation",
                "detail": "地点 ID 未通过本轮地点搜索验证",
                "retry_same_call": False,
            }}, ensure_ascii=False),
            name="propose_calendar_changes",
            tool_call_id="calendar-failed",
        )
        self.assertEqual(action_completion_fallback([failed]), "")
        self.assertIn("没有生成确认卡", tool_failure_fallback([failed]))

        runtime_failed = ToolMessage(
            content=json.dumps({"tool_error": {
                "kind": "runtime",
                "detail": TOOL_FAILURE_MESSAGE,
                "retry_same_call": False,
            }}, ensure_ascii=False),
            name="propose_calendar_changes",
            tool_call_id="calendar-runtime-failed",
        )
        public_copy = tool_failure_fallback([runtime_failed])
        self.assertEqual(public_copy, text("chat.fallback.required_failed", "zh-CN"))
        self.assertNotIn("不要重复调用", public_copy)
        self.assertNotIn("请基于", public_copy)

    def test_optional_meeting_tool_is_hidden_until_personal_token_exists(self):
        hidden = build_system_skill_tools(
            None, store=FakeStore(), conversation_id="meeting",
            user_id=TEST_USER_ID, env={},
        )
        self.assertNotIn("propose_meeting", {tool.name for tool in hidden})
        personal = build_system_skill_tools(
            None, store=FakeStore(), conversation_id="meeting",
            user_id=TEST_USER_ID,
            env={"TENCENT_MEETING_TOKEN": "personal-token"},
        )
        self.assertIn("propose_meeting", {tool.name for tool in personal})

    def test_personal_tencent_meeting_skill_uses_official_mcp_transport(self):
        payload = {
            "jsonrpc": "2.0", "id": "1", "result": {"content": [{"type": "text", "text": json.dumps({
                "meeting_id": "meeting-1", "meeting_code": "123456789", "join_url": "https://meeting.tencent.com/dm/example",
            })}]},
        }

        class Response:
            headers = {"X-Tc-Trace": "trace-meeting-1"}
            def __enter__(self): return self
            def __exit__(self, *_args): return None
            def read(self, _limit): return json.dumps(payload).encode("utf-8")

        with patch("agents._infrastructure.providers.side_effects.urllib.request.urlopen", return_value=Response()) as opened:
            result = _post_tencent_meeting_mcp(
                {"TENCENT_MEETING_TOKEN": "secret"}, "产品周会",
                "2026-07-21T15:00:00+08:00", "2026-07-21T16:00:00+08:00",
            )
        self.assertTrue(result["ok"])
        self.assertEqual(result["meeting_code"], "123456789")
        self.assertEqual(result["trace_id"], "trace-meeting-1")
        request = opened.call_args.args[0]
        self.assertEqual(request.headers["X-tencent-meeting-token"], "secret")
        self.assertEqual(json.loads(request.data)["params"]["name"], "schedule_meeting")

    def test_tencent_meeting_accepts_human_readable_mcp_success_content(self):
        payload = {
            "jsonrpc": "2.0",
            "id": "1",
            "result": {
                "content": [{
                    "type": "text",
                    "text": (
                        "会议创建成功。会议号：123 456 789，"
                        "入会链接：https://meeting.tencent.com/dm/example"
                    ),
                }],
            },
        }

        class Response:
            headers = {}
            def __enter__(self): return self
            def __exit__(self, *_args): return None
            def read(self, _limit): return json.dumps(payload).encode("utf-8")

        with patch("agents._infrastructure.providers.side_effects.urllib.request.urlopen", return_value=Response()):
            result = _post_tencent_meeting_mcp(
                {"TENCENT_MEETING_TOKEN": "secret"}, "产品周会",
                "2026-07-21T15:00:00+08:00", "2026-07-21T16:00:00+08:00",
            )
        self.assertTrue(result["ok"])
        self.assertEqual(result["meeting_code"], "123456789")
        self.assertEqual(result["join_url"], "https://meeting.tencent.com/dm/example")

    async def test_successful_tencent_meeting_is_written_to_calendar_once(self):
        store = FakeStore()
        state = empty_workspace()
        action = new_action("meeting_create", {
            "subject": "联调会议",
            "start_time": "2099-07-22T10:00:00+08:00",
            "end_time": "2099-07-22T10:15:00+08:00",
        }, requires_confirmation=True)
        put_action(state, action)
        await save_workspace(store, TEST_USER_ID, state)
        result = {
            "ok": True, "subject": "联调会议", "meeting_id": "meeting-1",
            "meeting_code": "123456789", "join_url": "https://meeting.tencent.com/dm/example",
        }
        body = {"operation": "confirm_action", "action_id": action["id"], "version": action["version"]}
        with patch("agents._controllers.workspace_controller.create_tencent_meeting", AsyncMock(return_value=result)) as provider:
            first = await handler(FakeContext(store, body))
            second = await handler(FakeContext(store, {
                "operation": "confirm_action", "action_id": action["id"], "version": first["action"]["version"],
            }))
        self.assertEqual(provider.await_count, 1)
        self.assertEqual(len(first["schedules"]), 1)
        self.assertEqual(len(second["schedules"]), 1)
        schedule = first["schedules"][0]
        self.assertEqual(schedule["category"], "meeting")
        self.assertEqual(schedule["extra"]["meeting_id"], "meeting-1")
        self.assertEqual(first["action"]["result"]["schedule_id"], schedule["id"])

