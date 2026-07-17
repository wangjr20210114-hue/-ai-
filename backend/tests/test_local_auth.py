from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient

from api.setup_routes import router as setup_router
from security.local_auth import (
    LocalAccessTokenService,
    LocalTokenMiddleware,
    require_websocket_token,
)


class LocalAuthTests(unittest.TestCase):
    def test_generated_token_is_persistent_and_constant_time_verified(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "access-token"
            first = LocalAccessTokenService(path)
            token = first.initialize()
            self.assertGreaterEqual(len(token), 32)
            self.assertTrue(first.verify(token))
            self.assertFalse(first.verify("wrong"))
            second = LocalAccessTokenService(path)
            self.assertEqual(second.initialize(), token)

    def test_rest_api_requires_token_but_loopback_setup_bootstraps_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            service = LocalAccessTokenService(Path(directory) / "access-token")
            app = FastAPI()
            app.state.local_access_token_service = service
            app.add_middleware(LocalTokenMiddleware)
            app.include_router(setup_router)

            @app.get("/api/private")
            async def private_route() -> dict:
                return {"ok": True}

            with TestClient(app) as client:
                self.assertEqual(client.get("/api/private").status_code, 401)
                setup = client.get("/api/setup/access-token")
                self.assertEqual(setup.status_code, 200)
                token = setup.json()["token"]
                response = client.get("/api/private", headers={"X-Agent-Token": token})
                self.assertEqual(response.status_code, 200)
                blocked_origin = client.get(
                    "/api/setup/access-token",
                    headers={"Origin": "https://malicious.example"},
                )
                self.assertEqual(blocked_origin.status_code, 403)


    def test_websocket_uses_subprotocol_instead_of_url_token(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            service = LocalAccessTokenService(Path(directory) / "access-token")
            token = service.initialize()
            app = FastAPI()
            app.state.local_access_token_service = service

            @app.websocket("/ws")
            async def websocket_route(websocket: WebSocket) -> None:
                protocol = await require_websocket_token(websocket)
                if protocol is None:
                    return
                await websocket.accept(subprotocol=protocol or None)
                await websocket.send_json({"ok": True})

            protocol = f"agent-token.{token}"
            with TestClient(app) as client:
                with client.websocket_connect("/ws", subprotocols=[protocol]) as websocket:
                    self.assertEqual(websocket.accepted_subprotocol, protocol)
                    self.assertEqual(websocket.receive_json(), {"ok": True})



if __name__ == "__main__":
    unittest.main()
