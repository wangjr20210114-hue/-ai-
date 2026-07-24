from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from agents.routes.index import handler


PLACES = [
    {"place_id": "a", "latitude": 39.9, "longitude": 116.3},
    {"place_id": "b", "latitude": 39.8, "longitude": 116.4},
]


class FakeStore:
    def __init__(self):
        self.values = {}

    async def aget(self, namespace, key):
        value = self.values.get((namespace, key))
        return None if value is None else {"value": value}

    async def aput(self, namespace, key, value):
        self.values[(namespace, key)] = value


class RouteCacheTests(unittest.IsolatedAsyncioTestCase):
    async def test_identical_route_reuses_makers_store(self):
        store = FakeStore()
        ctx = SimpleNamespace(
            env={},
            request=SimpleNamespace(body={"places": PLACES, "optimize": False}, headers={}),
            store=SimpleNamespace(langgraph_store=store),
        )
        route = {
            "schema_version": 1, "provider": "test", "mode": "driving",
            "places": PLACES, "path": [], "distance_meters": 1000, "duration_seconds": 600,
            "fare": {"currency": "CNY", "basis": "test", "self_driving": {"estimate": 1, "toll": 0}, "taxi": {"low": 10, "high": 12}},
        }
        planner = AsyncMock(return_value=route)
        with patch("agents.routes.index.plan_verified_route", planner):
            first = await handler(ctx)
            second = await handler(ctx)
        self.assertFalse(first["route"]["cache"]["hit"])
        self.assertTrue(second["route"]["cache"]["hit"])
        planner.assert_awaited_once()
        self.assertEqual(planner.await_args.args[1], PLACES)
        self.assertEqual(planner.await_args.kwargs, {"optimize": False})


if __name__ == "__main__":
    unittest.main()
