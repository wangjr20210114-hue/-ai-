from __future__ import annotations

import asyncio
import time
import unittest
from unittest.mock import AsyncMock, patch

import aiosqlite

from agent.cancellation import RunCancellationService
from agent.context import AgentContext
from agent.executor import AgentExecutor
from agent.orchestrator import AgentOrchestrator
from agent.runtime import PersistentRuntime
from agent.supervisor import AgentSupervisor
from agent.collectors import schedule_collector
from application.action_service import ActionService
from application.agent_application_service import AgentApplicationService
from application.notification_service import NotificationService
from application.proactive_event_service import ProactiveEventService
from database.init_db import (
    M1_SCHEMA,
    M2_EXECUTION_SCHEMA,
    M2_SCHEMA,
    M3_SCHEMA,
    PRODUCT_CONTROLS_SCHEMA,
    PRODUCT_INTELLIGENCE_SCHEMA,
    PROVIDER_CALLS_SCHEMA,
    SCHEMA,
)
from database.migrations import Migration, apply_migrations
from database.repositories import (
    conversation_repo,
    feedback_repo,
    job_repo,
    memory_repo,
    notification_repo,
    provider_call_repo,
    runtime_repo,
    usage_repo,
)
from skills.base_skill import BaseSkill, SkillRegistry, SkillResult, SkillStreamEvent
from skills.image_skill import ImageSkill
from agent.contracts import PermissionLevel, plan_to_dict


class FakeWebSocket:
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def send_text(self, message: str) -> None:
        self.messages.append(message)




class FakeStreamingSkill(BaseSkill):
    @property
    def name(self) -> str:
        return "chat"

    @property
    def description(self) -> str:
        return "test stream"

    @property
    def trigger_keywords(self) -> list[str]:
        return []

    @property
    def mode(self) -> str:
        return "auto"

    @property
    def permission_level(self) -> PermissionLevel:
        return PermissionLevel.AUTO

    @property
    def streaming(self) -> bool:
        return True

    async def suggest(self, message, params):
        return SkillResult(intent=self.name, content=message, params=params)

    async def stream(self, message, params, session_id, history, *, run_id, cancellation=None):
        del message, params, session_id, history, run_id, cancellation
        yield SkillStreamEvent(delta="持久")
        yield SkillStreamEvent(delta="回答")
        yield SkillStreamEvent(
            done=True,
            content="持久回答",
            data={"provider": "fake"},
            usage={"total_tokens": 4},
            provider_request_id="fake-request",
        )




class CancellableStreamingSkill(FakeStreamingSkill):
    def __init__(self, started: asyncio.Event) -> None:
        self.started = started

    async def stream(self, message, params, session_id, history, *, run_id, cancellation=None):
        del message, params, session_id, history, run_id
        if cancellation is None:
            raise RuntimeError("cancellation token missing")
        self.started.set()
        await cancellation.wait()
        cancellation.raise_if_cancelled()
        yield SkillStreamEvent(delta="unreachable")


class DisconnectingWebSocket:
    async def send_text(self, message: str) -> None:
        del message
        raise ConnectionError("browser disconnected")


class ProactiveAgentArchitectureTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await self.db.execute("PRAGMA foreign_keys=ON")
        await apply_migrations(
            self.db,
            [
                Migration(1, "initial_schema", SCHEMA),
                Migration(2, "persistent_identity_conversations_files", M1_SCHEMA),
                Migration(3, "persistent_agent_runtime", M2_SCHEMA),
                Migration(4, "agent_execution_leases_and_results", M2_EXECUTION_SCHEMA),
                Migration(5, "proactive_jobs_notifications_usage", M3_SCHEMA),
                Migration(6, "memory_feedback_product_intelligence", PRODUCT_INTELLIGENCE_SCHEMA),
                Migration(7, "memory_versions_and_usage_preferences", PRODUCT_CONTROLS_SCHEMA),
                Migration(8, "provider_call_reconciliation_ledger", PROVIDER_CALLS_SCHEMA),
            ],
        )
        modules = [
            runtime_repo,
            notification_repo,
            job_repo,
            conversation_repo,
            schedule_collector,
            usage_repo,
            memory_repo,
            feedback_repo,
            provider_call_repo,
        ]
        self.patches = [patch.object(module, "get_db", return_value=self.db) for module in modules]
        for item in self.patches:
            item.start()
        await conversation_repo.ensure_local_identity()

    async def asyncTearDown(self) -> None:
        for item in reversed(self.patches):
            item.stop()
        await self.db.close()

    async def test_user_message_creates_immutable_action_before_side_effect(self) -> None:
        registry = SkillRegistry()
        registry.register(ImageSkill())
        runtime = PersistentRuntime()
        notifications = NotificationService()
        executor = AgentExecutor(registry=registry, runtime=runtime, notifications=notifications)
        orchestrator = AgentOrchestrator(
            registry=registry,
            runtime=runtime,
            executor=executor,
            action_service=ActionService(),
        )
        application = AgentApplicationService(runtime=runtime, orchestrator=orchestrator)
        websocket = FakeWebSocket()

        with patch(
            "agent.intent_router.classify_intent",
            new=AsyncMock(return_value={"intent": "image", "params": {"prompt": "一艘乘风破浪的小船"}}),
        ):
            run = await application.handle_user_message(
                conversation_id=conversation_repo.DEFAULT_CONVERSATION_ID,
                text="帮我画一艘船",
                websocket=websocket,
                context=AgentContext(session_id=conversation_repo.DEFAULT_CONVERSATION_ID, history=[]),
                client_message_id="client-message-1",
            )

        self.assertEqual(run["status"], "waiting_confirmation")
        self.assertEqual(run["intent"], "image")
        action = run["action"]
        self.assertEqual(action["status"], "awaiting_confirmation")
        self.assertEqual(action["snapshot"]["input"]["prompt"], "一艘乘风破浪的小船")
        self.assertEqual(action["snapshot"]["input"]["schema_version"], 1)
        messages = await conversation_repo.list_messages(conversation_repo.DEFAULT_CONVERSATION_ID)
        self.assertEqual(messages[-1]["id"], "client-message-1")
        self.assertTrue(any('"action_id"' in message for message in websocket.messages))

    async def test_confirmed_action_executes_once_through_single_executor(self) -> None:
        registry = SkillRegistry()
        image_skill = ImageSkill()
        registry.register(image_skill)
        runtime = PersistentRuntime()
        notifications = NotificationService()
        executor = AgentExecutor(registry=registry, runtime=runtime, notifications=notifications)

        event, _ = await runtime_repo.create_event("user.message", {"text": "画图"}, "event:image")
        run = await runtime.start_run(event["id"])
        await runtime.set_classification(run["id"], "image", {"params": {"prompt": "星空"}})
        plan = await image_skill.create_plan(
            run_id=run["id"],
            session_id="default-conversation",
            event_type="user_activity",
            message="画图",
            params={"prompt": "星空"},
        )
        from agent.contracts import plan_to_dict

        await runtime.set_plan(run["id"], plan_to_dict(plan), execution_lane="background", max_attempts=1)
        await runtime.transition(run["id"], "planned", "policy_checked", step="policy_checked")
        await runtime.transition(run["id"], "policy_checked", "waiting_confirmation", step="confirmation_required")
        action = await ActionService().create_pending_action(run["id"], plan, image_skill)
        await runtime_repo.confirm_action(action["id"], action["version"])

        with patch(
            "services.hunyuan_service.hunyuan_service.text_to_image",
            new=AsyncMock(return_value="https://example.test/image.png"),
        ) as provider:
            result = await executor.execute_run(run["id"], worker_id="test-worker")
            duplicate = await runtime_repo.confirm_action(action["id"], action["version"])

        self.assertEqual(result.status, "succeeded")
        self.assertEqual(duplicate["status"], "succeeded")
        self.assertEqual(provider.await_count, 1)
        saved_action = await runtime_repo.get_action(action["id"])
        saved_run = await runtime_repo.get_run(run["id"])
        self.assertEqual(saved_action["result_json"]["data"]["image_url"], "https://example.test/image.png")
        self.assertEqual(saved_run["status"], "succeeded")

    async def test_provider_call_ledger_recovers_success_after_crash_window(self) -> None:
        registry = SkillRegistry()
        image_skill = ImageSkill()
        registry.register(image_skill)
        runtime = PersistentRuntime()
        executor = AgentExecutor(
            registry=registry,
            runtime=runtime,
            notifications=NotificationService(),
        )

        event, _ = await runtime_repo.create_event(
            "user.message", {}, "event:provider-ledger-recovery"
        )
        run = await runtime_repo.create_run(
            event["id"], execution_lane="background", max_attempts=1
        )
        for status in ("classified", "planned", "policy_checked", "waiting_confirmation"):
            run = await runtime_repo.transition_run(run["id"], status, step=status)
        action = await runtime_repo.create_action(
            run["id"],
            "image",
            {"input": {"schema_version": 1, "prompt": "durable result"}},
            "image:provider-ledger-recovery",
        )
        await runtime_repo.confirm_action(action["id"], 1)
        await runtime_repo.claim_run(run["id"], "dead-worker", lease_seconds=5)
        action = await runtime_repo.start_action_execution(action["id"])
        call, created = await provider_call_repo.begin_call(
            call_id=f"call-{action['id']}",
            run_id=run["id"],
            action_id=action["id"],
            provider="image",
            operation="execute_action",
            idempotency_key=action["idempotency_key"],
            request_hash=action["snapshot_hash"],
        )
        self.assertTrue(created)
        await provider_call_repo.complete_call(
            call["id"],
            response={
                "content": "图片已生成",
                "data": {"image_url": "https://example.test/recovered.png"},
                "usage": {"image_generations": 1},
            },
            external_resource_id="provider-image-1",
        )
        await self.db.execute(
            "UPDATE agent_runs SET lease_until=? WHERE id=?",
            (time.time() - 1, run["id"]),
        )
        await self.db.commit()

        report = await runtime_repo.recover_expired_runs()
        self.assertEqual(report["reconciliation_required"], 1)
        outcome = await executor.reconcile_unknown_side_effect(
            await runtime_repo.get_action(action["id"])
        )

        self.assertEqual(outcome["status"], "succeeded")
        saved_action = await runtime_repo.get_action(action["id"])
        saved_run = await runtime_repo.get_run(run["id"])
        self.assertEqual(saved_action["status"], "succeeded")
        self.assertFalse(saved_action["reconciliation_required"])
        self.assertEqual(
            saved_action["result_json"]["data"]["image_url"],
            "https://example.test/recovered.png",
        )
        self.assertEqual(saved_run["status"], "succeeded")
        self.assertTrue(
            any(
                item["step"] == "action_reconciled_succeeded"
                for item in saved_run["observations"]
            )
        )

    async def test_expired_side_effect_lease_requires_reconciliation(self) -> None:
        event, _ = await runtime_repo.create_event("user.message", {}, "event:reconcile")
        run = await runtime_repo.create_run(event["id"], execution_lane="background")
        for status in ("classified", "planned", "policy_checked", "waiting_confirmation"):
            run = await runtime_repo.transition_run(run["id"], status, step=status)
        action = await runtime_repo.create_action(
            run["id"],
            "image",
            {"input": {"schema_version": 1, "prompt": "unknown"}},
            "image:reconcile",
        )
        await runtime_repo.confirm_action(action["id"], 1)
        await runtime_repo.claim_run(run["id"], "dead-worker", lease_seconds=5)
        await runtime_repo.start_action_execution(action["id"])
        await self.db.execute(
            "UPDATE agent_runs SET lease_until=? WHERE id=?", (time.time() - 1, run["id"])
        )
        await self.db.commit()

        report = await runtime_repo.recover_expired_runs()
        recovered_action = await runtime_repo.get_action(action["id"])
        recovered_run = await runtime_repo.get_run(run["id"])
        self.assertEqual(report["reconciliation_required"], 1)
        self.assertTrue(recovered_action["reconciliation_required"])
        self.assertEqual(recovered_run["status"], "failed")
        with self.assertRaises(runtime_repo.StateConflict):
            await runtime_repo.retry_run(run["id"])

    async def test_explicit_cancellation_stops_streaming_run_and_persists_state(self) -> None:
        started = asyncio.Event()
        cancellation_service = RunCancellationService()
        registry = SkillRegistry()
        skill = CancellableStreamingSkill(started)
        registry.register(skill)
        runtime = PersistentRuntime()
        executor = AgentExecutor(
            registry=registry,
            runtime=runtime,
            cancellations=cancellation_service,
        )

        event, _ = await runtime_repo.create_event(
            "user.message", {"text": "long response"}, "event:cancel-stream"
        )
        run = await runtime.start_run(event["id"], max_attempts=1)
        await runtime.set_classification(run["id"], "chat", {"params": {}})
        plan = await skill.create_plan(
            run_id=run["id"],
            session_id=conversation_repo.DEFAULT_CONVERSATION_ID,
            event_type="user_activity",
            message="long response",
            params={},
        )
        await runtime.set_plan(
            run["id"], plan_to_dict(plan), execution_lane="interactive", max_attempts=1
        )
        await runtime.transition(run["id"], "planned", "policy_checked", step="policy_checked")
        await runtime.transition(run["id"], "policy_checked", "queued", step="queued")

        task = asyncio.create_task(executor.execute_run(run["id"], worker_id="interactive-test"))
        await asyncio.wait_for(started.wait(), timeout=1)
        self.assertTrue(await cancellation_service.cancel(run["id"]))
        await runtime_repo.cancel_run(run["id"])
        result = await asyncio.wait_for(task, timeout=1)

        self.assertEqual(result.status, "cancelled")
        saved = await runtime_repo.get_run(run["id"])
        self.assertEqual(saved["status"], "cancelled")
        self.assertTrue(any(item["step"] == "run_cancelled" for item in saved["observations"]))

    async def test_executing_side_effect_refuses_unsafe_cancellation(self) -> None:
        event, _ = await runtime_repo.create_event("user.message", {}, "event:unsafe-cancel")
        run = await runtime_repo.create_run(event["id"], execution_lane="background")
        for status in ("classified", "planned", "policy_checked", "waiting_confirmation"):
            run = await runtime_repo.transition_run(run["id"], status, step=status)
        action = await runtime_repo.create_action(
            run["id"],
            "image",
            {"input": {"schema_version": 1, "prompt": "already sent"}},
            "image:unsafe-cancel",
        )
        await runtime_repo.confirm_action(action["id"], 1)
        await runtime_repo.claim_run(run["id"], "worker", lease_seconds=30)
        await runtime_repo.start_action_execution(action["id"])

        with self.assertRaisesRegex(runtime_repo.StateConflict, "cannot be cancelled safely"):
            await runtime_repo.cancel_run(run["id"])

    async def test_schedule_collector_produces_deduplicated_proactive_notification(self) -> None:
        start_time = time.time() + 10 * 60
        await self.db.execute(
            "INSERT INTO schedules(id,session_id,title,start_time,duration_minutes,done,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?)",
            ("schedule-1", "local-user", "需求评审", start_time, 60, 0, time.time(), time.time()),
        )
        await self.db.commit()
        collector = schedule_collector.ScheduleCollector(lookahead_minutes=30)
        signals, _ = await collector.collect(now=time.time())
        service = ProactiveEventService(
            runtime=PersistentRuntime(), notifications=NotificationService()
        )
        first = await service.process_signal(signals[0].to_dict())
        second = await service.process_signal(signals[0].to_dict())

        cursor = await self.db.execute("SELECT COUNT(*) FROM notifications")
        self.assertEqual((await cursor.fetchone())[0], 1)
        cursor = await self.db.execute("SELECT COUNT(*) FROM agent_events")
        self.assertEqual((await cursor.fetchone())[0], 1)
        self.assertEqual(first["status"], "succeeded")
        self.assertEqual(second["id"], first["id"])

    async def test_supervisor_periodic_maintenance_recovers_expired_run_without_restart(self) -> None:
        runtime = PersistentRuntime()
        registry = SkillRegistry()
        executor = AgentExecutor(registry=registry, runtime=runtime)
        supervisor = AgentSupervisor(
            runtime=runtime,
            executor=executor,
            maintenance_interval_seconds=1,
        )
        event, _ = await runtime_repo.create_event(
            "system.test", {}, "event:periodic-maintenance"
        )
        run = await runtime_repo.create_run(
            event["id"], execution_lane="background", max_attempts=2
        )
        for status in ("classified", "planned", "policy_checked", "queued"):
            run = await runtime_repo.transition_run(run["id"], status, step=status)
        await runtime_repo.claim_run(run["id"], "dead-worker", lease_seconds=5)
        await self.db.execute(
            "UPDATE agent_runs SET lease_until=? WHERE id=?",
            (time.time() - 1, run["id"]),
        )
        await self.db.commit()

        report = await supervisor.maintain(force=True)
        saved = await runtime_repo.get_run(run["id"])
        health = await supervisor.health()

        self.assertEqual(report["requeued"], 1)
        self.assertEqual(saved["status"], "queued")
        self.assertEqual(health["queues"]["runs"]["queued"], 1)
        self.assertIsNotNone(health["last_maintenance_at"])

    async def test_scheduler_job_uses_lease_and_checkpoint(self) -> None:
        await job_repo.upsert_job(
            "collector:test",
            "collector.test",
            {},
            next_run_at=time.time() - 1,
            interval_seconds=60,
        )
        claimed = await job_repo.claim_due_job("worker-1")
        self.assertEqual(claimed["status"], "running")
        self.assertIsNone(await job_repo.claim_due_job("worker-2"))
        completed = await job_repo.complete_job(
            claimed["id"], checkpoint={"items": 3}, now=time.time()
        )
        self.assertEqual(completed["status"], "enabled")
        self.assertEqual(completed["checkpoint"]["items"], 3)
        self.assertGreater(completed["next_run_at"], time.time())

    async def test_streaming_skill_survives_transport_disconnect_and_persists_message(self) -> None:
        registry = SkillRegistry()
        skill = FakeStreamingSkill()
        registry.register(skill)
        runtime = PersistentRuntime()
        executor = AgentExecutor(
            registry=registry,
            runtime=runtime,
            notifications=NotificationService(),
        )
        event, _ = await runtime_repo.create_event(
            "user.message",
            {"text": "回答我", "conversation_id": conversation_repo.DEFAULT_CONVERSATION_ID},
            "event:stream-disconnect",
        )
        run = await runtime.start_run(event["id"], execution_lane="interactive")
        await runtime.set_classification(run["id"], "chat", {"params": {}})
        plan = await skill.create_plan(
            run_id=run["id"],
            session_id=conversation_repo.DEFAULT_CONVERSATION_ID,
            event_type="user_activity",
            message="回答我",
            params={},
        )
        await runtime.set_plan(
            run["id"],
            plan_to_dict(plan),
            execution_lane="interactive",
            max_attempts=1,
        )
        await runtime.transition(run["id"], "planned", "policy_checked", step="policy_checked")
        await runtime.transition(run["id"], "policy_checked", "queued", step="run_queued")

        result = await executor.execute_run(
            run["id"],
            worker_id="interactive:test",
            websocket=DisconnectingWebSocket(),
            context=AgentContext(
                session_id=conversation_repo.DEFAULT_CONVERSATION_ID,
                history=["用户: 回答我"],
            ),
        )

        self.assertEqual(result.status, "succeeded")
        self.assertFalse(result.data["transport_delivered"])
        messages = await conversation_repo.list_messages(conversation_repo.DEFAULT_CONVERSATION_ID)
        self.assertEqual(messages[-1]["content"], "持久回答")
        self.assertEqual(messages[-1]["metadata"]["run_id"], run["id"] )
        persisted_run = await runtime.get_run(run["id"])
        self.assertEqual(persisted_run["status"], "succeeded")
        self.assertTrue(
            any(item["step"] == "stream_transport_disconnected" for item in persisted_run["observations"])
        )


if __name__ == "__main__":
    unittest.main()
