from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from config import settings
from database.connection import close_db
from main import app
from services.model_gateway import ModelChunk, ModelGateway, ProviderUsage
from skills.chat_skill import ChatSkill


async def _fake_stream(
    self: ModelGateway,
    request,
    context,
    cancellation=None,
):
    del self, request, context, cancellation
    yield ModelChunk(delta="基础", provider="fake", model="fake")
    yield ModelChunk(delta="链路通过", provider="fake", model="fake")
    yield ModelChunk(
        done=True,
        provider="fake",
        model="fake",
        usage=ProviderUsage(output_tokens=3, total_tokens=3),
    )


class LocalChatTransportTests(unittest.TestCase):
    """Full local contract: token -> WebSocket -> stream -> persistence."""

    def test_local_websocket_chat_and_message_recovery(self) -> None:
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

                with (
                    patch.object(ModelGateway, "stream_text", new=_fake_stream),
                    patch.object(
                        ChatSkill,
                        "_generate_follow_ups",
                        new=AsyncMock(return_value=[]),
                    ),
                    patch(
                        "database.repositories.job_repo.claim_due_job",
                        new=AsyncMock(return_value=None),
                    ),
                    TestClient(app) as client,
                ):
                    setup = client.get("/api/setup/access-token")
                    self.assertEqual(setup.status_code, 200)
                    token = setup.json()["token"]
                    headers = {"X-Agent-Token": token}

                    bootstrap = client.get(
                        "/api/bootstrap?conversation_id=default-conversation",
                        headers=headers,
                    )
                    self.assertEqual(bootstrap.status_code, 200)
                    self.assertEqual(bootstrap.json()["messages"], [])

                    protocol = f"agent-token.{token}"
                    with client.websocket_connect(
                        "/ws/default-conversation",
                        subprotocols=[protocol],
                    ) as websocket:
                        ack = websocket.receive_json()
                        self.assertEqual(ack["type"], "ack")
                        self.assertEqual(
                            ack["payload"]["conversation_id"],
                            "default-conversation",
                        )

                        websocket.send_json({"type": "ping", "payload": {}})
                        self.assertEqual(websocket.receive_json()["type"], "pong")

                        websocket.send_json(
                            {
                                "type": "user_activity",
                                "payload": {
                                    "text": "你好，本地链路测试",
                                    "message_id": "local-smoke-user",
                                    "web_search": False,
                                },
                            }
                        )
                        events = []
                        while "stream_end" not in events and "error" not in events:
                            events.append(websocket.receive_json()["type"])

                    self.assertEqual(
                        events,
                        [
                            "chat_thinking",
                            "stream_start",
                            "stream_delta",
                            "stream_delta",
                            "stream_end",
                        ],
                    )
                    recovered = client.get(
                        "/api/conversations/default-conversation/messages",
                        headers=headers,
                    )
                    self.assertEqual(recovered.status_code, 200)
                    messages = recovered.json()["messages"]
                    self.assertEqual([item["role"] for item in messages], ["user", "ai"])
                    self.assertEqual(messages[0]["content"], "你好，本地链路测试")
                    self.assertEqual(messages[1]["content"], "基础链路通过")
            finally:
                asyncio.run(close_db())
                for name, value in previous.items():
                    setattr(settings, name, value)


if __name__ == "__main__":
    unittest.main()
