"""Repository architecture gate for Python Agent layers."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AGENTS = ROOT / "agents"
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

    for path in AGENTS.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
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
    print("Python architecture passed: domain is pure and agents/_shared is absent.")


if __name__ == "__main__":
    main()
