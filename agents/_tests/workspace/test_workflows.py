from agents._tests.support.workspace_environment import *  # noqa: F401,F403


class WorkspaceWorkflowTests(unittest.IsolatedAsyncioTestCase):
    def test_persistent_active_workflow_has_its_own_capability_route(self):
        self.assertEqual(
            required_tools_for_plan({"needs_workflow_action": True}),
            ("propose_workflow",),
        )

    async def test_workspace_round_trip_increments_revision(self):
        store = FakeStore()
        state = empty_workspace()
        saved = await save_workspace(store, "c1", state)
        restored = await load_workspace(store, "c1")
        self.assertEqual(saved["revision"], 1)
        self.assertEqual(restored["revision"], 1)

    def test_workspace_signals_are_persistent_and_deduplicated(self):
        state = empty_proactive_state()
        first, created = ingest_workspace_signal(
            state, signal_type="file_uploaded", dedup_key="blob-1", payload={"filename": "paper.pdf"}, now=100,
        )
        repeated, created_again = ingest_workspace_signal(
            state, signal_type="file_uploaded", dedup_key="blob-1", payload={"filename": "paper.pdf"}, now=101,
        )
        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(first["id"], repeated["id"])
        self.assertEqual(len(state["runs"]), 1)

        route, route_created = ingest_workspace_signal(
            state, signal_type="route_changed", dedup_key="route-1", payload={"source": "map"}, now=102,
        )
        self.assertTrue(route_created)
        self.assertEqual(route["type"], "route_changed")

        location, location_created = ingest_workspace_signal(
            state,
            signal_type="browser_location_weather",
            dedup_key="2026-07-23:39.90:116.40",
            payload={"source": "browser_permission", "precision": "city"},
            now=103,
        )
        self.assertTrue(location_created)
        self.assertEqual(location["type"], "browser_location_weather")
        self.assertNotIn("latitude", location["payload"])
        self.assertNotIn("longitude", location["payload"])

    def test_workflow_requires_confirmation_and_emits_due_steps_once(self):
        state = empty_proactive_state()
        workflow = propose_workflow(
            state,
            title="出发准备",
            reason="按阶段提醒",
            steps=[
                {"offset_minutes": 0, "title": "检查证件", "body": "确认身份证", "action_prompt": "帮我列清单"},
                {"offset_minutes": 60, "title": "准备出门", "body": "检查路线"},
            ],
            now=100,
        )
        self.assertEqual(workflow["status"], "awaiting_confirmation")
        self.assertEqual(collect_workflow_signals(state, 100), [])
        accepted = decide_workflow(state, workflow["id"], workflow["version"], True, 100)
        self.assertEqual(accepted["status"], "active")
        due = collect_workflow_signals(state, 100)
        self.assertEqual(len(due), 1)
        self.assertEqual(due[0]["source"], "workflow_scheduler")
        self.assertEqual(collect_workflow_signals(state, 100), [])
        decide_workflow_step(state, workflow["id"], "step_1", "complete", 200)
        later = collect_workflow_signals(state, 3700)
        self.assertEqual(len(later), 1)
        self.assertEqual(state["workflows"][workflow["id"]]["status"], "active")
        decide_workflow_step(state, workflow["id"], "step_2", "complete", 3800)
        self.assertEqual(state["workflows"][workflow["id"]]["status"], "completed")

    def test_pending_workflow_title_is_idempotent_across_model_variations(self):
        state = empty_proactive_state()
        first = propose_workflow(
            state,
            title="TEST-WORKFLOW",
            reason="第一次模型表述",
            steps=[{"offset_minutes": 0, "title": "核对测试", "body": "检查状态"}],
            now=100,
        )
        repeated = propose_workflow(
            state,
            title="  test-workflow  ",
            reason="第二次模型换了一种说法",
            steps=[{"offset_minutes": 0, "title": "执行测试", "body": "核对结果并报告"}],
            now=101,
        )
        self.assertEqual(repeated["id"], first["id"])
        self.assertEqual(repeated["reason"], "第一次模型表述")
        self.assertEqual(len(state["workflows"]), 1)

    def test_workflow_failure_emits_compensation_and_blocks_dependents_until_resolved(self):
        state = empty_proactive_state()
        workflow = propose_workflow(
            state,
            title="发布准备",
            reason="失败时需要回退",
            steps=[
                {
                    "offset_minutes": 0,
                    "title": "更新配置",
                    "body": "应用新配置",
                    "compensation": {
                        "title": "恢复旧配置",
                        "body": "将配置恢复到上一个已知版本",
                        "action_prompt": "请给我恢复步骤",
                    },
                },
                {"offset_minutes": 0, "title": "验证结果", "depends_on": ["step_1"]},
            ],
            now=100,
        )
        decide_workflow(state, workflow["id"], workflow["version"], True, 100)
        self.assertEqual(len(collect_workflow_signals(state, 100)), 1)
        decide_workflow_step(state, workflow["id"], "step_1", "fail", 110)
        compensation = collect_workflow_signals(state, 110)
        self.assertEqual(len(compensation), 1)
        self.assertEqual(compensation[0]["type"], "workflow_compensation_due")
        self.assertEqual(collect_workflow_signals(state, 110), [])
        decide_workflow_step(state, workflow["id"], "step_1", "compensate", 120)
        due = collect_workflow_signals(state, 120)
        self.assertEqual(len(due), 1)
        self.assertEqual(due[0]["title"], "验证结果")

    def test_failed_workflow_step_can_retry_without_duplicate_attempt_signal(self):
        state = empty_proactive_state()
        workflow = propose_workflow(
            state, title="重试流程", reason="测试", steps=[{"offset_minutes": 0, "title": "执行"}], now=100,
        )
        decide_workflow(state, workflow["id"], workflow["version"], True, 100)
        collect_workflow_signals(state, 100)
        decide_workflow_step(state, workflow["id"], "step_1", "fail", 110)
        self.assertEqual(len(collect_workflow_signals(state, 110)), 1)
        decide_workflow_step(state, workflow["id"], "step_1", "retry", 120)
        retried = collect_workflow_signals(state, 120)
        self.assertEqual(len(retried), 1)
        self.assertIn(":1:", retried[0]["dedup_key"].replace("workflow_step_due", ""))

    def test_workflow_step_transition_retires_stale_notification(self):
        state = empty_proactive_state()
        workflow = propose_workflow(
            state,
            title="补偿通知清理",
            reason="测试完成后不再主动展示旧提醒",
            steps=[{
                "offset_minutes": 0,
                "title": "核对",
                "compensation": {"title": "恢复", "body": "恢复测试状态"},
            }],
            now=100,
        )
        decide_workflow(state, workflow["id"], workflow["version"], True, 100)
        due = collect_workflow_signals(state, 100)
        process_schedule_signals(state, due, 100)
        self.assertEqual(len(public_proactive_state(state)["notifications"]), 1)

        decide_workflow_step(state, workflow["id"], "step_1", "fail", 110)
        self.assertEqual(public_proactive_state(state)["notifications"], [])
        compensation = collect_workflow_signals(state, 110)
        process_schedule_signals(state, compensation, 110)
        self.assertEqual(public_proactive_state(state)["notifications"][0]["title"], "恢复")

        decide_workflow_step(state, workflow["id"], "step_1", "compensate", 120)
        self.assertEqual(public_proactive_state(state)["notifications"], [])

    def test_action_snapshot_tampering_is_rejected(self):
        action = new_action("meeting_create", {"subject": "评审会"}, requires_confirmation=True)
        action["payload"]["subject"] = "被篡改"
        with self.assertRaisesRegex(ValueError, "快照校验失败"):
            verify_action_snapshot(action)

    def test_provider_ledger_blocks_duplicate_side_effects(self):
        state = empty_workspace()
        action = new_action("meeting_create", {"subject": "评审会"}, requires_confirmation=True)
        begin_action_execution(action, owner="test", now=100)
        first = start_provider_call(state, action, 100)
        with self.assertRaisesRegex(ValueError, "未核对"):
            start_provider_call(state, action, 101)
        finish_provider_call(state, action, {"ok": True, "meeting_id": "m1"}, 102)
        self.assertEqual(first["status"], "succeeded")
        self.assertEqual(action["status"], "succeeded")

    def test_provider_unknown_result_requires_manual_reconciliation(self):
        state = empty_workspace()
        action = new_action("meeting_create", {"subject": "评审会"}, requires_confirmation=True)
        begin_action_execution(action, owner="test", now=100)
        call = start_provider_call(state, action, 100)
        finish_provider_call(
            state, action,
            {"ok": False, "error": "请求中断", "reconciliation_required": True},
            102,
        )
        self.assertEqual(call["status"], "unknown")
        self.assertEqual(action["status"], "reconciliation_required")
        self.assertTrue(action["reconciliation_required"])

    def test_expired_execution_requires_reconciliation_and_never_retries(self):
        state = empty_workspace()
        action = new_action("image_generate", {"prompt": "test"}, requires_confirmation=False)
        begin_action_execution(action, owner="test", now=100, lease_seconds=30)
        put_action(state, action)
        recovered = recover_stale_actions(state, 131)
        self.assertEqual(len(recovered), 1)
        stored = state["actions"][action["id"]]
        self.assertEqual(stored["status"], "reconciliation_required")
        self.assertTrue(stored["reconciliation_required"])

    async def test_travel_plan_asset_crud_uses_user_workspace(self):
        store = FakeStore()
        saved = await handler(FakeContext(store, {
            "operation": "save_travel_plan",
            "plan": {"title": "北京三日游", "destination": "北京", "days": 3, "markdown_content": "行程"},
        }))
        plan = saved["travel_plan"]
        self.assertTrue(plan["id"].startswith("travel_"))
        restored = await load_user_workspace(store, user_id=TEST_USER_ID)
        self.assertIn(plan["id"], restored["travel_plans"])
        deleted = await handler(FakeContext(store, {"operation": "delete_travel_plan", "plan_id": plan["id"]}))
        self.assertEqual(deleted["deleted_plan_id"], plan["id"])

