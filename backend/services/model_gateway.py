"""Unified OpenAI-compatible model gateway.

The gateway owns provider configuration, response validation, streaming parsing,
normalized errors, and usage persistence. Domain skills never construct HTTP
requests or know provider credentials.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from agent.cancellation import AgentCancelledError, CancellationToken
from agent.errors import (
    ProviderAuthenticationError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderTimeoutError,
)
from application.usage_service import UsageService
from config import settings
from services.hunyuan_service import ApiNotConfiguredError, QuotaExhaustedError

T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True, slots=True)
class ProviderConfig:
    name: str
    base_url: str
    api_key: str
    model: str
    input_price_per_1k: float = 0.0
    output_price_per_1k: float = 0.0

    @property
    def ready(self) -> bool:
        return bool(self.api_key) and not self.api_key.startswith("sk-your")


@dataclass(slots=True)
class ModelRequest:
    messages: list[dict[str, Any]]
    provider: str = ""
    model: str = ""
    max_tokens: int = 1500
    temperature: float = 0.7
    operation: str = "chat"


@dataclass(frozen=True, slots=True)
class CallContext:
    run_id: str | None = None
    conversation_id: str | None = None
    skill_name: str = ""


@dataclass(slots=True)
class ProviderUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_cny: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "estimated_cost_cny": self.estimated_cost_cny,
        }


@dataclass(slots=True)
class ModelTextResult:
    content: str
    provider: str
    model: str
    usage: ProviderUsage = field(default_factory=ProviderUsage)
    provider_request_id: str = ""
    latency_ms: int = 0


@dataclass(slots=True)
class ModelChunk:
    delta: str = ""
    done: bool = False
    provider: str = ""
    model: str = ""
    usage: ProviderUsage = field(default_factory=ProviderUsage)
    provider_request_id: str = ""


def _default_configs() -> dict[str, ProviderConfig]:
    return {
        "hunyuan": ProviderConfig(
            name="hunyuan",
            base_url=settings.hunyuan_base_url.rstrip("/"),
            api_key=settings.hunyuan_api_key,
            model=settings.hunyuan_model,
            input_price_per_1k=0.015,
            output_price_per_1k=0.015,
        ),
        "deepseek": ProviderConfig(
            name="deepseek",
            base_url=settings.deepseek_base_url.rstrip("/"),
            api_key=settings.deepseek_api_key,
            model=settings.deepseek_model,
            input_price_per_1k=0.002,
            output_price_per_1k=0.002,
        ),
    }


def _extract_json_text(text: str) -> str:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE)
    try:
        json.loads(cleaned)
        return cleaned
    except json.JSONDecodeError:
        match = re.search(r"(?:\{.*\}|\[.*\])", cleaned, re.DOTALL)
        if not match:
            raise ProviderResponseError("模型响应中没有合法 JSON")
        return match.group(0)


class ModelGateway:
    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        usage: UsageService | None = None,
        configs: dict[str, ProviderConfig] | None = None,
    ) -> None:
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0))
        self._owns_client = client is None
        self.usage = usage or UsageService()
        self.configs = configs or _default_configs()

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def _resolve(self, request: ModelRequest) -> ProviderConfig:
        provider = request.provider.strip().lower()
        if not provider:
            provider = "deepseek" if request.model == settings.deepseek_model else settings.llm_provider.lower()
        config = self.configs.get(provider)
        if config is None:
            raise ApiNotConfiguredError(f"未知模型提供方：{provider}")
        if not config.ready:
            raise ApiNotConfiguredError(f"{config.name} API 尚未配置")
        return config

    @staticmethod
    def _usage(raw: dict[str, Any], config: ProviderConfig, *, fallback_text: str = "") -> ProviderUsage:
        input_tokens = int(raw.get("prompt_tokens") or raw.get("input_tokens") or 0)
        output_tokens = int(raw.get("completion_tokens") or raw.get("output_tokens") or 0)
        if output_tokens <= 0 and fallback_text:
            output_tokens = max(1, len(fallback_text) // 4)
        total = int(raw.get("total_tokens") or (input_tokens + output_tokens))
        cost = input_tokens / 1000 * config.input_price_per_1k + output_tokens / 1000 * config.output_price_per_1k
        return ProviderUsage(input_tokens, output_tokens, total, round(cost, 6))

    @staticmethod
    async def _raise_for_status(response: httpx.Response, provider: str) -> None:
        if response.status_code < 400:
            return
        body = (await response.aread()).decode("utf-8", errors="replace")[:500]
        if response.status_code in {401, 403}:
            raise ProviderAuthenticationError(f"{provider} 认证失败")
        if response.status_code == 429:
            raise ProviderRateLimitError(f"{provider} 请求过于频繁或额度不足")
        if response.status_code == 402:
            raise QuotaExhaustedError(provider, "余额不足")
        raise ProviderResponseError(f"{provider} 返回 HTTP {response.status_code}: {body}")

    async def _record_usage(
        self,
        *,
        context: CallContext,
        config: ProviderConfig,
        request: ModelRequest,
        usage: ProviderUsage,
        status: str = "succeeded",
    ) -> None:
        try:
            await self.usage.record_usage(
                run_id=context.run_id,
                provider=config.name,
                operation=request.operation,
                model=request.model or config.model,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                estimated_cost=usage.estimated_cost_cny,
                status=status,
            )
        except Exception:
            # Usage persistence is observable telemetry, not part of model output.
            # Callers record a Run observation when needed; content must not be lost.
            return

    async def complete_text(self, request: ModelRequest, context: CallContext) -> ModelTextResult:
        config = self._resolve(request)
        model = request.model or config.model
        started = time.perf_counter()
        try:
            response = await self._client.post(
                f"{config.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {config.api_key}"},
                json={
                    "model": model,
                    "messages": request.messages,
                    "max_tokens": request.max_tokens,
                    "temperature": request.temperature,
                    "stream": False,
                },
            )
        except httpx.TimeoutException as error:
            raise ProviderTimeoutError(f"{config.name} 请求超时") from error
        except httpx.HTTPError as error:
            raise ProviderResponseError(f"{config.name} 网络请求失败") from error
        await self._raise_for_status(response, config.name)
        try:
            data = response.json()
            content = str(data["choices"][0]["message"]["content"]).strip()
        except (ValueError, KeyError, IndexError, TypeError) as error:
            raise ProviderResponseError(f"{config.name} 响应结构无效") from error
        if not content:
            raise ProviderResponseError(f"{config.name} 返回空响应")
        usage = self._usage(data.get("usage") or {}, config, fallback_text=content)
        await self._record_usage(context=context, config=config, request=request, usage=usage)
        return ModelTextResult(
            content=content,
            provider=config.name,
            model=model,
            usage=usage,
            provider_request_id=response.headers.get("x-request-id", ""),
            latency_ms=round((time.perf_counter() - started) * 1000),
        )

    async def complete_json(
        self,
        request: ModelRequest,
        response_model: type[T],
        context: CallContext,
    ) -> T:
        result = await self.complete_text(request, context)
        try:
            return response_model.model_validate_json(_extract_json_text(result.content))
        except (ValidationError, json.JSONDecodeError) as error:
            raise ProviderResponseError("模型 JSON 未通过结构校验") from error

    async def stream_text(
        self,
        request: ModelRequest,
        context: CallContext,
        cancellation: CancellationToken | None = None,
    ) -> AsyncIterator[ModelChunk]:
        if cancellation is not None:
            cancellation.raise_if_cancelled()
        config = self._resolve(request)
        model = request.model or config.model
        full_text = ""
        raw_usage: dict[str, Any] = {}
        request_id = ""
        try:
            async with self._client.stream(
                "POST",
                f"{config.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {config.api_key}"},
                json={
                    "model": model,
                    "messages": request.messages,
                    "max_tokens": request.max_tokens,
                    "temperature": request.temperature,
                    "stream": True,
                    "stream_options": {"include_usage": True},
                },
            ) as response:
                await self._raise_for_status(response, config.name)
                request_id = response.headers.get("x-request-id", "")
                line_iterator = response.aiter_lines().__aiter__()
                while True:
                    if cancellation is not None:
                        cancellation.raise_if_cancelled()
                        line_task = asyncio.create_task(anext(line_iterator))
                        cancel_task = asyncio.create_task(cancellation.wait())
                        done, _ = await asyncio.wait(
                            {line_task, cancel_task},
                            return_when=asyncio.FIRST_COMPLETED,
                        )
                        if cancel_task in done:
                            line_task.cancel()
                            with contextlib.suppress(asyncio.CancelledError, StopAsyncIteration):
                                await line_task
                            raise AgentCancelledError("run cancelled by user")
                        cancel_task.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await cancel_task
                        try:
                            line = line_task.result()
                        except StopAsyncIteration:
                            break
                    else:
                        try:
                            line = await anext(line_iterator)
                        except StopAsyncIteration:
                            break
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        break
                    try:
                        data = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    if data.get("usage"):
                        raw_usage = data["usage"]
                    try:
                        delta = str(data.get("choices", [{}])[0].get("delta", {}).get("content") or "")
                    except (IndexError, TypeError):
                        delta = ""
                    if delta:
                        full_text += delta
                        yield ModelChunk(delta=delta, provider=config.name, model=model)
        except httpx.TimeoutException as error:
            raise ProviderTimeoutError(f"{config.name} 流式请求超时") from error
        except httpx.HTTPError as error:
            raise ProviderResponseError(f"{config.name} 流式请求失败") from error
        if not full_text:
            raise ProviderResponseError(f"{config.name} 返回空流")
        usage = self._usage(raw_usage, config, fallback_text=full_text)
        await self._record_usage(context=context, config=config, request=request, usage=usage)
        yield ModelChunk(
            done=True,
            provider=config.name,
            model=model,
            usage=usage,
            provider_request_id=request_id,
        )
