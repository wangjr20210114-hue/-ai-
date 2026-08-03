from agents._tests.support.workspace_environment import *  # noqa: F401,F403


class ProactiveMemoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_capability_planner_receives_filtered_memory_context(self):
        model = StructuredPlannerModel({"needs_web_search": False})
        await plan_capabilities(model, "帮我规划旅行", "- preference.travel: 喜欢安静的博物馆")
        system_prompt = model.messages[0]["content"]
        self.assertIn("喜欢安静的博物馆", system_prompt)
        self.assertIn("不得把姓名、联系方式", system_prompt)

    def test_memory_refresh_queues_behind_existing_fcfs_window(self):
        now = 1_800_000_000
        state = empty_proactive_state()
        update_preferences(state, {
            "daily_limit": 50,
            "window_limit": 4,
            "quiet_hours": {"enabled": False},
        })
        operation_signals = [{
            "type": "schedule_upcoming",
            "dedup_key": f"operation:{index}",
            "title": f"操作{index}",
            "detail": "操作提醒",
            "action": "处理",
            "occurred_at": now,
        } for index in range(4)]
        process_schedule_signals(state, operation_signals, now)
        for index in range(5):
            stats = process_schedule_signals(state, [{
                "type": "memory_context_reminder",
                "source": "memory_window",
                "window_policy": "memory_refresh",
                "dedup_key": f"memory:{index}",
                "title": f"记忆{index}",
                "detail": "记忆推导",
                "action": "继续",
                "occurred_at": now + index + 1,
            }], now + index + 1)
        public = public_proactive_state(state, now + 20)
        self.assertEqual(len(public["notifications"]), 4)
        self.assertTrue(all(item["window_origin"] == "operation" for item in public["notifications"]))
        self.assertEqual(stats["notifications_created"], 1)
        self.assertEqual(stats["window_queued"], 1)
        self.assertEqual(stats["skipped"], 0)

    async def test_memory_reminder_requires_safe_memory_and_returns_one_bounded_signal(self):
        model = AsyncMock()
        model.ainvoke.return_value = SimpleNamespace(content=json.dumps({
            "should_remind": True,
            "title": "带上雨具",
            "detail": "你常在下班后散步，海淀今天有雷阵雨，出门记得带伞。",
            "action": "需要我结合今天的日程看看什么时候出门更合适吗？",
            "priority": "normal",
        }, ensure_ascii=False))
        intelligence = empty_intelligence_state()
        self.assertIsNone(await infer_memory_reminder(
            model, intelligence, location_context={}, existing_reminders=[], now=1_800_000_000,
        ))
        apply_automatic_memory_candidates(
            intelligence,
            [{"key": "habit.walk", "value": "经常下班后散步", "confidence": 0.9, "ttl_days": 90}],
            now=1_800_000_000,
        )
        signal = await infer_memory_reminder(
            model,
            intelligence,
            location_context={"district": "海淀区", "weather": "雷阵雨", "expires_at": 1_900_000_000},
            existing_reminders=[],
            now=1_800_000_000,
        )
        self.assertEqual(signal["window_policy"], "memory_refresh")
        self.assertEqual(signal["title"], "带上雨具")
        self.assertEqual(signal["evidence"], {"basis": "safe_memory", "location_used": True})

    def test_memory_requires_confirmation_and_is_injected_only_after_confirmation(self):
        state = empty_intelligence_state()
        proposal = propose_memory(state, "travel.seat", "靠窗", "用户明确要求记住")
        self.assertEqual(confirmed_memory_context(state), "")
        _, memory = confirm_memory(state, proposal["id"], proposal["version"])
        self.assertIn("travel.seat", confirmed_memory_context(state))
        self.assertEqual(memory["version"], 1)

    def test_memory_update_keeps_history_and_can_rollback(self):
        state = empty_intelligence_state()
        first = propose_memory(state, "travel.seat", "靠窗", "首次设置")
        _, memory = confirm_memory(state, first["id"], first["version"])
        second = propose_memory(state, "travel.seat", "过道", "用户修改")
        _, updated = confirm_memory(state, second["id"], second["version"])
        self.assertEqual(updated["version"], 2)
        self.assertEqual(updated["history"][0]["value"], "靠窗")
        rolled_back = rollback_memory(state, memory["id"], 1)
        self.assertEqual(rolled_back["value"], "靠窗")
        self.assertEqual(rolled_back["version"], 3)

    def test_sensitive_memory_is_not_auto_injected(self):
        state = empty_intelligence_state()
        proposal = propose_memory(state, "identity.secret", "敏感内容", "用户要求保存", sensitivity="sensitive")
        confirm_memory(state, proposal["id"], proposal["version"])
        self.assertNotIn("敏感内容", confirmed_memory_context(state))

    def test_automatic_memory_filters_private_data_and_is_not_exposed(self):
        state = empty_intelligence_state()
        changed = apply_automatic_memory_candidates(state, [
            {"key": "preference.answer_style", "value": "喜欢先给结论", "confidence": 0.95, "ttl_days": 180},
            {"key": "contact.phone", "value": "13800138000", "confidence": 1, "ttl_days": 365},
            {"key": "preference.uncertain", "value": "可能喜欢咖啡", "confidence": 0.4, "ttl_days": 180},
        ], now=1_800_000_000)
        self.assertEqual(changed, 1)
        self.assertIn("喜欢先给结论", confirmed_memory_context(state))
        public = public_intelligence_state(state)
        self.assertEqual(public["memory_count"], 1)
        self.assertEqual(public["memories"], [])
        memory = next(iter(state["memories"].values()))
        memory["expires_at"] = 1_799_999_999
        self.assertEqual(prune_automatic_memories(state, 1_800_000_000), 1)

    def test_feedback_creates_confirmable_rule_instead_of_silent_policy_change(self):
        state = empty_intelligence_state()
        for index in range(3):
            record_feedback(
                state, target_type="notification", target_id=f"n{index}", outcome="dismissed",
                metadata={"notification_type": "schedule_upcoming"},
            )
        rules = list(state["rule_proposals"].values())
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0]["status"], "pending")

    def test_usage_budget_summary_is_date_bounded(self):
        state = empty_intelligence_state()
        with patch("agents._application.intelligence.service.time.time", return_value=1_800_000_000):
            record_usage(state, 10, 5, 15, "chat")
        summary = usage_summary(state, 1_800_000_000)
        self.assertEqual(summary["daily_tokens"], 15)
        self.assertEqual(summary["monthly_tokens"], 15)

    async def test_user_assets_are_shared_across_conversations(self):
        store = FakeStore()
        workspace = empty_workspace()
        event = apply_calendar_changes(workspace, [{
            "operation": "create",
            "event": {"title": "参观故宫", "start_time": 100, "place": PLACE},
        }])[0]
        await save_workspace(store, TEST_USER_ID, workspace)

        first_read = await load_user_workspace(store, user_id=TEST_USER_ID)
        second_read = await load_user_workspace(store, user_id=TEST_USER_ID)

        self.assertIn(event["id"], first_read["schedules"])
        self.assertIn(event["id"], second_read["schedules"])

