from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


class InfrastructureLayerBoundaryTests(unittest.TestCase):
    def test_maker_and_provider_adapters_have_explicit_packages(self) -> None:
        infrastructure = ROOT / "agents" / "_infrastructure"
        self.assertTrue((infrastructure / "makers" / "identity.py").is_file())
        self.assertTrue((infrastructure / "makers" / "repository.py").is_file())
        self.assertTrue((infrastructure / "providers" / "rich_search.py").is_file())
        self.assertTrue(
            (infrastructure / "providers" / "unavailable_billing.py").is_file()
        )


if __name__ == "__main__":
    unittest.main()
