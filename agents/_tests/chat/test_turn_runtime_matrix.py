from __future__ import annotations

import asyncio
import copy
import time
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from langchain_core.messages import AIMessageChunk, ToolMessage

from agents._application.chat.turn_service import ChatTurnService
from agents._application.skills.access import (
    resolve_skill_access as resolve_test_skill_access,
)
from agents._application.search.search_use_case import SearchExecution
from agents._domain.search.evidence import (
    ReviewedMedia,
    SearchEvidence,
    SearchSource,
)
from agents._tests.auth_helpers import auth_env, auth_headers
from agents._tests.support.fakes import FakeCheckpointer, FakeStore
from agents.chat._capability_plan import DEFAULT_PLAN


class _ConversationStore:
    def __init__(self) -> None:
        self.langgraph_store = FakeStore()
        self.langgraph_checkpointer = FakeCheckpointer([])
        self.metadata: dict = {}
        self.append_count = 0

    async def append_message(self, **_values) -> None:
        self.append_count += 1
        return None

    async def get_conversation(self, **_values) -> dict:
        return {"metadata": copy.deepcopy(self.metadata)}

    async def update_conversation(self, *, metadata: dict, **_values) -> None:
        self.metadata.update(copy.deepcopy(metadata))


class _Utils:
    @staticmethod
    def stream_sse(stream):
        return stream

    @staticmethod
    def abortActiveRun(_conversation_id: str) -> None:
        return None


class _AnswerGraph:
    last_tool_names: tuple[str, ...] = ()

    def __init__(self, tools=()) -> None:
        self.tools = list(tools)
        type(self).last_tool_names = tuple(
            str(getattr(tool, "name", "") or "")
            for tool in self.tools
        )

    async def astream(self, *_args, **_kwargs):
        rich_search = next(
            (
                tool
                for tool in self.tools
                if getattr(tool, "name", "") == "rich_search"
            ),
            None,
        )
        if rich_search is not None:
            try:
                content = await rich_search.ainvoke({"query": "planned query"})
            except Exception as exc:
                content = str(exc)
            yield ToolMessage(
                content=content,
                name="rich_search",
                tool_call_id="runtime-rich-search",
            ), {}
        yield AIMessageChunk(
            content="Production-like runtime matrix answer completed.",
        ), {}

    async def aget_state(self, _config):
        return SimpleNamespace(values={"messages": []})


class _SearchUseCase:
    execute_count = 0

    def __init__(self, **_values) -> None:
        pass

    async def execute(self, request, *, on_media=None) -> SearchExecution:
        del on_media
        type(self).execute_count += 1
        return SearchExecution(
            evidence=SearchEvidence(
                query=request.query,
                sources=(SearchSource(
                    id="source-runtime-1",
                    title="Runtime source",
                    url="https://example.com/runtime",
                    snippet="Verified runtime evidence.",
                ),),
                total=1,
            ),
            provider_request_count=0,
        )


class _FailingSearchUseCase:
    def __init__(self, **_values) -> None:
        pass

    async def execute(self, request, *, on_media=None) -> SearchExecution:
        del request, on_media
        raise TimeoutError("search provider timed out")


class _ProgressiveSearchUseCase:
    execute_count = 0

    def __init__(self, **_values) -> None:
        pass

    async def execute(self, request, *, on_media=None) -> SearchExecution:
        type(self).execute_count += 1
        source = SearchSource(
            id="source-runtime-1",
            title="Runtime source",
            url="https://example.com/runtime",
            snippet="Verified runtime evidence.",
        )
        enriched = SearchEvidence(
            query=request.query,
            sources=(source,),
            media=(ReviewedMedia(
                id="media-runtime-1",
                url="https://img.example.com/runtime.jpg",
                source_id=source.id,
                source_url=source.url,
                vision_reviewed=True,
            ),),
            total=1,
        )

        async def publish_media() -> SearchEvidence:
            await asyncio.sleep(0)
            if on_media is not None:
                await on_media(enriched)
            return enriched

        return SearchExecution(
            evidence=SearchEvidence(
                query=request.query,
                sources=(source,),
                total=1,
                media_pending=True,
            ),
            media_tasks=(asyncio.create_task(publish_media()),),
            provider_request_count=1,
        )


def _plan(**updates) -> dict:
    return {**copy.deepcopy(DEFAULT_PLAN), **updates}


class ChatTurnRuntimeMatrixTests(unittest.IsolatedAsyncioTestCase):
    async def _run(
        self,
        name: str,
        plan: dict,
        *,
        planner_timed_out: bool = False,
        store: _ConversationStore | None = None,
        conversation_id: str = "",
        body_updates: dict | None = None,
        enabled_preferences: dict[str, bool] | None = None,
        identity: dict | None = None,
        search_use_case_type=_SearchUseCase,
    ) -> tuple[str, _ConversationStore]:
        store = store or _ConversationStore()
        ctx = SimpleNamespace(
            conversation_id=conversation_id or f"runtime-{name}",
            run_id=f"run-{name}",
            store=store,
            request=SimpleNamespace(
                body={
                    "message": f"exercise {name}",
                    **(body_updates or {}),
                },
                headers=auth_headers(**(identity or {"membership": "plus"})),
            ),
            env=auth_env(),
            utils=_Utils(),
            tracer=None,
        )
        enabled = {
            "core": True,
            "web-search": True,
            "maps": True,
            "calendar": True,
            "paper-assistant": True,
            "image-generation": True,
            "vision-analysis": True,
            "workflow-action": True,
            "meeting-action": True,
        }

        with (
            patch(
                "agents._application.chat.turn_service.get_model",
                return_value=object(),
            ),
            patch(
                "agents._application.chat.turn_service.plan_capabilities_bounded",
                new=AsyncMock(return_value=(plan, planner_timed_out)),
            ),
            patch(
                "agents._application.chat.turn_service.resolve_skill_access",
                side_effect=lambda identity, _preferences: resolve_test_skill_access(
                    identity,
                    enabled_preferences or enabled,
                ),
            ),
            patch(
                "agents._application.chat.turn_service.load_user_workspace",
                new=AsyncMock(return_value={}),
            ),
            patch(
                "agents._application.chat.turn_service.load_proactive_state",
                new=AsyncMock(return_value={}),
            ),
            patch(
                "agents._application.chat.turn_search.SearchUseCase",
                new=search_use_case_type,
            ),
            patch(
                "agents._application.chat.turn_service.build_graph",
                side_effect=(
                    lambda _model, tools, *_args, **_kwargs: _AnswerGraph(tools)
                ),
            ),
            patch(
                "agents._application.chat.turn_service.should_generate_followups",
                return_value=False,
            ),
        ):
            stream = await ChatTurnService(ctx).handle()
            frames = [frame async for frame in stream]

        wire = b"".join(frames).decode("utf-8")
        self.assertIn("[DONE]", wire, name)
        self.assertNotIn("event: error", wire, name)
        self.assertEqual(
            store.metadata["yuanbao_chat_run_v1"]["status"],
            "completed",
            name,
        )
        return wire, store

    async def test_guest_search_plan_falls_back_to_model_without_install_prompt(self):
        _SearchUseCase.execute_count = 0
        enabled = {
            "core": True,
            "web-search": False,
            "proactive-agent": True,
        }
        wire, _ = await self._run(
            "guest-search-fallback",
            _plan(
                needs_web_search=True,
                search_query="最近 AI 有什么新进展",
                _capabilities=["web_search"],
            ),
            enabled_preferences=enabled,
            identity={"auth_type": "guest", "membership": "guest"},
            body_updates={"message": "最近 AI 有什么新进展"},
        )
        self.assertIn("Production-like runtime matrix answer completed.", wire)
        self.assertNotIn("Skills 广场", wire)
        self.assertNotIn("安装", wire)
        self.assertEqual(_SearchUseCase.execute_count, 0)

    async def test_guest_search_discards_planner_clarification_card(self):
        _SearchUseCase.execute_count = 0
        enabled = {
            "core": True,
            "web-search": False,
            "proactive-agent": True,
        }
        wire, _ = await self._run(
            "guest-search-clarification-fallback",
            _plan(
                needs_clarification=True,
                clarification_title="AI progress scope",
                clarification_prompt="Choose one category first.",
                clarification_fields=[{
                    "id": "scope",
                    "label": "Category",
                    "type": "single",
                    "required": True,
                    "options": ["language models", "images", "coding"],
                }],
                needs_web_search=True,
                search_query="recent AI progress",
                _capabilities=["web_search"],
            ),
            enabled_preferences=enabled,
            identity={"auth_type": "guest", "membership": "guest"},
            body_updates={"message": "What is new in AI?"},
        )

        self.assertIn("Production-like runtime matrix answer completed.", wire)
        self.assertNotIn("clarification_action", wire)
        self.assertNotIn("ask_user_clarification", wire)
        self.assertNotIn("AI progress scope", wire)
        self.assertIn('"kind":"freshness"', wire)
        self.assertIn('"login_required":true', wire)
        self.assertEqual(_SearchUseCase.execute_count, 0)
        self.assertEqual(_AnswerGraph.last_tool_names, ())

    async def test_user_disabled_search_degrades_without_login_prompt(self):
        _SearchUseCase.execute_count = 0
        enabled = {
            "core": True,
            "web-search": False,
            "proactive-agent": True,
        }
        wire, _ = await self._run(
            "user-disabled-search",
            _plan(
                needs_clarification=True,
                clarification_title="Search scope",
                clarification_prompt="Choose a scope.",
                clarification_fields=[{
                    "id": "scope",
                    "label": "Scope",
                    "type": "single",
                    "required": True,
                    "options": ["A", "B"],
                }],
                needs_web_search=True,
                search_query="recent AI progress",
                _capabilities=["web_search"],
            ),
            enabled_preferences=enabled,
            identity={"auth_type": "cloudbase", "membership": "free"},
        )

        self.assertIn("Production-like runtime matrix answer completed.", wire)
        self.assertNotIn("clarification_action", wire)
        self.assertIn('"kind":"freshness"', wire)
        self.assertIn('"login_required":false', wire)
        self.assertEqual(_SearchUseCase.execute_count, 0)
        self.assertEqual(_AnswerGraph.last_tool_names, ())

    async def test_authenticated_clarification_tool_remains_available(self):
        await self._run(
            "authenticated-clarification",
            _plan(
                needs_clarification=True,
                clarification_title="Required side-effect target",
                clarification_prompt="Choose the target.",
                clarification_fields=[{
                    "id": "target",
                    "label": "Target",
                    "type": "single",
                    "required": True,
                    "options": ["A", "B"],
                }],
            ),
        )

        self.assertEqual(
            _AnswerGraph.last_tool_names,
            ("ask_user_clarification",),
        )

    async def test_runtime_search_failure_keeps_main_tool_result_boundary(self):
        wire, _ = await self._run(
            "runtime-search-fallback",
            _plan(
                needs_web_search=True,
                search_query="recent AI progress",
                _capabilities=["web_search"],
            ),
            search_use_case_type=_FailingSearchUseCase,
        )

        self.assertIn("Production-like runtime matrix answer completed.", wire)
        self.assertNotIn('"type":"search_results"', wire)
        self.assertNotIn("event: error", wire)

    async def test_successful_search_publishes_measured_search_time(self):
        wire, _ = await self._run(
            "runtime-search-timing",
            _plan(
                needs_web_search=True,
                search_query="recent AI progress",
                _capabilities=["web_search"],
            ),
        )

        self.assertRegex(wire, r'"timings_ms":\{"search":\d+\}')

    async def test_cloudbase_search_streams_sources_and_bound_media_once(self):
        _ProgressiveSearchUseCase.execute_count = 0
        wire, store = await self._run(
            "cloudbase-progressive-search",
            _plan(
                needs_web_search=True,
                needs_images=True,
                search_query="recent AI progress",
                image_query="AI launch event",
                _capabilities=["web_search"],
            ),
            identity={"auth_type": "cloudbase", "membership": "free"},
            search_use_case_type=_ProgressiveSearchUseCase,
        )

        self.assertEqual(_ProgressiveSearchUseCase.execute_count, 1)
        self.assertEqual(wire.count('"type":"search_results"'), 1)
        self.assertEqual(wire.count('"type":"search_media"'), 1)
        self.assertIn('"source_id":"source-runtime-1"', wire)
        self.assertIn('"vision_reviewed":true', wire)
        self.assertLess(wire.index("event: sources"), wire.index("event: token"))
        self.assertLess(wire.index("event: media"), wire.index("data: [DONE]"))
        self.assertNotIn('"login_required":true', wire)
        extras = [
            value
            for (namespace, key), value in store.langgraph_store.values.items()
            if key == "latest_extras" and namespace
        ]
        self.assertEqual(len(extras), 1)
        persisted = extras[0]["search_results"]
        self.assertEqual(persisted["results"][0]["id"], "source-runtime-1")
        self.assertEqual(
            persisted["media"][0]["source_id"],
            "source-runtime-1",
        )

    async def test_representative_plans_construct_tools_and_finish_streams(self):
        plans = {
            "general": _plan(),
            "search_media": _plan(
                needs_web_search=True,
                needs_images=True,
                search_query="current architecture",
                image_query="architecture diagram",
            ),
            "map": _plan(
                needs_places=True,
                needs_map_action=True,
            ),
            "calendar": _plan(
                needs_calendar_context=True,
                needs_calendar_action=True,
            ),
            "route": _plan(
                needs_route=True,
                route_stops=[
                    {"query": "Origin", "near_query": ""},
                    {"query": "Destination", "near_query": ""},
                ],
            ),
            "route_calendar": _plan(
                needs_route=True,
                needs_calendar_context=True,
                needs_calendar_action=True,
                route_stops=[
                    {"query": "Origin", "near_query": ""},
                    {"query": "Destination", "near_query": ""},
                ],
            ),
            "paper": _plan(
                needs_papers=True,
                paper_topic="agent architecture",
            ),
            "image": _plan(needs_image_generation=True),
            "workflow": _plan(needs_workflow_action=True),
            "meeting": _plan(needs_meeting_action=True),
            "clarification": _plan(
                needs_clarification=True,
                clarification_title="Required detail",
                clarification_prompt="Provide the missing detail.",
                clarification_fields=[{
                    "id": "detail",
                    "label": "Detail",
                    "type": "text",
                    "required": True,
                }],
            ),
            "location_permission": _plan(needs_current_location=True),
            "planner_timeout": _plan(_prompt_topics=["web"]),
        }

        for name, plan in plans.items():
            with self.subTest(plan=name):
                await self._run(
                    name,
                    plan,
                    planner_timed_out=name == "planner_timeout",
                )

    async def test_location_retry_closes_the_first_run_and_persists_once(self):
        store = _ConversationStore()
        conversation_id = "runtime-location-retry"
        location_plan = _plan(needs_current_location=True)

        first_wire, _ = await self._run(
            "location-first",
            location_plan,
            store=store,
            conversation_id=conversation_id,
            body_updates={"message": "Where am I?"},
        )
        self.assertIn("browser_location_request", first_wire)
        self.assertEqual(store.append_count, 1)
        self.assertEqual(
            store.metadata["yuanbao_chat_run_v1"]["status"],
            "completed",
        )

        retry_wire, _ = await self._run(
            "location-second",
            location_plan,
            store=store,
            conversation_id=conversation_id,
            body_updates={
                "message": "Where am I?",
                "_location_retry": True,
                "location_request": {"state": "granted"},
                "current_location": {
                    "latitude": 39.9042,
                    "longitude": 116.4074,
                    "accuracy_meters": 20,
                    "captured_at": int(time.time() * 1000),
                    "coordinate_type": "wgs84",
                },
            },
        )
        self.assertNotIn("event: error", retry_wire)
        self.assertEqual(store.append_count, 1)
        self.assertEqual(
            store.metadata["yuanbao_chat_run_v1"]["status"],
            "completed",
        )


if __name__ == "__main__":
    unittest.main()
