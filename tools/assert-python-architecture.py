"""Repository architecture gate for Python Agent layers."""

from __future__ import annotations

import ast
import re
import runpy
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AGENTS = ROOT / "agents"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
MAX_TEST_FILE_LINES = 750
MAX_PRODUCTION_FILE_LINES = 2_500
CRITICAL_FILE_LIMITS = {
    "_application/chat/turn_service.py": 1_500,
    "chat/_graph.py": 1_350,
    "chat/_capability_plan.py": 1_350,
}
FORBIDDEN_DOMAIN_PARTS = {
    "_application",
    "_controllers",
    "_infrastructure",
    "_presenters",
    "pages_agents",
    "pages_blob",
    "requests",
    "urllib",
}
LOCALIZED_CHAT_BOUNDARIES = (
    "_application/chat/turn_admission.py",
    "_application/chat/turn_policy.py",
    "_application/chat/turn_protocol.py",
    "_application/chat/turn_service.py",
    "chat/_capability_plan.py",
    "chat/_fallbacks.py",
    "chat/_followups.py",
    "chat/_graph.py",
    "chat/_protocol.py",
    "_controllers/reader_controller.py",
    "_controllers/messages_controller.py",
    "_controllers/system_controller.py",
    "_controllers/workspace_controller.py",
    "_infrastructure/skills/builtin_operations.py",
    "_infrastructure/skills/calendar_operations.py",
    "_infrastructure/skills/nearby_operations.py",
    "_infrastructure/skills/place_operations.py",
    "_infrastructure/skills/route_operations.py",
    "_infrastructure/skills/route_resolution.py",
    "_application/chat/turn_io.py",
    "_application/search/evidence_presenter.py",
    "_application/skills/component_api.py",
    "_application/workspace/service.py",
    "_infrastructure/makers/identity.py",
    "_infrastructure/makers/conversation_repository.py",
    "_infrastructure/providers/arxiv.py",
    "_infrastructure/providers/web_media.py",
    "_infrastructure/skills/paper_candidates.py",
    "_infrastructure/skills/paper_operations.py",
    "_infrastructure/skills/search_operations.py",
    "_presenters/chat_stream.py",
    "_skill_adapters/core/adapter.py",
)
NON_PRESENTATION_PROVIDER_LITERALS = {"全国", "中国"}


def imported_modules(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            modules.append(node.module or "")
    return modules


def literal_copy_violations(path: Path) -> list[int]:
    """Catch model-facing literals even when their source language is English."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            for keyword in node.keywords:
                if keyword.arg == "description" and isinstance(
                    keyword.value, (ast.Constant, ast.JoinedStr),
                ):
                    lines.add(node.lineno)
            function_name = (
                node.func.id
                if isinstance(node.func, ast.Name)
                else node.func.attr
                if isinstance(node.func, ast.Attribute)
                else ""
            )
            if function_name in {"SystemMessage", "HumanMessage"}:
                content_values = list(node.args[:1]) + [
                    keyword.value
                    for keyword in node.keywords
                    if keyword.arg == "content"
                ]
                if any(
                    isinstance(value, (ast.Constant, ast.JoinedStr))
                    for value in content_values
                ):
                    lines.add(node.lineno)
        if isinstance(node, ast.Dict):
            values = {
                key.value: value
                for key, value in zip(node.keys, node.values)
                if isinstance(key, ast.Constant) and isinstance(key.value, str)
            }
            role = values.get("role")
            content = values.get("content")
            if (
                isinstance(role, ast.Constant)
                and role.value in {"system", "user", "human"}
                and isinstance(content, (ast.Constant, ast.JoinedStr))
            ):
                lines.add(node.lineno)
        if isinstance(node, ast.Assign) and isinstance(
            node.value, (ast.Constant, ast.JoinedStr),
        ):
            names = {
                target.id for target in node.targets
                if isinstance(target, ast.Name)
            }
            if names & {"prompt", "system_prompt", "instruction", "instructions"}:
                lines.add(node.lineno)
    return sorted(lines)


def main() -> None:
    failures: list[str] = []
    i18n_namespace = runpy.run_path(str(AGENTS / "_application" / "i18n.py"))
    backend_catalog = i18n_namespace["CATALOG"]
    supported_languages = i18n_namespace["SUPPORTED_LANGUAGES"]
    if len(supported_languages) != 5 or len(set(supported_languages)) != 5:
        failures.append("backend i18n must declare five distinct product languages")
    for key, entry in backend_catalog.items():
        if len(entry) != len(supported_languages) or not all(
            isinstance(value, str) and value.strip() for value in entry
        ):
            failures.append(
                f"backend i18n entry {key!r} must provide every product language"
            )
    for relative in LOCALIZED_CHAT_BOUNDARIES:
        path = AGENTS / relative
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        hardcoded = sorted({
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and re.search(r"[\u3400-\u9fff]", node.value)
            and node.value not in NON_PRESENTATION_PROVIDER_LITERALS
        })
        if hardcoded:
            failures.append(
                f"{path.relative_to(ROOT)} contains user/model copy outside "
                f"agents/_application/i18n.py: {hardcoded[:3]}"
            )
    for path in AGENTS.rglob("*.py"):
        if "_tests" in path.parts or path.name in {"i18n.py", "i18n_catalogs.py"}:
            continue
        violation_lines = literal_copy_violations(path)
        if violation_lines:
            failures.append(
                f"{path.relative_to(ROOT)} contains literal model/schema copy "
                f"outside backend i18n at lines {violation_lines[:5]}"
            )
    shared = AGENTS / "_shared"
    if shared.exists():
        failures.append("agents/_shared must not exist")
    if (AGENTS / "_domain" / "skills" / "policy.py").exists():
        failures.append("the duplicate Skill policy must not shadow entitlements policy")

    legacy_workspace_suite = AGENTS / "_tests" / "test_workspace.py"
    if legacy_workspace_suite.exists():
        failures.append("agents/_tests/test_workspace.py must remain split by domain")

    legacy_stream_view = AGENTS / "_views" / "chat_progress.py"
    if legacy_stream_view.exists():
        failures.append(
            "agents/_views/chat_progress.py must not shadow the StreamPresenter"
        )

    legacy_chat_controller = (
        AGENTS / "_application" / "chat" / "turn_controller.py"
    )
    if legacy_chat_controller.exists():
        failures.append(
            "application turn_controller.py must not shadow the controller layer"
        )

    chat_turn_service = AGENTS / "_application" / "chat" / "turn_service.py"
    chat_turn_tree = ast.parse(
        chat_turn_service.read_text(encoding="utf-8"),
        filename=str(chat_turn_service),
    )
    turn_service_lines = len(chat_turn_service.read_text(encoding="utf-8").splitlines())
    if turn_service_lines > CRITICAL_FILE_LIMITS["_application/chat/turn_service.py"]:
        failures.append(
            "turn_service.py must keep admission and presentation responsibilities "
            f"split out ({turn_service_lines}/1500)"
        )
    if not (AGENTS / "_application" / "chat" / "turn_admission.py").exists():
        failures.append("chat request/run admission must remain outside turn_service.py")
    if any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "frame"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "presenter"
        for node in ast.walk(chat_turn_tree)
    ):
        failures.append(
            "turn_service.py must emit typed ChatStreamPresenter events, "
            "not assemble raw presenter.frame payloads"
        )

    skill_registry = AGENTS / "_application" / "skills" / "registry.py"
    skill_runtime = AGENTS / "_application" / "skills" / "runtime.py"
    skill_registry_tree = ast.parse(
        skill_registry.read_text(encoding="utf-8"),
        filename=str(skill_registry),
    )
    runtime_declarations = {
        "_runtime_root_package",
        "_runtime_module_name",
        "SkillRuntimeContext",
        "build_adapter_tools",
        "run_preference_hooks",
    }
    registry_runtime_shadows = {
        node.name
        for node in skill_registry_tree.body
        if isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
        )
        and node.name in runtime_declarations
    }
    if registry_runtime_shadows:
        failures.append(
            "skills/registry.py must not shadow trusted runtime declarations: "
            f"{sorted(registry_runtime_shadows)}"
        )
    registry_lines = len(
        skill_registry.read_text(encoding="utf-8").splitlines()
    )
    runtime_lines = len(
        skill_runtime.read_text(encoding="utf-8").splitlines()
    )
    if registry_lines > 750 or runtime_lines > 450:
        failures.append(
            "Skill manifest and runtime responsibilities must remain split "
            f"(registry={registry_lines}/750, runtime={runtime_lines}/450)"
        )

    skill_assembler = (
        AGENTS / "_infrastructure" / "skills" / "builtin_operations.py"
    )
    skill_assembler_lines = len(
        skill_assembler.read_text(encoding="utf-8").splitlines()
    )
    if skill_assembler_lines > 500:
        failures.append(
            "builtin_operations.py must keep map/place/nearby/route/calendar "
            f"responsibilities split out ({skill_assembler_lines} lines; maximum 500)"
        )

    for path in (AGENTS / "_tests").rglob("test_*.py"):
        line_count = len(path.read_text(encoding="utf-8").splitlines())
        if line_count > MAX_TEST_FILE_LINES:
            failures.append(
                f"{path.relative_to(ROOT)} has {line_count} lines "
                f"(maximum {MAX_TEST_FILE_LINES})"
            )

    for path in AGENTS.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        if "_tests" not in path.parts:
            line_count = len(path.read_text(encoding="utf-8").splitlines())
            relative = path.relative_to(AGENTS).as_posix()
            critical_limit = CRITICAL_FILE_LIMITS.get(relative)
            if critical_limit is not None and line_count > critical_limit:
                failures.append(
                    f"{path.relative_to(ROOT)} has {line_count} lines "
                    f"(critical maximum {critical_limit})"
                )
            if line_count > MAX_PRODUCTION_FILE_LINES:
                failures.append(
                    f"{path.relative_to(ROOT)} has {line_count} lines "
                    f"(production maximum {MAX_PRODUCTION_FILE_LINES})"
                )
        for module in imported_modules(path):
            if "_shared" in module:
                failures.append(f"{path.relative_to(ROOT)} imports removed {module}")

    for path in (AGENTS / "_skill_adapters").rglob("*.py"):
        for module in imported_modules(path):
            if "_infrastructure" in module:
                failures.append(
                    f"{path.relative_to(ROOT)} trusted adapter imports infrastructure: {module}"
                )

    for path in (AGENTS / "_domain").rglob("*.py"):
        for module in imported_modules(path):
            parts = set(module.split("."))
            if parts & FORBIDDEN_DOMAIN_PARTS:
                failures.append(
                    f"{path.relative_to(ROOT)} domain import crosses boundary: {module}"
                )

    route_algorithm_boundaries = (
        AGENTS / "_domain" / "maps" / "route_place_set.py",
        AGENTS / "_domain" / "maps" / "route_strategy.py",
        AGENTS / "_infrastructure" / "skills" / "route_operations.py",
    )
    model_invocation_tokens = ("with_structured_output(", ".ainvoke(", "get_model(")
    for path in route_algorithm_boundaries:
        source = path.read_text(encoding="utf-8")
        if any(token in source for token in model_invocation_tokens):
            failures.append(
                f"{path.relative_to(ROOT)} route algorithms must not invoke a model; "
                "only route_resolution.py may reconcile user place language to provider POIs"
            )

    if failures:
        raise SystemExit(
            "Python architecture check failed:\n- " + "\n- ".join(sorted(failures))
        )
    print(
        "Python architecture passed: domain is pure, agents/_shared is absent, "
        "and test files remain bounded."
    )


if __name__ == "__main__":
    main()
