from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
DOMAIN = ROOT / "agents" / "_domain"
FORBIDDEN = {
    "_application",
    "_controllers",
    "_infrastructure",
    "_presenters",
    "pages_agents",
    "pages_blob",
    "requests",
    "urllib",
}


class DomainLayerBoundaryTests(unittest.TestCase):
    def test_domain_does_not_import_runtime_or_provider_layers(self) -> None:
        violations: list[str] = []
        for path in DOMAIN.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                module = ""
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if set(alias.name.split(".")) & FORBIDDEN:
                            violations.append(f"{path.name}: {alias.name}")
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    if set(module.split(".")) & FORBIDDEN:
                        violations.append(f"{path.name}: {module}")
        self.assertEqual(violations, [])

    def test_removed_shared_package_does_not_exist(self) -> None:
        self.assertFalse((ROOT / "agents" / "_shared").exists())


if __name__ == "__main__":
    unittest.main()
