"""Tencent Maps runtime shared by trusted map and calendar operations."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from ..._infrastructure.makers.place_repository import (
    load_place_cache,
    save_place_cache,
)
from ..._infrastructure.makers.provider_usage_repository import (
    record_provider_usage,
)


ProviderResolver = Callable[[], Callable[..., Awaitable[Any]]]


class MapProviderRuntime:
    """Own provider calls, Makers caching, tracing, timeouts, and metering."""

    def __init__(
        self,
        *,
        store: Any,
        user_id: str,
        service_mode: str,
        search_timeout: float,
        place_result_limit: int,
        tracer: Any,
        search_places_provider: ProviderResolver,
        search_nearby_provider: ProviderResolver,
        reverse_geocode_provider: ProviderResolver,
        plan_route_provider: ProviderResolver,
    ) -> None:
        self._store = store
        self._user_id = user_id
        self._service_mode = service_mode
        self._search_timeout = search_timeout
        self._place_result_limit = place_result_limit
        self._tracer = tracer
        self._search_places_provider = search_places_provider
        self._search_nearby_provider = search_nearby_provider
        self._reverse_geocode_provider = reverse_geocode_provider
        self._plan_route_provider = plan_route_provider

    async def _record_call(self, source: str, map_key: str) -> None:
        if str(map_key or "").strip():
            await record_provider_usage(
                self._store,
                self._user_id,
                "tencent_maps",
                "requests",
                1,
                source=source,
            )

    async def _traced_call(
        self,
        name: str,
        operation: str,
        call: Callable[[], Awaitable[Any]],
    ) -> Any:
        span_method = getattr(self._tracer, "span", None)
        if not callable(span_method):
            return await call()

        async def run(span):
            result = await call()
            set_attributes = getattr(span, "set_attributes", None)
            if callable(set_attributes):
                attributes: dict[str, str | int | float | bool] = {
                    "maps.operation": operation,
                    "maps.service_mode": self._service_mode,
                    "maps.timeout_seconds": self._search_timeout,
                }
                if isinstance(result, list):
                    attributes["maps.result_count"] = len(result)
                elif isinstance(result, dict):
                    attributes["maps.provider"] = str(
                        result.get("provider") or "unknown"
                    )
                    attributes["maps.result_count"] = len(
                        result.get("places") or []
                    )
                set_attributes(attributes)
            return result

        return await span_method(
            name,
            run,
            {
                "maps.operation": operation,
                "maps.service_mode": self._service_mode,
            },
        )

    async def search_places(self, map_key: str, *args, **kwargs):
        query = str(args[0] if args else kwargs.get("query") or "")
        city = str(kwargs.get("city") or "全国")
        limit = int(kwargs.get("limit") or self._place_result_limit)
        cached = await load_place_cache(
            self._store,
            self._user_id,
            query,
            city,
            limit,
        )
        if cached is not None:
            return cached
        try:
            places = await self._traced_call(
                "maps.place_search",
                "place_search",
                lambda: asyncio.wait_for(
                    self._search_places_provider()(map_key, *args, **kwargs),
                    timeout=self._search_timeout,
                ),
            )
        finally:
            await self._record_call("chat_place_search", map_key)
        await save_place_cache(
            self._store,
            self._user_id,
            query,
            city,
            limit,
            places,
        )
        return places

    async def search_nearby(self, map_key: str, *args, **kwargs):
        try:
            return await self._traced_call(
                "maps.nearby_search",
                "nearby_search",
                lambda: self._search_nearby_provider()(
                    map_key,
                    *args,
                    **kwargs,
                ),
            )
        finally:
            await self._record_call("chat_nearby_search", map_key)

    async def reverse_geocode(
        self,
        map_key: str,
        location: dict[str, Any],
    ):
        try:
            return await self._traced_call(
                "maps.reverse_geocode",
                "reverse_geocode",
                lambda: asyncio.wait_for(
                    self._reverse_geocode_provider()(map_key, location),
                    timeout=min(12.0, self._search_timeout),
                ),
            )
        finally:
            await self._record_call("chat_reverse_geocode", map_key)

    async def plan_route(self, map_key: str, *args, **kwargs):
        try:
            return await self._traced_call(
                "maps.tencent_route",
                "tencent_route",
                lambda: asyncio.wait_for(
                    self._plan_route_provider()(map_key, *args, **kwargs),
                    timeout=min(
                        18.0,
                        max(8.0, 58.0 - self._search_timeout),
                    ),
                ),
            )
        finally:
            await self._record_call("chat_route", map_key)
