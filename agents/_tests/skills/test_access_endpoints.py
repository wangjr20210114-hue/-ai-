from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from agents._controllers.image_controller import handler as image_handler
from agents._controllers.places_controller import handler as places_handler
from agents._controllers.reader_controller import (
    _resolve_reader_source,
    handler as reader_handler,
)
from agents._controllers.routes_controller import handler as routes_handler
from agents._tests.auth_helpers import auth_env, auth_headers
from agents._tests.support.fakes import FakeStore


def guest_context(body: dict) -> SimpleNamespace:
    return SimpleNamespace(
        conversation_id="access-smoke",
        env=auth_env(),
        request=SimpleNamespace(
            body=body,
            headers=auth_headers(auth_type="guest", membership="guest"),
        ),
        store=SimpleNamespace(langgraph_store=FakeStore()),
    )


class SkillAccessEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_guest_direct_api_calls_stop_before_providers(self) -> None:
        route_provider = AsyncMock()
        place_provider = AsyncMock()
        image_provider = AsyncMock()
        with (
            patch(
                "agents._controllers.routes_controller.plan_verified_route",
                route_provider,
            ),
            patch(
                "agents._controllers.places_controller.search_verified_places_bounded",
                place_provider,
            ),
            patch(
                "agents._controllers.image_controller.generate_image",
                image_provider,
            ),
        ):
            route = await routes_handler(guest_context({
                "places": [
                    {"place_id": "a", "latitude": 1, "longitude": 1},
                    {"place_id": "b", "latitude": 2, "longitude": 2},
                ],
            }))
            places = await places_handler(guest_context({"query": "museum"}))
            image = await image_handler(guest_context({
                "prompt": "make it warmer",
                "parent_action_id": "image-parent",
            }))

        for response in (route, places, image):
            self.assertEqual(response["status_code"], 403)
            self.assertEqual(response["body"]["code"], "LOGIN_REQUIRED")
        route_provider.assert_not_awaited()
        place_provider.assert_not_awaited()
        image_provider.assert_not_awaited()

    async def test_guest_reader_stops_before_model_construction(self) -> None:
        with patch("agents._controllers.reader_controller.get_model") as model:
            response = await reader_handler(guest_context({
                "action": "summarize",
                "text": "paper content",
            }))

        self.assertEqual(response["status_code"], 403)
        self.assertEqual(response["body"]["code"], "LOGIN_REQUIRED")
        model.assert_not_called()

    async def test_reader_can_resolve_an_owned_file_without_client_pdf_parsing(self) -> None:
        ctx = guest_context({"file_id": "tenant-file"})
        source = {
            "file_id": "tenant-file", "storage_key": "tenant-file",
            "text": "server extracted text", "preview": "server extracted text",
            "page_count": 2, "truncated": False,
        }
        with patch(
            "agents._controllers.reader_controller.load_document_text",
            AsyncMock(return_value=source),
        ) as loader:
            content, metadata = await _resolve_reader_source(ctx, ctx.request.body)
        loader.assert_awaited_once_with(ctx, "tenant-file")
        self.assertEqual(content, "server extracted text")
        self.assertEqual(metadata["page_count"], 2)


if __name__ == "__main__":
    unittest.main()
