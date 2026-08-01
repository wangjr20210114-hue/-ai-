from __future__ import annotations

import ast
import builtins
import inspect
import unittest
from pathlib import Path

from agents._application.chat import turn_service as turn_service_module
from agents._application.chat.turn_context import (
    answer_tool_names,
    model_only_search_fallback,
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

    def test_runtime_search_failure_becomes_plain_model_fallback(self):
        original = {
            "needs_web_search": True,
            "needs_images": True,
            "needs_image_generation": False,
            "_capabilities": ["web_search"],
        }

        fallback = model_only_search_fallback(original)

        self.assertTrue(original["needs_web_search"])
        self.assertFalse(fallback["needs_web_search"])
        self.assertFalse(fallback["needs_images"])
        self.assertEqual(fallback["_capabilities"], [])
        self.assertIn(
            "web-search",
            fallback["_runtime_model_fallback_skills"],
        )
        prompt = turn_service_module.dynamic_system_prompt(
            selected_tools=set(),
            now="2026-08-01 18:00 Asia/Shanghai",
            response_language_instruction="请使用简体中文回答。",
            capability_plan=fallback,
            calendar_context="",
            reference_image_context="",
            document_context="",
            current_location_context="",
            current_route_context="",
            memory_context="",
            public_answer=True,
        )
        self.assertIn("实时搜索不可用", prompt)
        self.assertIn("不能要求用户安装", prompt)

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

    def test_turn_service_imports_its_search_evidence_annotation(self):
        service_path = (
            Path(__file__).parents[2]
            / "_application"
            / "chat"
            / "turn_service.py"
        )
        tree = ast.parse(service_path.read_text(encoding="utf-8"))
        imported_names = {
            alias.asname or alias.name
            for node in tree.body
            if isinstance(node, ast.ImportFrom)
            for alias in node.names
        }

        self.assertIn("SearchEvidence", imported_names)

    def test_progressive_media_call_matches_the_domain_contract(self):
        service_path = (
            Path(__file__).parents[2]
            / "_application"
            / "chat"
            / "turn_service.py"
        )
        tree = ast.parse(service_path.read_text(encoding="utf-8"))
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "progressive_media_for_plan"
        ]

        self.assertEqual(len(calls), 1)
        self.assertEqual(len(calls[0].args), 1)
        self.assertEqual(
            [keyword.arg for keyword in calls[0].keywords],
            ["planner_timed_out"],
        )

    def test_runtime_annotations_resolve_from_module_scope(self):
        service_path = Path(turn_service_module.__file__)
        tree = ast.parse(service_path.read_text(encoding="utf-8"))
        module_names = set(vars(builtins))
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                module_names.add(node.name)
            elif isinstance(node, ast.Import):
                module_names.update(
                    alias.asname or alias.name.split(".")[0]
                    for alias in node.names
                )
            elif isinstance(node, ast.ImportFrom):
                module_names.update(alias.asname or alias.name for alias in node.names)
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                module_names.update(
                    target.id for target in targets if isinstance(target, ast.Name)
                )

        annotation_nodes = []
        for node in ast.walk(tree):
            if isinstance(node, ast.arg) and node.annotation is not None:
                annotation_nodes.append(node.annotation)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.returns is not None:
                annotation_nodes.append(node.returns)
            elif isinstance(node, ast.AnnAssign):
                annotation_nodes.append(node.annotation)
        referenced = {
            child.id
            for annotation in annotation_nodes
            for child in ast.walk(annotation)
            if isinstance(child, ast.Name)
        }

        self.assertEqual(referenced - module_names, set())

    def test_direct_runtime_calls_bind_to_their_current_contracts(self):
        service_path = Path(turn_service_module.__file__)
        tree = ast.parse(service_path.read_text(encoding="utf-8"))
        failures = []
        for call in (node for node in ast.walk(tree) if isinstance(node, ast.Call)):
            if not isinstance(call.func, ast.Name):
                continue
            target = getattr(turn_service_module, call.func.id, None)
            if not callable(target):
                continue
            if any(isinstance(argument, ast.Starred) for argument in call.args):
                continue
            if any(keyword.arg is None for keyword in call.keywords):
                continue
            try:
                signature = inspect.signature(target)
            except (TypeError, ValueError):
                continue
            try:
                signature.bind(
                    *([None] * len(call.args)),
                    **{keyword.arg: None for keyword in call.keywords},
                )
            except TypeError as exc:
                failures.append(
                    f"{call.func.id} at line {call.lineno}: {exc}"
                )

        self.assertEqual(failures, [])


if __name__ == "__main__":
    unittest.main()
