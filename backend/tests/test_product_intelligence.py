from __future__ import annotations

import unittest
from unittest.mock import patch

import aiosqlite

from application.feedback_service import FeedbackService
from application.memory_service import MemoryService
from application.usage_service import UsageService
from database.init_db import (
    M1_SCHEMA,
    M2_EXECUTION_SCHEMA,
    M2_SCHEMA,
    M3_SCHEMA,
    PRODUCT_CONTROLS_SCHEMA,
    PRODUCT_INTELLIGENCE_SCHEMA,
    SCHEMA,
)
from database.migrations import Migration, apply_migrations
from database.repositories import feedback_repo, memory_repo, usage_repo


class ProductIntelligenceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.db = await aiosqlite.connect(":memory:")
        self.db.row_factory = aiosqlite.Row
        await self.db.execute("PRAGMA foreign_keys=ON")
        await apply_migrations(
            self.db,
            [
                Migration(1, "initial_schema", SCHEMA),
                Migration(2, "persistent_identity_conversations_files", M1_SCHEMA),
                Migration(3, "persistent_agent_runtime", M2_SCHEMA),
                Migration(4, "agent_execution_leases_and_results", M2_EXECUTION_SCHEMA),
                Migration(5, "proactive_jobs_notifications_usage", M3_SCHEMA),
                Migration(6, "memory_feedback_product_intelligence", PRODUCT_INTELLIGENCE_SCHEMA),
                Migration(7, "memory_versions_and_usage_preferences", PRODUCT_CONTROLS_SCHEMA),
            ],
        )
        self.patches = [
            patch.object(memory_repo, "get_db", return_value=self.db),
            patch.object(feedback_repo, "get_db", return_value=self.db),
            patch.object(usage_repo, "get_db", return_value=self.db),
        ]
        for item in self.patches:
            item.start()

    async def asyncTearDown(self) -> None:
        for item in reversed(self.patches):
            item.stop()
        await self.db.close()

    async def test_memory_requires_confirmation_and_uses_optimistic_version(self) -> None:
        service = MemoryService()
        proposal = await service.propose_memory(
            "message-1",
            {
                "key": "travel.preference.hotel",
                "value": "安静、靠近地铁",
                "confidence": 0.95,
            },
        )
        self.assertEqual(proposal["status"], "awaiting_confirmation")
        confirmed = await service.upsert_confirmed_memory(proposal["id"], proposal["version"])
        duplicate = await service.upsert_confirmed_memory(proposal["id"], proposal["version"])
        self.assertEqual(confirmed["memory"]["id"], duplicate["memory"]["id"])
        self.assertEqual(confirmed["memory"]["version"], 1)

        updated = await service.update_memory(
            confirmed["memory"]["id"],
            value="安静、地铁 500 米内",
            version=1,
        )
        self.assertEqual(updated["version"], 2)
        with self.assertRaises(memory_repo.MemoryConflict):
            await service.update_memory(
                updated["id"],
                value="旧页面覆盖",
                version=1,
            )

    async def test_sensitive_memory_is_marked_and_can_be_exported_deleted(self) -> None:
        service = MemoryService()
        proposal = await service.propose_memory(
            "message-2",
            {"key": "账号密码", "value": "do-not-store", "confidence": 1},
        )
        self.assertEqual(proposal["candidate_json"]["sensitivity"], "sensitive")
        confirmed = await service.upsert_confirmed_memory(proposal["id"], 1)
        exported = await service.export_memories()
        self.assertEqual(exported["schema_version"], 1)
        self.assertEqual(len(exported["memories"]), 1)
        self.assertTrue(await service.delete_memory(confirmed["memory"]["id"]))
        self.assertEqual((await service.export_memories())["memories"], [])

    async def test_feedback_is_idempotent_and_proposes_explainable_adjustments(self) -> None:
        service = FeedbackService()
        first = await service.record_feedback(
            run_id=None,
            action_id=None,
            action="dismissed",
            metadata={"source_label": "旅行天气"},
            client_feedback_id="feedback-client-1",
        )
        duplicate = await service.record_feedback(
            run_id=None,
            action_id=None,
            action="dismissed",
            metadata={"source_label": "旅行天气"},
            client_feedback_id="feedback-client-1",
        )
        self.assertEqual(first["feedback"]["id"], duplicate["feedback"]["id"])
        self.assertFalse(first["adjustment"]["applied"])
        self.assertTrue(first["adjustment"]["requires_user_confirmation"])

        for index in range(2, 4):
            result = await service.record_feedback(
                run_id=None,
                action_id=None,
                action="unhelpful",
                metadata={"source_label": "旅行天气"},
                client_feedback_id=f"feedback-client-{index}",
            )
        suggestion_types = {item["type"] for item in result["adjustment"]["suggestions"]}
        self.assertIn("pause_source_automation", suggestion_types)

    async def test_usage_budget_preferences_are_persistent(self) -> None:
        service = UsageService()
        preferences = await service.update_preferences(
            daily_budget_cny=1.0,
            monthly_budget_cny=10.0,
            enforcement="hard",
            alert_threshold_percent=50,
        )
        self.assertEqual(preferences["enforcement"], "hard")
        await service.record_usage(
            run_id=None,
            provider="test",
            operation="chat",
            estimated_cost=0.8,
            input_tokens=100,
            output_tokens=20,
        )
        budget = await service.check_budget(0.3)
        self.assertFalse(budget["allowed"])
        summary = await service.summarize()
        self.assertTrue(summary["alerts"]["daily"])
        self.assertEqual(summary["daily"]["calls"], 1)


if __name__ == "__main__":
    unittest.main()
