from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from services.model_gateway import ModelChunk, ProviderUsage
from skills.chat_skill import ChatSkill
from skills.paper_skill import PaperSkill
from skills.search_skill import SearchSkill


class FakeGateway:
    def __init__(self) -> None:
        self.requests = []

    async def stream_text(self, request, context, cancellation=None):
        self.requests.append(request)
        del context, cancellation
        yield ModelChunk(delta="第一段")
        yield ModelChunk(delta="第二段")
        yield ModelChunk(
            done=True,
            provider="fake",
            model="fake-model",
            usage=ProviderUsage(input_tokens=10, output_tokens=4, total_tokens=14),
            provider_request_id="req-fake",
        )


class StreamingSkillTests(unittest.IsolatedAsyncioTestCase):
    async def test_chat_skill_uses_structured_media_for_web_assisted_answers(self) -> None:
        gateway = FakeGateway()
        skill = ChatSkill(gateway)
        search_result = {
            "results": [{
                "source": "web",
                "title": "故宫介绍",
                "snippet": "故宫位于北京。",
                "url": "https://example.test/palace",
            }],
            "images": ["https://cdn.example.test/palace.jpg"],
            "image_descriptions": [],
            "media": [{
                "id": "media-1",
                "url": "https://cdn.example.test/palace.jpg",
                "source_id": "source-1",
                "source_url": "https://example.test/palace",
                "source_title": "故宫介绍",
                "alt": "故宫外景",
                "caption": "故宫外景",
            }],
            "source_references": [{
                "id": "source-1",
                "source": "web",
                "title": "故宫介绍",
                "snippet": "故宫位于北京。",
                "url": "https://example.test/palace",
            }],
            "sources_used": ["web"],
        }
        with (
            patch("services.search_system.search", new=AsyncMock(return_value=search_result)),
            patch.object(skill, "_generate_follow_ups", new=AsyncMock(return_value=[])),
        ):
            events = [
                event
                async for event in skill.stream(
                    "给我介绍一下北京故宫",
                    {"web_search": True},
                    "default-conversation",
                    [],
                    run_id="run-chat",
                )
            ]

        prompt = "\n".join(message["content"] for message in gateway.requests[0].messages)
        self.assertIn("media-1", prompt)
        self.assertNotIn("https://cdn.example.test/palace.jpg", prompt)
        self.assertEqual(events[-1].data["search_results"]["media"][0]["id"], "media-1")

    async def test_search_skill_emits_progress_sources_and_final_answer(self) -> None:
        skill = SearchSkill(FakeGateway())
        search_result = {
            "results": [
                {
                    "source": "web",
                    "title": "Agent Architecture",
                    "snippet": "event run action",
                    "url": "https://example.test/agent",
                    "site": "example.test",
                }
            ],
            "images": [],
            "image_descriptions": [],
            "media": [],
            "source_references": [
                {
                    "id": "source-1",
                    "source": "web",
                    "title": "Agent Architecture",
                    "snippet": "event run action",
                    "url": "https://example.test/agent",
                }
            ],
            "sources_used": ["web"],
        }
        with patch("services.search_system.search", new=AsyncMock(return_value=search_result)):
            events = [
                event
                async for event in skill.stream(
                    "搜索 Agent 架构",
                    {"query": "Agent 架构"},
                    "default-conversation",
                    [],
                    run_id="run-search",
                )
            ]
        self.assertEqual(events[0].event_type, "search_status")
        self.assertEqual(events[1].data["status"], "thinking")
        self.assertEqual("".join(event.delta for event in events), "第一段第二段")
        self.assertTrue(events[-1].done)
        self.assertEqual(events[-1].data["search_results"]["total"], 1)

    async def test_paper_skill_reuses_service_without_local_http_call(self) -> None:
        skill = PaperSkill(FakeGateway())
        papers = [
            {
                "title": "A Proactive Agent",
                "arxiv_id": "2601.00001",
                "authors": "A. Author",
                "year": 2026,
                "abstract_zh": "主动式智能体架构。",
                "key_contribution": "事件驱动执行。",
                "arxiv_url": "https://arxiv.org/abs/2601.00001",
                "pdf_url": "https://arxiv.org/pdf/2601.00001.pdf",
            }
        ]
        with patch(
            "services.paper_search_service._search_arxiv_sync",
            return_value=papers,
        ):
            events = [
                event
                async for event in skill.stream(
                    "找主动式 Agent 论文",
                    {"topic": "proactive agent", "max_results": 3},
                    "default-conversation",
                    [],
                    run_id="run-paper",
                )
            ]
        self.assertEqual(events[0].event_type, "paper_status")
        self.assertTrue(events[-1].done)
        self.assertEqual(events[-1].data["papers"][0]["arxiv_id"], "2601.00001")
        self.assertEqual("".join(event.delta for event in events), "第一段第二段")


if __name__ == "__main__":
    unittest.main()
