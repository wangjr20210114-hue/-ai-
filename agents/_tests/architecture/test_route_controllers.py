from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
AGENTS = ROOT / "agents"


class RouteControllerBoundaryTests(unittest.TestCase):
    def test_every_agent_route_is_a_thin_controller_adapter(self) -> None:
        violations: list[str] = []
        routes = sorted(
            path
            for path in AGENTS.glob("*/index.py")
            if not path.parent.name.startswith("_")
        )
        self.assertGreaterEqual(len(routes), 15)
        for path in routes:
            source = path.read_text(encoding="utf-8")
            nonblank = [line for line in source.splitlines() if line.strip()]
            if len(nonblank) > 80:
                violations.append(
                    f"{path.parent.name}: {len(nonblank)} nonblank lines"
                )
            tree = ast.parse(source, filename=str(path))
            handlers = [
                node
                for node in tree.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == "handler"
            ]
            if len(handlers) != 1:
                violations.append(f"{path.parent.name}: requires one handler")
            for node in tree.body:
                if isinstance(node, ast.Import):
                    violations.append(
                        f"{path.parent.name}: direct import is not a controller import"
                    )
                elif isinstance(node, ast.ImportFrom):
                    if node.module == "__future__":
                        continue
                    if "_controllers" not in (node.module or ""):
                        violations.append(
                            f"{path.parent.name}: imports {node.module}"
                        )
        self.assertEqual(violations, [])


if __name__ == "__main__":
    unittest.main()
