from __future__ import annotations

import ast
import unittest
from pathlib import Path

from agents._application.chat.turn_context import (
    answer_tool_names,
    search_request_for_plan,
)


IDENTITY = {
    "tenant_id": "tenant-a",
    "subject_id": "user-a",
    "auth_type": "wechat",
    "membership": "plus",
}


class ChatTurnBoundaryTests(unittest.TestCase):
    def test_controller_is_a_bounded_delegate_without_runtime_dependencies(self):
        controller_path = (
            Path(__file__).parents[2]
            / "_application"
            / "chat"
            / "turn_controller.py"
        )
        source = controller_path.read_text(encoding="utf-8")

        self.assertLessEqual(len(source.splitlines()), 100)
        self.assertIn("ChatTurnService(ctx)", source)
        self.assertNotIn("_infrastructure", source)
        self.assertNotIn("SearchPro", source)

    def test_planned_search_is_not_an_answer_graph_tool(self):
        self.assertEqual(
            answer_tool_names(("rich_search", "search_arxiv")),
            ("search_arxiv",),
        )

    def test_search_request_uses_signed_identity_and_entitlement_depth(self):
        request = search_request_for_plan(
            {
                "needs_web_search": True,
                "needs_images": True,
                "search_query": "Floris 最新架构",
                "image_query": "Floris 界面",
            },
            IDENTITY,
            conversation_id="conversation-a",
            user_message="请查资料",
            current_date="2026-07-31",
            result_limit=8,
            image_limit=4,
            parallel_queries=True,
            vision_enabled=True,
            force_refresh=False,
        )

        self.assertIsNotNone(request)
        assert request is not None
        self.assertEqual(request.tenant_id, "tenant-a")
        self.assertEqual(request.user_id, "user-a")
        self.assertEqual(request.depth, "deep")
        self.assertEqual(request.media_mode, "progressive")

    def test_image_generation_keeps_reviewed_media_blocking(self):
        request = search_request_for_plan(
            {
                "needs_web_search": True,
                "needs_images": True,
                "needs_image_generation": True,
                "search_query": "真实物体",
            },
            IDENTITY,
            conversation_id="conversation-a",
            user_message="参考真实物体生图",
            current_date="2026-07-31",
            result_limit=8,
            image_limit=3,
            parallel_queries=True,
            vision_enabled=True,
            force_refresh=False,
        )

        self.assertEqual(request.media_mode, "blocking")

    def test_route_adapter_is_thin_and_has_no_provider_imports(self):
        route_path = Path(__file__).parents[2] / "chat" / "index.py"
        source = route_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        handler = next(
            node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "handler"
        )

        self.assertLessEqual(len(handler.body), 2)
        self.assertNotIn("SearchPro", source)
        self.assertNotIn("_infrastructure.providers", source)

    def test_production_controller_preexecutes_search_and_filters_answer_tools(self):
        controller_path = (
            Path(__file__).parents[2]
            / "_application"
            / "chat"
            / "turn_service.py"
        )
        source = controller_path.read_text(encoding="utf-8")

        self.assertIn("search_use_case.execute(", source)
        self.assertIn("answer_tool_names(", source)


if __name__ == "__main__":
    unittest.main()
