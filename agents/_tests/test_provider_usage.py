from __future__ import annotations

import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from agents._application.intelligence.service import empty_intelligence_state, intelligence_namespace
from agents._infrastructure.makers.provider_usage_repository import (
    metering_namespace,
    provider_metering_summary,
    record_provider_usage,
)
from agents._infrastructure.providers.vision import _usage_fields
from agents._controllers import provider_usage_controller
from agents.provider_usage import index as provider_usage
from agents._tests.auth_helpers import TEST_USER_ID, authenticated_context


class FakeStore:
    def __init__(self):
        self.values = {}

    async def aget(self, namespace, key):
        value = self.values.get((namespace, key))
        return None if value is None else {"value": value}

    async def aput(self, namespace, key, value):
        self.values[(namespace, key)] = value


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class ProviderUsageTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        provider_usage_controller._deepseek_cache.update(
            {"expires_at": 0, "value": None}
        )

    async def test_endpoint_returns_only_safe_balance_fields_and_recorded_usage(self):
        store = FakeStore()
        state = empty_intelligence_state()
        state["usage"] = [{
            "total_tokens": 321,
            "created_at": 2_000_000_000,
        }]
        store.values[(intelligence_namespace(TEST_USER_ID), "state")] = state
        ctx = authenticated_context(SimpleNamespace(
            env={"DEEPSEEK_API_KEY": "secret-value"},
            store=SimpleNamespace(langgraph_store=store),
        ), roles=["admin"])
        payload = {
            "is_available": True,
            "balance_infos": [{
                "currency": "CNY",
                "total_balance": "13.84",
                "granted_balance": "0.00",
                "topped_up_balance": "13.84",
                "private_field": "must-not-leak",
            }],
        }
        with patch("agents._controllers.provider_usage_controller.time.time", return_value=2_000_000_000), patch(
            "agents._controllers.provider_usage_controller.urllib.request.urlopen",
            return_value=FakeResponse(payload),
        ):
            result = await provider_usage.handler(ctx)

        self.assertEqual(result["usage"]["daily_tokens"], 321)
        self.assertEqual(result["metering"]["timezone"], "Asia/Shanghai")
        self.assertEqual(result["providers"][0]["balances"][0]["total_balance"], "13.84")
        encoded = json.dumps(result)
        self.assertNotIn("secret-value", encoded)
        self.assertNotIn("private_field", encoded)

    async def test_missing_deepseek_key_does_not_create_a_provider_card(self):
        ctx = authenticated_context(SimpleNamespace(
            env={},
            store=SimpleNamespace(langgraph_store=FakeStore()),
        ))
        result = await provider_usage.handler(ctx)
        self.assertEqual(result["providers"], [])

    async def test_application_metering_is_persisted_and_grouped_by_day_and_month(self):
        store = FakeStore()
        now = 2_000_000_000
        await record_provider_usage(
            store, TEST_USER_ID, "wsa", "requests", 2,
            source="test", created_at=now,
        )
        await record_provider_usage(
            store, TEST_USER_ID, "hunyuan", "vision_tokens", 123,
            input_tokens=100, output_tokens=23, source="test", created_at=now,
        )
        state = store.values[(metering_namespace(TEST_USER_ID), "state")]
        summary = provider_metering_summary(state, now)
        self.assertEqual(summary["daily"]["wsa.requests"], 2)
        self.assertEqual(summary["monthly"]["hunyuan.vision_tokens"], 123)
        self.assertEqual(summary["providers"]["hunyuan"]["daily_vision_tokens"], 123)

    def test_openai_compatible_vision_usage_is_normalized(self):
        self.assertEqual(_usage_fields({
            "prompt_tokens": 80,
            "completion_tokens": 20,
            "total_tokens": 100,
        }), {
            "input_tokens": 80,
            "output_tokens": 20,
            "total_tokens": 100,
        })


if __name__ == "__main__":
    unittest.main()
