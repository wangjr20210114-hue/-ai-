from __future__ import annotations

import asyncio
import json
import time
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agents._infrastructure.makers.conversation_repository import (
    discard_chat_turn,
    public_chat_run,
    read_chat_run,
    write_chat_run,
)
from agents._infrastructure.http import error
from agents._application.proactive.service import collect_provider_signals
from agents._application.proactive.service import empty_proactive_state, process_schedule_signals
from agents._infrastructure.providers.tencent_location import (
    normalize_route_contract,
    plan_driving_route,
)
from agents.proactive.index import handler as proactive_handler
from agents.stop.index import handler as stop_handler
from agents._controllers.system_controller import _expected_tick_after
from agents._application.chat.turn_policy import run_cancelled
from agents._application.chat.turn_finalizer import TurnFinalizer
from agents._application.chat.presentation_journal import PresentationJournalQueue
from agents._infrastructure.makers.presentation_repository import (
    load_presentation_snapshot,
    save_presentation_snapshot,
)
from agents._presenters.chat_stream import ChatStreamPresenter
from agents._application.intelligence.service import (
    apply_automatic_memory_candidates,
    empty_intelligence_state,
    load_intelligence_state,
    save_intelligence_state,
)
from agents._infrastructure.makers.identity import scoped_conversation_id
from agents._tests.auth_helpers import TEST_USER_ID, authenticated_context
from agents._tests.auth_helpers import authenticated_namespace
from agents._tests.support.fakes import (
    FakeCheckpointer,
    FakeStore as WorkspaceFakeStore,
)
from agents.messages.index import handler as messages_handler
from agents.run.index import handler as run_handler


class FakeStore:
    def __init__(self):
        self.values = {}

    async def aget(self, namespace, key):
        value = self.values.get((namespace, key))
        return None if value is None else {"value": value}

    async def aput(self, namespace, key, value):
        self.values[(namespace, key)] = value


class FakeConversationStore:
    def __init__(self):
        self.metadata = {"title": "保留标题"}

    async def get_conversation(self, **_value):
        return {"metadata": self.metadata}

    async def update_conversation(self, **value):
        self.metadata.update(value["metadata"])


class FakeProactiveStores:
    def __init__(self):
        self.langgraph_store = FakeStore()


class RuntimeRegressionTests(unittest.IsolatedAsyncioTestCase):
    async def test_public_stream_snapshot_recovers_without_private_reasoning(self):
        store = FakeStore()
        presenter = ChatStreamPresenter("zh-CN")
        queue = PresentationJournalQueue(
            store=store,
            conversation_id="conversation-recovery",
            run_id="run-recovery",
            client_message_id="client-recovery",
        )
        await queue.put(presenter.progress("planning", "completed"))
        await queue.put(presenter.token("正在恢复"))
        await queue.put(presenter.token("中的回答"))
        await queue.put(presenter.sources({
            "query": "AI",
            "results": [{"title": "source", "url": "https://example.com"}],
        }))
        await queue.put(object())

        snapshot = await load_presentation_snapshot(
            store,
            "conversation-recovery",
            "run-recovery",
        )
        self.assertEqual(snapshot["content"], "正在恢复中的回答")
        self.assertEqual(snapshot["client_message_id"], "client-recovery")
        self.assertEqual(snapshot["search_results"]["query"], "AI")
        self.assertGreaterEqual(snapshot["revision"], 4)
        self.assertNotIn("messages", snapshot)
        self.assertNotIn("tool_calls", snapshot)

    async def test_run_endpoint_returns_only_the_current_maker_projection(self):
        client_id = "client-run-state"

        class Store:
            def __init__(self):
                self.langgraph_store = FakeStore()

            async def get_conversation(self, **_values):
                return {"metadata": {"yuanbao_chat_run_v1": {
                    "run_id": "run-state",
                    "client_message_id": client_id,
                    "status": "running",
                    "discarded_client_message_ids": [],
                }}}

        store = Store()
        ctx = authenticated_namespace(
            conversation_id="run-state-conversation",
            store=store,
        )
        physical_id = scoped_conversation_id(
            ctx,
            TEST_USER_ID,
            "run-state-conversation",
        )
        await save_presentation_snapshot(
            store.langgraph_store,
            physical_id,
            "run-state",
            {
                "schema_version": 1,
                "run_id": "run-state",
                "client_message_id": client_id,
                "revision": 2,
                "updated_at": 2,
                "content": "可恢复内容",
            },
        )
        response = await run_handler(ctx)
        self.assertEqual(response["run"]["status"], "running")
        self.assertEqual(response["presentation"]["content"], "可恢复内容")
        self.assertEqual(response["presentation"]["revision"], 2)

    async def test_proactive_preference_change_triggers_one_refresh(self):
        stores = FakeProactiveStores()
        refreshed = empty_proactive_state()
        refreshed["preferences"]["daily_limit"] = 3
        ctx = authenticated_context(SimpleNamespace(
            env={}, store=stores, conversation_id="settings-conversation",
            request=SimpleNamespace(body={
                "operation": "update_preferences", "preferences": {"daily_limit": 3},
            }, headers={}),
        ))
        with patch(
            "agents._controllers.proactive_controller.run_proactive_tick",
            AsyncMock(return_value=(refreshed, {"signals": 0})),
        ) as tick:
            response = await proactive_handler(ctx)
        tick.assert_awaited_once()
        self.assertEqual(response["preferences"]["daily_limit"], 3)
        self.assertEqual(response["tick_stats"], {"signals": 0})

    async def test_page_open_forces_one_memory_first_refresh(self):
        stores = FakeProactiveStores()
        state = empty_proactive_state()
        ctx = authenticated_context(SimpleNamespace(
            env={}, store=stores, conversation_id="page-open-conversation",
            request=SimpleNamespace(body={"operation": "page_open"}, headers={}),
        ))
        with patch(
            "agents._controllers.proactive_controller._run_tick_with_memory",
            AsyncMock(return_value=(state, {"signals": 0})),
        ) as refresh:
            response = await proactive_handler(ctx)
        refresh.assert_awaited_once()
        self.assertTrue(refresh.await_args.kwargs["force_memory"])
        self.assertEqual(response["tick_stats"], {"signals": 0})

    async def test_document_signal_immediately_creates_one_proactive_opportunity(self):
        stores = FakeProactiveStores()
        ctx = authenticated_context(SimpleNamespace(
            env={}, store=stores, conversation_id="document-conversation",
            request=SimpleNamespace(body={
                "operation": "ingest_signal",
                "signal_type": "file_uploaded",
                "dedup_key": "blob-document-1",
                "payload": {
                    "file_id": "file-1", "storage_key": "uploads/file-1",
                    "filename": "TEST-方案.pdf", "is_paper": False,
                },
            }, headers={}),
        ))
        first = await proactive_handler(ctx)
        second = await proactive_handler(ctx)
        self.assertTrue(first["signal_created"])
        self.assertEqual(first["tick_stats"]["notifications_created"], 1)
        self.assertEqual(first["notifications"][0]["type"], "opportunity_document_next_step")
        self.assertFalse(second["signal_created"])
        self.assertEqual(len(second["notifications"]), 1)

    async def test_foreign_document_can_proactively_offer_translation_without_persisting_preview(self):
        stores = FakeProactiveStores()
        ctx = authenticated_context(SimpleNamespace(
            env={}, store=stores, conversation_id="translation-opportunity",
            request=SimpleNamespace(body={
                "operation": "ingest_signal",
                "signal_type": "file_uploaded",
                "dedup_key": "blob-english-paper",
                "payload": {
                    "file_id": "file-en", "storage_key": "uploads/file-en",
                    "filename": "research.pdf", "is_paper": True,
                    "ui_language": "zh-CN",
                    "preview": "Abstract. This paper presents a new evaluation method for language models.",
                },
            }, headers={}),
        ))
        model = SimpleNamespace(ainvoke=AsyncMock(return_value=SimpleNamespace(content=(
            '{"should_notify":true,"type":"translation_review","title":"先读中文版",'
            '"body":"这份论文主要是英文，翻译后可以直接阅读。",'
            '"action_prompt":"请把“research.pdf”翻译成简体中文，保留标题层级和术语一致性",'
            '"priority":"normal","confidence":0.94,"expires_in_hours":72,"reason":"正文语言与界面语言不同"}'
        ))))
        with patch("agents._controllers.proactive_controller.get_model", return_value=model):
            response = await proactive_handler(ctx)
        self.assertEqual(response["notifications"][0]["type"], "opportunity_translation_review")
        self.assertEqual(response["notifications"][0]["evidence"]["storage_key"], "uploads/file-en")
        self.assertEqual(model.ainvoke.await_count, 1)
        serialized = repr(stores.langgraph_store.values)
        self.assertNotIn("This paper presents", serialized)

    async def test_generated_image_signal_runs_semantic_judgment_once(self):
        stores = FakeProactiveStores()
        ctx = authenticated_context(SimpleNamespace(
            env={}, store=stores, conversation_id="image-conversation",
            request=SimpleNamespace(body={
                "operation": "ingest_signal",
                "signal_type": "image_generated",
                "dedup_key": "image-action-1",
                "payload": {
                    "action_id": "image-action-1",
                    "prompt": "活动页首屏插图，主体靠左并给右侧标题留白",
                    "has_reference_image": False,
                },
            }, headers={}),
        ))
        model = SimpleNamespace(ainvoke=AsyncMock(return_value=SimpleNamespace(content=(
            '{"should_notify":true,"type":"image_iteration","title":"生成移动端适配版",'
            '"body":"当前横幅还可以补一版竖屏构图。",'
            '"action_prompt":"基于刚生成的图片制作9:16移动端版本并保留标题区域",'
            '"priority":"low","confidence":0.9,"expires_in_hours":24,"reason":"已有明确活动页用途"}'
        ))))
        with patch("agents._controllers.proactive_controller.get_model", return_value=model):
            first = await proactive_handler(ctx)
            second = await proactive_handler(ctx)
        self.assertIn("signal_created", first, first)
        self.assertTrue(first["signal_created"])
        self.assertEqual(first["tick_stats"]["notifications_created"], 1)
        self.assertEqual(first["notifications"][0]["type"], "opportunity_image_iteration")
        self.assertFalse(second["signal_created"])
        self.assertEqual(model.ainvoke.await_count, 1)
        image_events = [
            value for value in stores.langgraph_store.values.values()
            if isinstance(value, dict) and isinstance(value.get("events"), dict)
        ]
        self.assertTrue(image_events)
        persisted = next(
            event for event in image_events[0]["events"].values()
            if event.get("type") == "image_generated"
        )
        self.assertNotIn("prompt", persisted["payload"])

    async def test_chat_run_uses_native_conversation_metadata(self):
        store = FakeConversationStore()
        await write_chat_run(
            store,
            "conversation-1",
            run_id="run-1",
            status="running",
            client_message_id="client-1",
            diagnostics={"stage": "semantic_plan", "category": "request_rejected"},
        )
        restored = await read_chat_run(store, "conversation-1")
        self.assertEqual(restored["status"], "running")
        self.assertEqual(public_chat_run(restored)["run_id"], "run-1")
        self.assertEqual(public_chat_run(restored)["client_message_id"], "client-1")
        self.assertEqual(
            public_chat_run(restored)["diagnostics"]["stage"],
            "semantic_plan",
        )
        self.assertEqual(store.metadata["title"], "保留标题")

    async def test_stop_delegates_public_id_to_makers_abort(self):
        store = FakeConversationStore()
        physical_id = scoped_conversation_id(
            SimpleNamespace(),
            TEST_USER_ID,
            "conversation-1",
        )
        await write_chat_run(store, physical_id, run_id="run-1", status="running")
        targets = []
        ctx = authenticated_context(SimpleNamespace(
            env={},
            store=store,
            request=SimpleNamespace(body={"conversation_id": "conversation-1"}, headers={}),
            utils=SimpleNamespace(
                abortActiveRun=lambda target: (
                    targets.append(target)
                    or SimpleNamespace(aborted=True, run_id="run-1")
                ),
            ),
        ))
        response = await stop_handler(ctx)
        self.assertEqual(targets, ["conversation-1"])
        self.assertEqual(response["status"], "aborted")
        self.assertEqual((await read_chat_run(store, physical_id))["status"], "cancelled")

    async def test_stop_removes_memory_that_raced_terminal_generation(self):
        store = FakeConversationStore()
        store.langgraph_store = FakeStore()
        physical_id = scoped_conversation_id(
            SimpleNamespace(), TEST_USER_ID, "conversation-memory-stop",
        )
        await write_chat_run(
            store,
            physical_id,
            run_id="run-memory",
            status="running",
            client_message_id="client-memory",
        )
        intelligence = empty_intelligence_state()
        apply_automatic_memory_candidates(intelligence, [{
            "key": "preference.travel",
            "value": "night clubs",
            "confidence": 0.95,
            "ttl_days": 180,
        }], source_message_id="client-memory")
        await save_intelligence_state(
            store.langgraph_store, intelligence, TEST_USER_ID,
        )
        ctx = authenticated_context(SimpleNamespace(
            env={},
            store=store,
            request=SimpleNamespace(body={
                "conversation_id": "conversation-memory-stop",
                "client_message_id": "client-memory",
            }, headers={}),
            utils=SimpleNamespace(abortActiveRun=lambda _target: None),
        ))
        response = await stop_handler(ctx)
        restored = await load_intelligence_state(
            store.langgraph_store, TEST_USER_ID,
        )
        self.assertEqual(response["status"], "aborted")
        self.assertEqual(restored["memories"], {})

    async def test_delayed_stop_tombstone_never_cancels_the_next_turn(self):
        store = FakeConversationStore()
        await write_chat_run(
            store, "conversation-queue", run_id="run-1", status="running",
            client_message_id="client-1",
        )
        stopped, active = await discard_chat_turn(
            store, "conversation-queue", client_message_id="client-1",
        )
        self.assertTrue(active)
        self.assertEqual(stopped["status"], "cancelled")
        await write_chat_run(
            store, "conversation-queue", run_id="run-2", status="running",
            client_message_id="client-2",
        )
        current, active = await discard_chat_turn(
            store, "conversation-queue", client_message_id="client-1",
        )
        self.assertFalse(active)
        self.assertEqual(current["run_id"], "run-2")
        self.assertEqual(current["status"], "running")
        self.assertIn("client-1", current["discarded_client_message_ids"])

    async def test_stop_before_admission_prevents_the_model_run(self):
        store = FakeConversationStore()
        stopped, active = await discard_chat_turn(
            store, "conversation-early-stop", client_message_id="client-early",
        )
        self.assertFalse(active)
        self.assertIn("client-early", stopped["discarded_client_message_ids"])
        admitted = await write_chat_run(
            store,
            "conversation-early-stop",
            run_id="run-must-not-start",
            status="running",
            client_message_id="client-early",
        )
        self.assertEqual(admitted["status"], "cancelled")
        self.assertTrue(run_cancelled(admitted))

    async def test_cancelled_turn_answer_and_cards_never_restore(self):
        cancelled_id = "client-cancelled"
        messages = [
            HumanMessage(
                content="保留这个问题",
                additional_kwargs={"floris_client_message_id": cancelled_id},
                id="u-cancelled",
            ),
            ToolMessage(
                content=json.dumps({
                    "ui_action": "clarification_action",
                    "clarification": {
                        "id": "must-not-render",
                        "title": "不应显示",
                        "prompt": "不应显示",
                        "fields": [{"id": "x", "label": "x", "type": "text"}],
                    },
                }, ensure_ascii=False),
                tool_call_id="cancelled-tool",
            ),
            AIMessage(content="这段回答必须被彻底删除", id="a-cancelled"),
            HumanMessage(
                content="下一个问题",
                additional_kwargs={"floris_client_message_id": "client-next"},
                id="u-next",
            ),
            AIMessage(content="下一个回答", id="a-next"),
        ]

        class Store:
            def __init__(self):
                self.langgraph_checkpointer = FakeCheckpointer(messages)
                self.langgraph_store = WorkspaceFakeStore()

            async def get_conversation(self, **_values):
                return {"metadata": {"yuanbao_chat_run_v1": {
                    "run_id": "run-next",
                    "client_message_id": "client-next",
                    "status": "completed",
                    "discarded_client_message_ids": [cancelled_id],
                }}}

        response = await messages_handler(authenticated_namespace(
            conversation_id="restore-cancelled", store=Store(),
        ))
        restored = response["messages"]
        self.assertEqual(
            [(item["role"], item["content"]) for item in restored],
            [
                ("user", "保留这个问题"),
                ("user", "下一个问题"),
                ("ai", "下一个回答"),
            ],
        )
        self.assertEqual(restored[1]["client_message_id"], "client-next")
        self.assertEqual(restored[2]["client_message_id"], "client-next")
        self.assertTrue(restored[0]["stopped"])
        self.assertNotIn("clarification", restored[0])

    async def test_running_checkpoint_answer_is_only_a_private_turn_buffer(self):
        client_id = "client-running"
        messages = [
            HumanMessage(
                content="question",
                additional_kwargs={"floris_client_message_id": client_id},
                id="u-running",
            ),
            AIMessage(content="buffered answer must stay private", id="a-running"),
        ]

        class Store:
            def __init__(self):
                self.langgraph_checkpointer = FakeCheckpointer(messages)
                self.langgraph_store = WorkspaceFakeStore()

            async def get_conversation(self, **_values):
                return {"metadata": {"yuanbao_chat_run_v1": {
                    "run_id": "run-active",
                    "client_message_id": client_id,
                    "status": "running",
                    "discarded_client_message_ids": [],
                }}}

        response = await messages_handler(authenticated_namespace(
            conversation_id="restore-running", store=Store(),
        ))
        self.assertEqual(
            [(item["role"], item["content"]) for item in response["messages"]],
            [("user", "question")],
        )
        self.assertNotIn("stopped", response["messages"][0])
        self.assertEqual(response["run"]["status"], "running")

    def test_chat_producer_honors_both_makers_stop_states(self):
        self.assertTrue(run_cancelled({"status": "cancel_requested"}))
        self.assertTrue(run_cancelled({"status": "cancelled"}))
        self.assertTrue(run_cancelled({
            "status": "running",
            "client_message_id": "client-stop",
            "discarded_client_message_ids": ["client-stop"],
        }))
        self.assertFalse(run_cancelled({"status": "running"}))

    async def test_cancelled_finalizer_publishes_no_answer_or_card(self):
        store = FakeConversationStore()
        await write_chat_run(
            store, "conversation-finalizer", run_id="run-stop",
            status="cancelled", client_message_id="client-stop",
        )
        queue = asyncio.Queue()
        sentinel = object()

        class SearchRunner:
            cancelled = False

            def cancel(self):
                self.cancelled = True

        search = SearchRunner()
        settled = []
        finalizer = TurnFinalizer(
            ctx=SimpleNamespace(
                store=store,
                env={},
            ),
            presenter=SimpleNamespace(),
            queue=queue,
            completion_sentinel=sentinel,
            search_runner=search,
            fast_model=object(),
            message="question",
            response_language="zh-CN",
            conversation_id="conversation-finalizer",
            user_id=TEST_USER_ID,
            run_id="run-stop",
            body={},
            identity={"auth_type": "user"},
            capability_plan={},
            answer_capability_plan={},
            memory_context="",
            pending_actions=[{"action": {"id": "must-not-publish"}}],
            followups_enabled=True,
            memory_task=None,
            recent_questions_task=None,
            opportunity_enabled=False,
            telemetry=SimpleNamespace(
                settle=lambda outcome: settled.append(outcome),
                timings_ms={},
            ),
        )
        await finalizer.finish(
            answer="partial answer that must disappear",
            run_error="",
            run_diagnostics={},
            cancelled=False,
            clarification_emitted=False,
            pending_search_results={"results": [{"title": "hidden"}]},
            pending_papers={"papers": [{"title": "hidden"}]},
            usage=[0, 0, 0],
        )
        self.assertTrue(search.cancelled)
        self.assertEqual(await queue.get(), sentinel)
        self.assertTrue(queue.empty())
        self.assertEqual(settled, ["cancelled"])

    def test_daily_health_grace_uses_scheduled_boundary(self):
        now = int(datetime.fromisoformat("2026-07-19T11:00:00+08:00").timestamp())
        expected = _expected_tick_after(now)
        self.assertEqual(expected, int(datetime.fromisoformat("2026-07-19T08:00:00+08:00").timestamp()))


    def test_error_helper_uses_runtime_status_envelope(self):
        self.assertEqual(
            error("预算不足", 429),
            {"status_code": 429, "body": {"error": "预算不足"}},
        )

    async def test_tencent_duration_is_normalized_from_minutes_to_seconds(self):
        places = [
            {"place_id": "a", "city": "City One", "latitude": 39.9, "longitude": 116.3},
            {"place_id": "b", "city": "City Two", "latitude": 39.8, "longitude": 116.4},
        ]
        response = {
            "result": {
                "routes": [{"distance": 4824, "duration": 24, "polyline": []}],
            },
        }
        with patch("agents._infrastructure.providers.tencent_location._get", AsyncMock(return_value=response)):
            route = await plan_driving_route("key", places)
        self.assertEqual(route["duration_seconds"], 24 * 60)
        self.assertEqual(route["schema_version"], 4)
        self.assertEqual(route["legs"][0]["scope"], "intercity")
        cached_places = [
            {key: value for key, value in place.items() if key != "city"}
            for place in places
        ]
        cached = normalize_route_contract({
            "provider": "tencent",
            "mode": "transit",
            "places": cached_places,
            "legs": [{
                "from": cached_places[0],
                "to": cached_places[1],
                "mode": "transit",
                "sections": [
                    {"mode": "walking"},
                    {"mode": "rail", "vehicle": "RAIL"},
                ],
            }],
            "transit": {"segments": [{"vehicle": "RAIL"}]},
        }, places)
        self.assertEqual(cached["legs"][0]["scope"], "intercity")
        self.assertEqual(cached["places"][0]["city"], places[0]["city"])
        self.assertEqual(cached["transit"]["modes"], ["rail", "walking"])

    async def test_tencent_taxi_fare_is_not_misreported_as_a_road_toll(self):
        places = [
            {"place_id": "a", "latitude": 39.9, "longitude": 116.3},
            {"place_id": "b", "latitude": 39.8, "longitude": 116.4},
        ]
        response = {"result": {"routes": [{
            "distance": 10_000,
            "duration": 30,
            "polyline": [],
            "toll": 0,
            "taxi_fare": {"fare": 50},
        }]}}
        with patch("agents._infrastructure.providers.tencent_location._get", AsyncMock(return_value=response)):
            route = await plan_driving_route("key", places)
        self.assertEqual(route["fare"]["self_driving"]["toll"], 0)
        self.assertEqual(route["fare"]["taxi"]["provider_estimate"], 50)
        self.assertLess(route["fare"]["taxi"]["low"], 50)
        self.assertGreater(route["fare"]["taxi"]["high"], 50)

    async def test_provider_collectors_keep_safe_weather_and_route_facts(self):
        now = int(time.time())
        place_a = {"place_id": "a", "latitude": 39.9, "longitude": 116.3}
        place_b = {"place_id": "b", "latitude": 39.8, "longitude": 116.4}
        schedules = [
            {"id": "a", "title": "A", "start_time": now + 3600, "duration_minutes": 30, "extra": {"place": place_a}},
            {"id": "b", "title": "B", "start_time": now + 5700, "duration_minutes": 30, "extra": {"place": place_b}},
        ]
        route = {"provider": "tencent", "duration_seconds": 1800, "distance_meters": 5000}
        weather = {"weather": "晴", "temperature": 28, "humidity": 55}
        with (
            patch("agents._application.proactive.service.get_current_weather", AsyncMock(return_value=weather)),
            patch("agents._application.proactive.service.plan_verified_route", AsyncMock(return_value=route)),
        ):
            signals, diagnostics = await collect_provider_signals({"TENCENT_MAP_KEY": "key"}, schedules, now)
        self.assertEqual(len(diagnostics["weather_facts"]), 2)
        self.assertEqual(diagnostics["route_facts"][0]["route_duration_seconds"], 1800)
        self.assertTrue(any(item["type"] == "route_risk" for item in signals))

if __name__ == "__main__":
    unittest.main()
