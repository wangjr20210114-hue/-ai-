from __future__ import annotations

import unittest
from unittest.mock import AsyncMock

import httpx
from pydantic import BaseModel

from agent.cancellation import AgentCancelledError, CancellationToken
from agent.errors import ProviderAuthenticationError
from services.model_gateway import (
    CallContext,
    ModelGateway,
    ModelRequest,
    ProviderConfig,
)


class IntentPayload(BaseModel):
    intent: str
    confidence: float


class ModelGatewayTests(unittest.IsolatedAsyncioTestCase):
    def _gateway(self, handler, usage=None) -> ModelGateway:
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        return ModelGateway(
            client=client,
            usage=usage or AsyncMock(),
            configs={
                "test": ProviderConfig(
                    name="test",
                    base_url="https://model.test/v1",
                    api_key="test-key",
                    model="test-model",
                    input_price_per_1k=0.01,
                    output_price_per_1k=0.02,
                )
            },
        )

    async def test_complete_text_normalizes_usage_and_records_it(self) -> None:
        usage_service = AsyncMock()

        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/v1/chat/completions")
            return httpx.Response(
                200,
                headers={"x-request-id": "provider-123"},
                json={
                    "choices": [{"message": {"content": "统一网关回答"}}],
                    "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
                },
            )

        gateway = self._gateway(handler, usage_service)
        result = await gateway.complete_text(
            ModelRequest(
                messages=[{"role": "user", "content": "hello"}],
                provider="test",
                operation="chat",
            ),
            CallContext(run_id="run-1", conversation_id="conv-1", skill_name="chat"),
        )
        self.assertEqual(result.content, "统一网关回答")
        self.assertEqual(result.provider_request_id, "provider-123")
        self.assertEqual(result.usage.total_tokens, 150)
        self.assertAlmostEqual(result.usage.estimated_cost_cny, 0.002, places=6)
        usage_service.record_usage.assert_awaited_once()
        await gateway._client.aclose()

    async def test_complete_json_strips_fence_and_validates_schema(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            del request
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {"message": {"content": "```json\n{\"intent\":\"chat\",\"confidence\":0.9}\n```"}}
                    ]
                },
            )

        gateway = self._gateway(handler)
        result = await gateway.complete_json(
            ModelRequest(messages=[], provider="test"),
            IntentPayload,
            CallContext(run_id="run-json"),
        )
        self.assertEqual(result.intent, "chat")
        self.assertEqual(result.confidence, 0.9)
        await gateway._client.aclose()

    async def test_stream_text_emits_deltas_and_final_usage(self) -> None:
        body = (
            'data: {"choices":[{"delta":{"content":"你"}}]}\n\n'
            'data: {"choices":[{"delta":{"content":"好"}}]}\n\n'
            'data: {"choices":[],"usage":{"prompt_tokens":10,"completion_tokens":2,"total_tokens":12}}\n\n'
            'data: [DONE]\n\n'
        )

        def handler(request: httpx.Request) -> httpx.Response:
            del request
            return httpx.Response(200, content=body, headers={"x-request-id": "stream-1"})

        gateway = self._gateway(handler)
        chunks = []
        async for chunk in gateway.stream_text(
            ModelRequest(messages=[], provider="test", operation="translation"),
            CallContext(run_id="run-stream"),
        ):
            chunks.append(chunk)
        self.assertEqual("".join(item.delta for item in chunks), "你好")
        self.assertTrue(chunks[-1].done)
        self.assertEqual(chunks[-1].usage.total_tokens, 12)
        self.assertEqual(chunks[-1].provider_request_id, "stream-1")
        await gateway._client.aclose()

    async def test_stream_honors_explicit_cancellation_before_provider_call(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            del request
            return httpx.Response(200, content="data: [DONE]\n\n")

        gateway = self._gateway(handler)
        token = CancellationToken()
        token.cancel()
        with self.assertRaises(AgentCancelledError):
            async for _ in gateway.stream_text(
                ModelRequest(messages=[], provider="test"),
                CallContext(run_id="run-cancelled"),
                cancellation=token,
            ):
                pass
        self.assertEqual(calls, 0)
        await gateway._client.aclose()

    async def test_authentication_error_is_normalized(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            del request
            return httpx.Response(401, text="bad key")

        gateway = self._gateway(handler)
        with self.assertRaises(ProviderAuthenticationError):
            await gateway.complete_text(
                ModelRequest(messages=[], provider="test"),
                CallContext(run_id="run-auth"),
            )
        await gateway._client.aclose()


if __name__ == "__main__":
    unittest.main()
