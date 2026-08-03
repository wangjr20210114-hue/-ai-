from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class SkillAccessControllerBoundaryTests(unittest.TestCase):
    def test_feature_controllers_share_one_runtime_access_resolver(self) -> None:
        for filename in (
            "image_controller.py",
            "places_controller.py",
            "proactive_controller.py",
            "reader_controller.py",
            "routes_controller.py",
            "workspace_controller.py",
        ):
            with self.subTest(controller=filename):
                source = (ROOT / "_controllers" / filename).read_text(
                    encoding="utf-8",
                )
                self.assertIn("resolve_skill_access", source)
                self.assertNotIn("capability_is_enabled", source)
                self.assertNotIn("require_skill_access", source)


if __name__ == "__main__":
    unittest.main()
