from __future__ import annotations

import copy
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from langchain_core.messages import AIMessageChunk

from agents._application.chat.turn_service import ChatTurnService
from agents._application.search.search_use_case import SearchExecution
from agents._domain.search.evidence import SearchEvidence, SearchSource
from agents._tests.auth_helpers import auth_env, auth_headers
from agents._tests.support.fakes import FakeCheckpointer, FakeStore
from agents.chat._capability_plan import DEFAULT_PLAN


class _ConversationStore:
    def __init__(self) -> None:
        self.langgraph_store = FakeStore()
        self.langgraph_checkpointer = FakeCheckpointer([])
        self.metadata: dict = {}

    async def append_message(self, **_values) -> None:
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
    async def astream(self, *_args, **_kwargs):
        yield AIMessageChunk(
            content="Production-like runtime matrix answer completed.",
        ), {}

    async def aget_state(self, _config):
        return SimpleNamespace(values={"messages": []})


class _SearchUseCase:
    def __init__(self, **_values) -> None:
        pass

    async def execute(self, request, *, on_media=None) -> SearchExecution:
        del on_media
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


def _plan(**updates) -> dict:
    return {**copy.deepcopy(DEFAULT_PLAN), **updates}


class ChatTurnRuntimeMatrixTests(unittest.IsolatedAsyncioTestCase):
    async def _run(
        self,
        name: str,
        plan: dict,
        *,
        planner_timed_out: bool = False,
    ) -> str:
        store = _ConversationStore()
        ctx = SimpleNamespace(
            conversation_id=f"runtime-{name}",
            run_id=f"run-{name}",
            store=store,
            request=SimpleNamespace(
                body={"message": f"exercise {name}"},
                headers=auth_headers(membership="plus"),
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
                "agents._application.chat.turn_service.effective_skill_preferences",
                return_value=enabled,
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
                "agents._application.chat.turn_service.SearchUseCase",
                new=_SearchUseCase,
            ),
            patch(
                "agents._application.chat.turn_service.build_graph",
                return_value=_AnswerGraph(),
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
        return wire

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


if __name__ == "__main__":
    unittest.main()
