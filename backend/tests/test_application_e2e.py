from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from config import settings
from database.connection import close_db
from main import app


class ApplicationE2ETests(unittest.TestCase):
    """Deterministic full-lifespan checks with no real external providers."""

    def test_full_application_starts_with_supervisor_and_protected_health(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fields = {
                "db_path": str(root / "agent.db"),
                "file_storage_dir": str(root / "files"),
                "agent_state_dir": str(root / "state"),
                "local_token_path": str(root / "state" / "access-token"),
            }
            previous = {name: getattr(settings, name) for name in fields}
            try:
                asyncio.run(close_db())
                for name, value in fields.items():
                    setattr(settings, name, value)

                with TestClient(app) as client:
                    self.assertEqual(client.get("/api/system/health").status_code, 401)
                    setup = client.get("/api/setup/access-token")
                    self.assertEqual(setup.status_code, 200)
                    token = setup.json()["token"]
                    health = client.get(
                        "/api/system/health",
                        headers={"X-Agent-Token": token},
                    )
                    self.assertEqual(health.status_code, 200)
                    payload = health.json()
                    self.assertEqual(payload["status"], "ok")
                    supervisor = payload["components"]["supervisor"]
                    self.assertTrue(supervisor["running"])
                    self.assertEqual(supervisor["status"], "ok")
                    self.assertEqual(supervisor["queues"]["jobs"]["enabled"], 2)
                    self.assertEqual(
                        payload["startup_recovery"]["reconciliation"]["errors"], []
                    )
            finally:
                asyncio.run(close_db())
                for name, value in previous.items():
                    setattr(settings, name, value)


if __name__ == "__main__":
    unittest.main()
