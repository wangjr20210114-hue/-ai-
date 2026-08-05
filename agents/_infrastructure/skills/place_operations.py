"""Trusted place lookup Component operations."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any, Literal

from ..._application.i18n import normalize_language, text
from .map_runtime import MapProviderRuntime
from .route_resolution import (
    _clarification_action,
    _normalized_place_name,
    _place_choice_field,
    _place_option_label,
    _place_resolution_with_provider_review,
    _selected_place_candidate,
    verify_place_queries_parallel,
)
from ..._application.workspace.service import new_action, put_action


StateLoader = Callable[[], Awaitable[dict[str, Any]]]
StateSaver = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


class PlaceOperations:
    """Expose verified place operations over one shared Maps runtime."""

    def __init__(
        self,
        *,
        runtime_env: dict[str, Any],
        conversation_id: str,
        browser_current_location: dict[str, Any] | None,
        map_runtime: MapProviderRuntime,
        load_state: StateLoader,
        save_state: StateSaver,
        place_disambiguation_model: Any,
        planned_calendar_place_resolution: bool,
        provider_place_review_enabled: bool,
        place_result_limit: int,
        route_stop_limit: int,
        parallelism: int,
        search_timeout: float,
        response_language: object = "zh-CN",
    ) -> None:
        self._runtime_env = runtime_env
        self._conversation_id = conversation_id
        self._browser_current_location = browser_current_location
        self._map_runtime = map_runtime
        self._load_state = load_state
        self._save_state = save_state
        self._place_disambiguation_model = place_disambiguation_model
        self._planned_calendar_place_resolution = (
            planned_calendar_place_resolution
        )
        self._provider_place_review_enabled = provider_place_review_enabled
        self._place_result_limit = place_result_limit
        self._route_stop_limit = route_stop_limit
        self._parallelism = parallelism
        self._search_timeout = search_timeout
        self._response_language = normalize_language(response_language)

    def _map_key(self) -> str:
        return str(
            self._runtime_env.get("TENCENT_MAP_SERVER_KEY")
            or self._runtime_env.get("TENCENT_MAP_KEY")
            or self._runtime_env.get("VITE_TENCENT_MAP_KEY")
            or ""
        )

    async def get_current_location(self) -> str:
        """Describe the fresh browser location through Tencent reverse geocoding."""
        if self._browser_current_location is None:
            return _clarification_action(
                self._conversation_id,
                title=text("place.location_required.title", self._response_language),
                prompt=text("place.location_required.prompt", self._response_language),
                fields=[{
                    "id": "manual_location",
                    "label": text(
                        "place.location_required.label", self._response_language,
                    ),
                    "type": "text",
                    "required": True,
                    "options": [],
                    "placeholder": text(
                        "place.location_required.placeholder",
                        self._response_language,
                    ),
                }],
            )
        try:
            resolved = await self._map_runtime.reverse_geocode(
                self._map_key(),
                self._browser_current_location,
            )
        except Exception as exc:
            logging.warning(
                "reverse geocode current location failed error=%s",
                exc,
            )
            raise ValueError(text(
                "place.location_reverse_failed", self._response_language,
            )) from exc
        return json.dumps({
            "location_available": True,
            "location": resolved,
            "accuracy_meters": self._browser_current_location.get(
                "accuracy_meters"
            ),
            "response_constraint": text(
                "model.place.location_constraint", self._response_language,
            ),
        }, ensure_ascii=False)

    async def search_places(
        self,
        query: str,
        city: str = "全国",
        limit: int = 10,
        purpose: Literal["browse", "calendar"] = "browse",
    ) -> str:
        """Search real places; calendar mode enforces auto/choose/fill resolution."""
        effective_purpose = (
            "calendar"
            if self._planned_calendar_place_resolution
            else purpose
        )
        state = await self._load_state()
        candidates = state.setdefault("place_candidates", {})
        selected_option = (
            _selected_place_candidate(query, candidates)
            or next(
                (
                    place
                    for place in candidates.values()
                    if isinstance(place, dict)
                    and _normalized_place_name(_place_option_label(place))
                    == _normalized_place_name(query)
                ),
                None,
            )
        )
        if effective_purpose == "calendar" and isinstance(
            selected_option,
            dict,
        ):
            return json.dumps({
                "places": [selected_option],
                "count": 1,
                "resolution": {
                    "decision": "auto_use",
                    "reason": "user_selected_verified_candidate",
                    "selected_place_id": selected_option.get("place_id"),
                },
            }, ensure_ascii=False)
        places = await self._map_runtime.search_places(
            self._map_key(),
            query,
            city=city,
            limit=max(1, min(self._place_result_limit, int(limit))),
        )
        for place in places:
            candidates[str(place["place_id"])] = place
        if len(candidates) > 200:
            state["place_candidates"] = dict(
                list(candidates.items())[-200:]
            )
        await self._save_state(state)
        if effective_purpose != "calendar":
            return json.dumps(
                {"places": places, "count": len(places)},
                ensure_ascii=False,
            )
        decision, selected, reason = (
            await _place_resolution_with_provider_review(
                self._place_disambiguation_model,
                query,
                places,
                context="calendar place lookup",
                enabled=self._provider_place_review_enabled,
                timeout_seconds=min(8.0, self._search_timeout),
                response_language=self._response_language,
            )
        )
        if decision == "auto_use" and isinstance(selected, dict):
            return json.dumps({
                "places": [selected],
                "count": 1,
                "resolution": {
                    "decision": decision,
                    "reason": reason,
                    "selected_place_id": selected.get("place_id"),
                },
            }, ensure_ascii=False)
        if decision == "choose":
            return _clarification_action(
                self._conversation_id,
                title=text("place.calendar_choice.title", self._response_language),
                prompt=text(
                    "place.calendar_choice.prompt", self._response_language,
                    query=query,
                ),
                fields=[_place_choice_field(
                    "calendar_place",
                    text("place.calendar_choice.label", self._response_language),
                    places,
                    self._response_language,
                )],
            )
        return _clarification_action(
            self._conversation_id,
            title=text("place.calendar_fill.title", self._response_language),
            prompt=text(
                "place.calendar_fill.prompt", self._response_language,
                query=query,
            ),
            fields=[{
                "id": "calendar_place",
                "label": text(
                    "place.calendar_fill.label", self._response_language,
                ),
                "type": "text",
                "required": True,
                "options": [],
                "placeholder": text(
                    "route.confirm.placeholder", self._response_language,
                    query=query,
                ),
            }],
        )

    async def search_places_batch(
        self,
        queries: list[str],
        city: str = "全国",
        limit_per_query: int = 3,
    ) -> str:
        """Verify every named destination independently and retain every candidate ID."""
        normalized = []
        seen_queries = set()
        for raw_query in queries or []:
            query = str(raw_query or "").strip()
            if query and query not in seen_queries:
                seen_queries.add(query)
                normalized.append(query)
        if not 1 <= len(normalized) <= self._route_stop_limit:
            raise ValueError(text(
                "place.error.batch_count", self._response_language,
                maximum=self._route_stop_limit,
            ))

        groups = []
        all_places = []
        seen_ids = set()
        semaphore = asyncio.Semaphore(self._parallelism)

        async def search_one(query: str) -> dict[str, Any]:
            try:
                async with semaphore:
                    places = await self._map_runtime.search_places(
                        self._map_key(),
                        query,
                        city=city,
                        limit=max(
                            1,
                            min(
                                self._place_result_limit,
                                int(limit_per_query),
                            ),
                        ),
                    )
                return {"query": query, "places": places}
            except Exception as exc:
                return {
                    "query": query,
                    "places": [],
                    "error": str(exc)[:200],
                }

        try:
            groups = await asyncio.wait_for(
                asyncio.gather(
                    *(search_one(query) for query in normalized)
                ),
                timeout=self._search_timeout,
            )
        except asyncio.TimeoutError as exc:
            raise TimeoutError(text(
                "place.error.batch_timeout", self._response_language,
                seconds=round(self._search_timeout),
            )) from exc
        for group in groups:
            places = group.get("places") or []
            for place in places:
                place_id = str(place["place_id"])
                if place_id not in seen_ids:
                    seen_ids.add(place_id)
                    all_places.append(place)

        state = await self._load_state()
        candidates = state.setdefault("place_candidates", {})
        for place in all_places:
            candidates[str(place["place_id"])] = place
        if len(candidates) > 200:
            state["place_candidates"] = dict(
                list(candidates.items())[-200:]
            )
        await self._save_state(state)
        return json.dumps(
            {
                "groups": groups,
                "places": all_places,
                "verified_query_count": sum(
                    bool(group.get("places"))
                    for group in groups
                ),
            },
            ensure_ascii=False,
        )

    async def prepare_map_recommendation(
        self,
        title: str,
        place_ids: list[str],
        action_text: str,
        expected_place_count: int = 2,
    ) -> str:
        """Prepare a clickable map recommendation from verified place IDs."""
        if (
            not isinstance(place_ids, list)
            or not 1 <= len(place_ids) <= self._place_result_limit
        ):
            raise ValueError(text(
                "place.error.map_id_count", self._response_language,
                maximum=self._place_result_limit,
            ))
        state = await self._load_state()
        candidates = dict(state.get("place_candidates", {}))
        for event in (state.get("schedules") or {}).values():
            extra = (
                event.get("extra")
                if isinstance(event, dict)
                and isinstance(event.get("extra"), dict)
                else {}
            )
            place = extra.get("place") if isinstance(extra, dict) else None
            if isinstance(place, dict) and str(place.get("place_id") or ""):
                candidates[str(place["place_id"])] = place
        places = []
        seen = set()
        for raw_id in place_ids:
            place_id = str(raw_id or "").strip()
            place = candidates.get(place_id)
            if (
                place_id
                and place_id not in seen
                and isinstance(place, dict)
            ):
                seen.add(place_id)
                places.append(place)
        if not places:
            raise ValueError(text(
                "place.error.none_verified", self._response_language,
            ))
        expected = max(
            1,
            min(
                self._place_result_limit,
                int(expected_place_count or 2),
            ),
        )
        action = new_action(
            "map_recommendation",
            {
                "title": str(title or text(
                    "place.map.default_title", self._response_language,
                ))[:120],
                "action_text": str(
                    action_text or text(
                        "place.map.default_action", self._response_language,
                    )
                )[:80],
                "places": places,
            },
            requires_confirmation=False,
        )
        put_action(state, action)
        await self._save_state(state)
        return json.dumps({
            "ui_action": "map_action",
            "action": action,
            "verified_place_count": len(places),
            "requested_place_count": expected,
            "partial": len(places) < expected,
        }, ensure_ascii=False)

    async def recommend_places_on_map(
        self,
        queries: list[str],
        city: str,
        title: str,
        action_text: str,
    ) -> str:
        """Verify model-selected destinations and prepare one map Action."""
        normalized = list(dict.fromkeys(
            str(item or "").strip()
            for item in queries
            if str(item or "").strip()
        ))
        if not 2 <= len(normalized) <= self._place_result_limit:
            raise ValueError(text(
                "place.error.recommend_count", self._response_language,
                maximum=self._place_result_limit,
            ))
        selected, all_candidates, missing = (
            await verify_place_queries_parallel(
                self._map_runtime.search_places,
                self._map_key(),
                normalized,
                city=city or "全国",
                timeout_seconds=float(
                    self._runtime_env.get(
                        "PLACE_LOOKUP_TIMEOUT_SECONDS"
                    )
                    or 5
                ),
            )
        )
        if not selected:
            raise ValueError(text(
                "place.error.all_unverified", self._response_language,
            ))
        state = await self._load_state()
        candidates = state.setdefault("place_candidates", {})
        for place in all_candidates:
            candidates[str(place["place_id"])] = place
        action = new_action(
            "map_recommendation",
            {
                "title": str(title or text(
                    "place.map.city_title", self._response_language,
                    city=city,
                ))[:120],
                "action_text": str(
                    action_text or text(
                        "place.map.city_action", self._response_language,
                    )
                )[:80],
                "places": selected,
            },
            requires_confirmation=False,
        )
        put_action(state, action)
        await self._save_state(state)
        verified_count = len(selected)
        requested_count = len(normalized)
        response_constraint = text(
            "model.place.map_constraint", self._response_language,
            verified=verified_count, requested=requested_count,
            missing=text(
                "model.place.map_missing", self._response_language,
                places="、".join(missing),
            ) if missing else "",
        )
        return json.dumps({
            "ui_action": "map_action",
            "action": action,
            "verified_place_count": verified_count,
            "requested_place_count": requested_count,
            "partial": bool(missing),
            "unverified_queries": missing,
            "response_constraint": response_constraint,
        }, ensure_ascii=False)
