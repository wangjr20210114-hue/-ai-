from agents._tests.support.workspace_environment import *  # noqa: F401,F403


class ProactiveOpportunityTests(unittest.IsolatedAsyncioTestCase):
    def test_proactive_policy_deduplicates_and_respects_daily_limit(self):
        now = 1_800_000_000
        state = empty_proactive_state()
        update_preferences(state, {
            "daily_limit": 1,
            "quiet_hours": {"enabled": False},
        })
        signals = [
            {"type": "schedule_upcoming", "dedup_key": "one", "priority": "normal", "title": "一", "detail": "一", "action": "一", "occurred_at": now},
            {"type": "schedule_upcoming", "dedup_key": "two", "priority": "normal", "title": "二", "detail": "二", "action": "二", "occurred_at": now},
        ]
        first = process_schedule_signals(state, signals, now)
        second = process_schedule_signals(state, signals, now)
        self.assertEqual(first["notifications_created"], 1)
        self.assertEqual(len(state["notifications"]), 1)
        self.assertEqual(second["notifications_created"], 0)
        self.assertTrue(any(run["reason"] == "daily_limit_reached" for run in state["runs"].values()))

    def test_proactive_fallback_mottos_are_sanitized_and_bounded(self):
        state = empty_proactive_state()
        update_preferences(state, {
            "fallback_mottos": [
                "  星光会找到夜路。  ", "", "星光会找到夜路。",
                "二", "三", "四", "五", "六",
            ],
        })
        self.assertEqual(
            state["preferences"]["fallback_mottos"],
            ["星光会找到夜路。", "二", "三", "四", "五", "六"],
        )

    def test_observe_only_persists_event_and_run_without_notification(self):
        state = empty_proactive_state()
        update_preferences(state, {"autonomy_mode": "observe", "quiet_hours": {"enabled": False}})
        signal = {
            "type": "schedule_upcoming", "source": "schedule_collector", "dedup_key": "observe:test",
            "priority": "normal", "title": "即将开始", "detail": "只记录不提醒", "action": "", "occurred_at": 100,
        }
        stats = process_schedule_signals(state, [signal], 100)
        self.assertEqual(stats["events_created"], 1)
        self.assertEqual(stats["notifications_created"], 0)
        self.assertEqual(next(iter(state["runs"].values()))["reason"], "observe_only")

    def test_read_notification_leaves_the_display_window(self):
        now = 1_800_000_000
        state = empty_proactive_state()
        update_preferences(state, {"quiet_hours": {"enabled": False}})
        process_schedule_signals(state, [{
            "type": "schedule_upcoming",
            "dedup_key": "read-me",
            "title": "待读提醒",
            "detail": "测试",
            "action": "测试",
            "occurred_at": now,
        }], now)
        notification_id = public_proactive_state(state, now)["notifications"][0]["id"]
        mutate_notification(state, notification_id, "mark_read", now + 1)
        self.assertEqual(public_proactive_state(state, now + 1)["notifications"], [])

    async def test_notification_controls_and_preferences_are_persistent(self):
        store = FakeStore()
        state = empty_proactive_state()
        state["notifications"]["ntf-1"] = {
            "id": "ntf-1", "status": "unread", "priority": "normal",
            "created_at": 100, "updated_at": 100, "version": 1,
        }
        update_preferences(state, {"enabled": False, "daily_limit": 2})
        mutate_notification(state, "ntf-1", "snooze", 100, 500)
        await save_proactive_state(store, state, TEST_USER_ID)
        restored = await load_proactive_state(store, TEST_USER_ID)
        self.assertTrue(restored["preferences"]["enabled"])
        self.assertEqual(restored["preferences"]["daily_limit"], 2)
        self.assertEqual(restored["notifications"]["ntf-1"]["status"], "snoozed")

