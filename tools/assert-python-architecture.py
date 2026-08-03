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
