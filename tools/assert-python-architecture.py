"""Repository architecture gate for Python Agent layers."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AGENTS = ROOT / "agents"
MAX_TEST_FILE_LINES = 750
MAX_PRODUCTION_FILE_LINES = 2_500
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


def imported_modules(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            modules.append(node.module or "")
    return modules


def main() -> None:
    failures: list[str] = []
    shared = AGENTS / "_shared"
    if shared.exists():
        failures.append("agents/_shared must not exist")

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
            if line_count > MAX_PRODUCTION_FILE_LINES:
                failures.append(
                    f"{path.relative_to(ROOT)} has {line_count} lines "
                    f"(production maximum {MAX_PRODUCTION_FILE_LINES})"
                )
        for module in imported_modules(path):
            if "_shared" in module:
                failures.append(f"{path.relative_to(ROOT)} imports removed {module}")

    for path in (AGENTS / "_domain").rglob("*.py"):
        for module in imported_modules(path):
            parts = set(module.split("."))
            if parts & FORBIDDEN_DOMAIN_PARTS:
                failures.append(
                    f"{path.relative_to(ROOT)} domain import crosses boundary: {module}"
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
