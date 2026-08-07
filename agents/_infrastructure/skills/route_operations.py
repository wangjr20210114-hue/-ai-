"""Trusted route planning operation backed by Makers state and provider adapters."""

from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import logging
import time
from typing import Any

from pydantic import BaseModel

from ..._application.i18n import normalize_language, text
from ..._application.workspace.service import new_action, put_action
from ..._domain.maps.route_place_set import RoutePlaceEdit, apply_route_place_edits
from ..._domain.maps.route_strategy import select_route_strategy
from ..._infrastructure.makers.route_repository import load_route_cache, save_route_cache
from .route_resolution import (
    _clarification_action,
    _learned_route_preference,
    _merge_clarification_actions,
    _normalized_place_name,
    _place_choice_field,
    _place_resolution_with_provider_review,
    _prioritize_clarification_options_for_city,
    _prioritize_provider_candidates_for_city,
    _provider_city_consensus,
    _rank_verified_workspace_matches,
    _route_plan_leg_summary,
    _selected_place_candidate,
    preserve_planned_route_stops,
)


def build_route_operation(
    *,
    _load_state,
    _normalize_route_contract,
    _plan_route_metered,
    _reverse_geocode_metered,
    _save_state,
    _search_places_metered,
    _search_places_nearby_metered,
    browser_current_location,
    calendar_skill_id,
    conversation_id,
    enabled_skills,
    map_learn_route_preferences,
    map_near_time_tolerance,
    map_parallelism,
    map_preferred_route_mode,
    map_route_stop_limit,
    map_route_strategy,
    map_search_timeout,
    place_disambiguation_model,
    planned_route_calendar_hint,
    planned_route_city,
    planned_route_mode,
    planned_route_stops,
    planned_route_strategy,
    planned_route_uses_current_location,
    planned_route_origin_is_departure,
    provider_place_review_enabled,
    route_user_message,
    runtime_env,
    store,
    user_id,
    response_language: object = "zh-CN",
):
    response_language = normalize_language(response_language)
    async def plan_route_between_places(
        origin_query: str = "",
        destination_query: str = "",
        city: str = "全国",
        origin_near_query: str = "",
        destination_near_query: str = "",
        nearby_radius_meters: int = 5_000,
        route_mode: str = "default",
        route_strategy: str = "default",
        use_current_location_as_origin: bool = False,
        ordered_stops: list[dict[str, str]] | None = None,
        place_edits: list[dict[str, str]] | None = None,
    ) -> str:
        """Resolve an ordered itinerary and calculate one verified Tencent route.

        For a two-place request, pass origin_query and destination_query. For a
        multi-stop trip, pass ordered_stops in the user's exact order; every
        item contains query and may contain near_query. Never optimize or
        reorder user-provided stops. When a place is described relative to
        another place, keep them separate, for example
        Each relative stop keeps a separate query and near_query value.
        """
        map_key = str(
            runtime_env.get("TENCENT_MAP_SERVER_KEY")
            or runtime_env.get("TENCENT_MAP_KEY")
            or runtime_env.get("VITE_TENCENT_MAP_KEY")
            or ""
        )
        requested_route_mode = str(route_mode or "default").strip().lower()
        planner_route_mode = str(planned_route_mode or "default").strip().lower()
        requested_route_strategy = str(route_strategy or "default").strip().lower()
        planner_route_strategy = str(planned_route_strategy or "default").strip().lower()
        should_use_current_location = bool(
            browser_current_location
            and (use_current_location_as_origin or planned_route_uses_current_location)
            and not str(origin_query or "").strip()
        )
        if (
            (use_current_location_as_origin or planned_route_uses_current_location)
            and not browser_current_location
            and not str(origin_query or "").strip()
        ):
            return _clarification_action(
                conversation_id,
                title=text("route.location_required.title", response_language),
                prompt=text("route.location_required.prompt", response_language),
                fields=[{
                    "id": "route_origin",
                    "label": text("route.location_required.label", response_language),
                    "type": "text",
                    "required": True,
                    "options": [],
                    "placeholder": text(
                        "route.location_required.placeholder", response_language,
                    ),
                }],
            )
        route_operation_deadline = asyncio.get_running_loop().time() + 58.0
        radius = max(500, min(20_000, int(nearby_radius_meters or 5_000)))
        state = await _load_state()
        learning = state.setdefault("route_preference_learning", {
            "mode_counts": {},
            "strategy_counts": {},
        })
        learned_route_mode = (
            _learned_route_preference(
                learning,
                "mode_counts",
                {"driving", "transit", "walking", "bicycling"},
            )
            if map_learn_route_preferences
            else ""
        )
        learned_route_strategy = (
            _learned_route_preference(
                learning,
                "strategy_counts",
                {"time_then_cost", "least_time", "least_cost"},
            )
            if map_learn_route_preferences
            else ""
        )
        latest_route = (
            state.get("latest_route_plan")
            if isinstance(state.get("latest_route_plan"), dict)
            else {}
        )
        strategy_selection = select_route_strategy(
            requested_mode=requested_route_mode,
            planned_mode=planner_route_mode,
            context_mode=(
                str(latest_route.get("mode") or "") if place_edits else ""
            ),
            learned_mode=learned_route_mode,
            default_mode=map_preferred_route_mode,
            requested_strategy=requested_route_strategy,
            planned_strategy=planner_route_strategy,
            context_strategy=(
                str(latest_route.get("strategy") or "") if place_edits else ""
            ),
            learned_strategy=learned_route_strategy,
            default_strategy=map_route_strategy,
        )
        selected_route_mode = strategy_selection.mode
        selected_route_strategy = strategy_selection.strategy
        explicit_route_mode = strategy_selection.explicit_mode
        explicit_route_strategy = strategy_selection.explicit_strategy
        candidates = state.setdefault("place_candidates", {})
        for event in (state.get("schedules") or {}).values():
            extra = event.get("extra") if isinstance(event, dict) and isinstance(event.get("extra"), dict) else {}
            place = extra.get("place") if isinstance(extra, dict) else None
            if isinstance(place, dict) and str(place.get("place_id") or ""):
                candidates[str(place["place_id"])] = place

        def unresolved_place_card(
            endpoint_id: str,
            endpoint_label: str,
            query: str,
            near_query: str = "",
            *,
            timed_out: bool = False,
        ) -> str:
            qualifier = (
                text(
                    "route.near_qualifier", response_language,
                    place=near_query, radius=radius,
                )
                if str(near_query or "").strip()
                else ""
            )
            evidence_state = (
                text("route.evidence.timeout", response_language)
                if timed_out
                else text("route.evidence.missing", response_language)
            )
            return _clarification_action(
                conversation_id,
                title=text(
                    "route.confirm.title", response_language,
                    endpoint=endpoint_label,
                ),
                prompt=text(
                    "route.confirm.prompt", response_language,
                    evidence=evidence_state, query=query, qualifier=qualifier,
                ),
                fields=[{
                    "id": (
                        f"{endpoint_id}_"
                        f"{hashlib.sha256(str(query).encode()).hexdigest()[:6]}"
                    ),
                    "label": text(
                        "route.confirm.label", response_language,
                        endpoint=endpoint_label,
                    ),
                    "type": "text",
                    "required": True,
                    "options": [],
                    "placeholder": text(
                        "route.confirm.placeholder", response_language,
                        query=query,
                    ),
                }],
            )

        async def resolve(
            endpoint_id: str,
            endpoint_label: str,
            query: str,
            near_query: str,
        ) -> tuple[dict[str, Any] | None, str | None]:
            clean_query = str(query or "").strip()
            clean_near = str(near_query or "").strip()
            if clean_query == "__browser_current_location__":
                return copy.deepcopy(browser_current_location), None
            if not clean_query:
                raise ValueError(text(
                    "route.error.empty_place", response_language,
                    endpoint=endpoint_label,
                ))
            if clean_near:
                selected_anchor = _selected_place_candidate(
                    clean_near,
                    candidates,
                )
                anchors = (
                    [selected_anchor]
                    if selected_anchor is not None
                    else await _search_places_metered(
                        map_key, clean_near, city=city or "全国", limit=5,
                    )
                )
                if not anchors:
                    return None, unresolved_place_card(
                        endpoint_id,
                        endpoint_label,
                        clean_query,
                        clean_near,
                    )
                anchor = anchors[0]
                if len(anchors) > 1:
                    return None, _clarification_action(
                        conversation_id,
                        title=text("route.anchor.title", response_language),
                        prompt=text(
                            "route.anchor.prompt", response_language,
                            anchor=clean_near, endpoint=endpoint_label,
                            query=clean_query,
                        ),
                        fields=[_place_choice_field(
                            f"{endpoint_id}_anchor",
                            text("route.anchor.label", response_language),
                            anchors,
                            response_language,
                        )],
                    )
                matches = await _search_places_nearby_metered(
                    map_key,
                    clean_query,
                    anchor,
                    radius_meters=radius,
                    limit=6,
                )
            else:
                matches = _rank_verified_workspace_matches(
                    clean_query,
                    candidates,
                    city or "全国",
                    limit=6,
                )
                reused_workspace_candidates = bool(matches)
                if not matches:
                    matches = await _search_places_metered(
                        map_key, clean_query, city=city or "全国", limit=6,
                    )
                    reused_workspace_candidates = False
            if clean_near:
                reused_workspace_candidates = False
            if not matches:
                return None, unresolved_place_card(
                    endpoint_id,
                    endpoint_label,
                    clean_query,
                    clean_near,
                )
            matches = _prioritize_provider_candidates_for_city(
                matches,
                city or "全国",
            )
            if not reused_workspace_candidates:
                for match in matches:
                    place_id = str(match.get("place_id") or "").strip()
                    if place_id:
                        candidates[place_id] = match
            if len(candidates) > 200:
                state["place_candidates"] = dict(list(candidates.items())[-200:])

            # A brand near an anchor commonly has several legitimate branches.
            # Even when one branch has the exact bare brand name, choosing it
            # silently would be arbitrary; let the user pick from real nearby
            # candidates instead.
            if clean_near and len(matches) > 1:
                field = _place_choice_field(
                    endpoint_id,
                    text(
                        "route.choice.label", response_language,
                        endpoint=endpoint_label,
                    ),
                    matches,
                    response_language,
                )
                return None, _clarification_action(
                    conversation_id,
                    title=text("route.choice.title", response_language),
                    prompt=text(
                        "route.choice.nearby_prompt", response_language,
                        anchor=clean_near, query=clean_query,
                        endpoint=endpoint_label,
                    ),
                    fields=[field],
                )
            if len(matches) > 1:
                decision, selected, _reason = await _place_resolution_with_provider_review(
                    place_disambiguation_model,
                    clean_query,
                    matches,
                    context=endpoint_label,
                    enabled=provider_place_review_enabled,
                    timeout_seconds=min(8.0, map_search_timeout),
                    response_language=response_language,
                )
                if decision == "auto_use" and isinstance(selected, dict):
                    return selected, None
                field = _place_choice_field(
                    endpoint_id,
                    text(
                        "route.choice.label", response_language,
                        endpoint=endpoint_label,
                    ),
                    matches,
                    response_language,
                )
                return None, _clarification_action(
                    conversation_id,
                    title=text("route.choice.title", response_language),
                    prompt=text(
                        "route.choice.prompt", response_language,
                        query=clean_query, endpoint=endpoint_label,
                    ),
                    fields=[field],
                )
            return matches[0], None

        requested_stops: list[tuple[str, str]] = []
        requested_stop_field_ids: list[str] = []
        editing_latest_route = bool(place_edits)
        edited_uses_current_location = False
        route_origin_is_departure = bool(planned_route_origin_is_departure)
        if editing_latest_route:
            latest_stops = (
                latest_route.get("ordered_stops")
                if isinstance(latest_route.get("ordered_stops"), list)
                else []
            )
            latest_stops = [
                copy.deepcopy(stop)
                for stop in latest_stops
                if isinstance(stop, dict)
            ]
            if (
                not latest_stops
                and str(origin_query or "").strip()
                and str(destination_query or "").strip()
            ):
                # A resumed no-current-route card has now supplied a complete
                # fresh route, so the obsolete edit intent is safely dropped.
                editing_latest_route = False
                place_edits = []
        if editing_latest_route:
            if not latest_stops:
                return _clarification_action(
                    conversation_id,
                    title=text("route.edit.no_current.title", response_language),
                    prompt=text("route.edit.no_current.prompt", response_language),
                    fields=[
                        {
                            "id": "route_origin",
                            "label": text(
                                "route.location_required.label", response_language,
                            ),
                            "type": "text",
                            "required": True,
                            "options": [],
                            "placeholder": text(
                                "route.location_required.placeholder", response_language,
                            ),
                        },
                        {
                            "id": "route_destination",
                            "label": text(
                                "route.edit.no_current.label", response_language,
                            ),
                            "type": "text",
                            "required": True,
                            "options": [],
                            "placeholder": text(
                                "route.edit.no_current.placeholder", response_language,
                            ),
                        },
                    ],
                )
            for stop in latest_stops:
                place_id = str(stop.get("place_id") or "").strip()
                if place_id and not stop.get("ephemeral"):
                    candidates[place_id] = copy.deepcopy(stop)
            normalized_edits: list[RoutePlaceEdit] = []
            for raw_edit in (place_edits or [])[:8]:
                if isinstance(raw_edit, BaseModel):
                    raw_edit = raw_edit.model_dump()
                if not isinstance(raw_edit, dict):
                    continue
                operation = str(raw_edit.get("operation") or "").strip().lower()
                if operation not in {"add", "remove", "replace"}:
                    continue
                position = str(raw_edit.get("position") or "default").strip().lower()
                normalized_edits.append(RoutePlaceEdit(
                    operation=operation,
                    target_query=str(raw_edit.get("target_query") or "").strip()[:160],
                    new_query=str(raw_edit.get("new_query") or "").strip()[:160],
                    new_near_query=str(
                        raw_edit.get("new_near_query") or ""
                    ).strip()[:160],
                    position=(
                        position
                        if position in {"default", "start", "end", "before", "after"}
                        else "default"
                    ),
                ))
            edit_result = apply_route_place_edits(latest_stops, normalized_edits)
            if edit_result.issues:
                issue = edit_result.issues[0]
                if issue.field == "target":
                    field = _place_choice_field(
                        f"route_edit_target_{issue.edit_index}",
                        text("route.edit.target.label", response_language),
                        list(issue.candidates),
                        response_language,
                    )
                    field["allow_custom_input"] = False
                    field.pop("custom_placeholder", None)
                    await _save_state(state)
                    return _clarification_action(
                        conversation_id,
                        title=text("route.edit.target.title", response_language),
                        prompt=text(
                            "route.edit.target.prompt", response_language,
                            query=issue.query,
                        ),
                        fields=[field],
                    )
                await _save_state(state)
                return _clarification_action(
                    conversation_id,
                    title=text("route.edit.new.title", response_language),
                    prompt=text("route.edit.new.prompt", response_language),
                    fields=[{
                        "id": f"route_edit_new_{issue.edit_index}",
                        "label": text("route.edit.new.label", response_language),
                        "type": "text",
                        "required": True,
                        "options": [],
                        "placeholder": text(
                            "route.edit.new.placeholder", response_language,
                        ),
                    }],
                )
            if len(edit_result.stops) < 2:
                await _save_state(state)
                return _clarification_action(
                    conversation_id,
                    title=text("route.edit.new.title", response_language),
                    prompt=text("route.edit.too_few", response_language),
                    fields=[{
                        "id": f"route_edit_new_{len(normalized_edits)}",
                        "label": text("route.edit.new.label", response_language),
                        "type": "text",
                        "required": True,
                        "options": [],
                        "placeholder": text(
                            "route.edit.new.placeholder", response_language,
                        ),
                    }],
                )
            for index, stop in enumerate(edit_result.stops):
                edit_index = edit_result.new_stop_edit_indexes[index]
                if edit_index is not None:
                    requested_stops.append((
                        str(stop.get("query") or "").strip(),
                        str(stop.get("near_query") or "").strip(),
                    ))
                    requested_stop_field_ids.append(f"route_edit_new_{edit_index}")
                    continue
                if stop.get("ephemeral"):
                    if index == 0 and browser_current_location:
                        requested_stops.append(("__browser_current_location__", ""))
                        requested_stop_field_ids.append("")
                        edited_uses_current_location = True
                        continue
                    if index == 0 and str(origin_query or "").strip():
                        requested_stops.append((str(origin_query).strip(), ""))
                        requested_stop_field_ids.append("route_origin")
                        continue
                    return _clarification_action(
                        conversation_id,
                        title=text("route.location_required.title", response_language),
                        prompt=text("route.location_required.prompt", response_language),
                        fields=[{
                            "id": "route_origin",
                            "label": text(
                                "route.location_required.label", response_language,
                            ),
                            "type": "text",
                            "required": True,
                            "options": [],
                            "placeholder": text(
                                "route.location_required.placeholder", response_language,
                            ),
                        }],
                    )
                place_id = str(stop.get("place_id") or "").strip()
                requested_stops.append((
                    f"floris-place:{place_id}" if place_id else str(stop.get("name") or ""),
                    "",
                ))
                requested_stop_field_ids.append("")
            route_origin_is_departure = bool(
                latest_route.get("explicit_origin_is_departure")
            )
            if (
                (not city or city == "全国")
                and str(next((
                    stop.get("city")
                    for stop in latest_stops
                    if str(stop.get("city") or "").strip()
                ), "")).strip()
            ):
                city = str(next(
                    stop.get("city")
                    for stop in latest_stops
                    if str(stop.get("city") or "").strip()
                ))[:80]
        elif ordered_stops:
            minimum_stops = 1 if should_use_current_location else 2
            if (
                not isinstance(ordered_stops, list)
                or not minimum_stops <= len(ordered_stops) <= map_route_stop_limit
            ):
                raise ValueError(text(
                    "route.error.stop_count", response_language,
                    minimum=minimum_stops, maximum=map_route_stop_limit,
                ))
            for index, raw_stop in enumerate(ordered_stops, 1):
                if isinstance(raw_stop, BaseModel):
                    raw_stop = raw_stop.model_dump()
                if not isinstance(raw_stop, dict):
                    raise ValueError(text(
                        "route.error.stop_format", response_language,
                        index=index,
                    ))
                query = str(raw_stop.get("query") or "").strip()
                near_query = str(raw_stop.get("near_query") or "").strip()
                if not query:
                    raise ValueError(text(
                        "route.error.stop_empty", response_language,
                        index=index,
                    ))
                requested_stops.append((query, near_query))
                requested_stop_field_ids.append("")
        else:
            requested_stops = [
                (str(origin_query or "").strip(), str(origin_near_query or "").strip()),
                (str(destination_query or "").strip(), str(destination_near_query or "").strip()),
            ]
            requested_stop_field_ids = ["", ""]
        model_stop_count = len(requested_stops)
        if not editing_latest_route:
            requested_stops = preserve_planned_route_stops(
                requested_stops,
                planned_route_stops,
                route_user_message,
            )
            requested_stop_field_ids = [""] * len(requested_stops)
        if should_use_current_location:
            requested_stops = [
                ("__browser_current_location__", ""),
                *[item for item in requested_stops if item[0]],
            ]
            requested_stop_field_ids = ["", *requested_stop_field_ids]
        if len(requested_stops) > map_route_stop_limit:
            raise ValueError(text(
                "route.error.stop_limit", response_language,
                maximum=map_route_stop_limit,
            ))
        logging.info(
            "route stop handoff planner=%s tool_model=%s selected=%s",
            len(planned_route_stops or []),
            model_stop_count,
            len(requested_stops),
        )
        if (not city or city == "全国") and str(planned_route_city or "").strip():
            city = str(planned_route_city).strip()[:80]

        route_search_semaphore = asyncio.Semaphore(map_parallelism)
        resolution_timeout = max(
            3.0,
            min(
                map_search_timeout + 12.0,
                route_operation_deadline - asyncio.get_running_loop().time() - 9.0,
            ),
        )

        async def resolve_indexed(
            index: int, query: str, near_query: str,
        ) -> tuple[dict[str, Any] | None, str | None]:
            default_endpoint_id, endpoint_label = (
                ("route_origin", text("route.origin", response_language))
                if index == 1
                else (
                    "route_destination",
                    text("route.destination", response_language),
                )
                if index == len(requested_stops)
                else (
                    f"route_stop_{index}",
                    text("route.stop", response_language, index=index),
                )
            )
            endpoint_id = (
                requested_stop_field_ids[index - 1]
                if index - 1 < len(requested_stop_field_ids)
                and requested_stop_field_ids[index - 1]
                else default_endpoint_id
            )

            async def resolve_with_capacity():
                async with route_search_semaphore:
                    return await resolve(
                        endpoint_id, endpoint_label, query, near_query,
                    )

            try:
                # The deadline includes time waiting for a search slot. This
                # keeps a large stop list inside the route-wide 58 s budget.
                return await asyncio.wait_for(
                    resolve_with_capacity(),
                    timeout=resolution_timeout,
                )
            except TimeoutError:
                return None, unresolved_place_card(
                    endpoint_id,
                    endpoint_label,
                    query,
                    near_query,
                    timed_out=True,
                )

        resolution_results = await asyncio.gather(*(
            resolve_indexed(index, query, near_query)
            for index, (query, near_query) in enumerate(requested_stops, 1)
        ))
        card_city = (
            _normalized_place_name(city)
            if city and _normalized_place_name(city) not in {"全国", "中国"}
            else _provider_city_consensus([
                place
                for place, _clarification in resolution_results
                if isinstance(place, dict)
            ])
        )
        if card_city:
            resolution_results = [
                (
                    place,
                    _prioritize_clarification_options_for_city(
                        clarification,
                        candidates,
                        card_city,
                        response_language,
                    )
                    if clarification
                    else None,
                )
                for place, clarification in resolution_results
            ]

        unresolved_cards = [
            clarification
            for _place, clarification in resolution_results
            if clarification
        ]
        if unresolved_cards:
            await _save_state(state)
            return _merge_clarification_actions(
                conversation_id,
                unresolved_cards,
                response_language=response_language,
            )

        resolved_stops: list[dict[str, Any]] = []
        for index, (place, clarification) in enumerate(resolution_results, 1):
            endpoint = (
                text("route.origin", response_language) if index == 1
                else text("route.destination", response_language)
                if index == len(requested_stops)
                else text("route.stop", response_language, index=index)
            )
            if not place:
                raise ValueError(text(
                    "route.error.unverified", response_language,
                    endpoint=endpoint,
                ))
            if (
                resolved_stops
                and str(resolved_stops[-1].get("place_id") or "")
                == str(place.get("place_id") or "")
            ):
                raise ValueError(text(
                    "route.error.duplicate", response_language,
                    endpoint=endpoint,
                ))
            resolved_stops.append(place)

        remaining_route_time = route_operation_deadline - asyncio.get_running_loop().time()
        if remaining_route_time <= 1:
            raise TimeoutError(text(
                "route.error.timeout_near", response_language,
            ))
        route = await load_route_cache(
            store,
            user_id,
            resolved_stops,
            False,
            mode=selected_route_mode,
            strategy=selected_route_strategy,
            near_time_tolerance_minutes=map_near_time_tolerance,
        )
        if route is not None and bool((route.get("cache") or {}).get("hit")):
            missing_city_indexes = [
                index for index, place in enumerate(resolved_stops)
                if not str(place.get("city") or "").strip()
                and isinstance(place.get("latitude"), (int, float))
                and isinstance(place.get("longitude"), (int, float))
            ]
            if missing_city_indexes:
                administrative_semaphore = asyncio.Semaphore(map_parallelism)

                async def enrich_administrative_metadata(index: int):
                    place = copy.deepcopy(resolved_stops[index])
                    async with administrative_semaphore:
                        metadata = await _reverse_geocode_metered(map_key, place)
                    if isinstance(metadata, dict):
                        administrative_city = (
                            metadata.get("city") or metadata.get("province")
                        )
                        if administrative_city:
                            place["city"] = str(administrative_city)[:80]
                        if not place.get("address") and metadata.get("address"):
                            place["address"] = str(metadata["address"])[:240]
                    return index, place

                metadata_budget = min(
                    12.0,
                    route_operation_deadline
                    - asyncio.get_running_loop().time()
                    - 1.0,
                )
                if metadata_budget > 0.5:
                    try:
                        enriched_places = await asyncio.wait_for(
                            asyncio.gather(*(
                                enrich_administrative_metadata(index)
                                for index in missing_city_indexes
                            )),
                            timeout=metadata_budget,
                        )
                        for index, place in enriched_places:
                            resolved_stops[index] = place
                    except Exception as exc:
                        logging.warning(
                            "cached route administrative enrichment failed: %s",
                            type(exc).__name__,
                        )
        if route is None:
            try:
                route = await asyncio.wait_for(
                    _plan_route_metered(
                        map_key,
                        resolved_stops,
                        optimize=False,
                        mode=selected_route_mode,
                        strategy=selected_route_strategy,
                        near_time_tolerance_minutes=map_near_time_tolerance,
                    ),
                    # The selected mode comes from the explicit request, semantic
                    # plan, or user setting—in that order.
                    timeout=remaining_route_time,
                )
            except asyncio.TimeoutError as exc:
                raise TimeoutError(text(
                    "route.error.timeout", response_language,
                )) from exc
            await save_route_cache(
                store,
                user_id,
                resolved_stops,
                False,
                route,
                mode=selected_route_mode,
                strategy=selected_route_strategy,
                near_time_tolerance_minutes=map_near_time_tolerance,
            )
        route = _normalize_route_contract(route, resolved_stops)
        provider_places = route.get("places")
        if isinstance(provider_places, list) and len(provider_places) == len(resolved_stops):
            current_resolution = list(resolved_stops)
            resolved_stops = [
                copy.deepcopy(item)
                for item in provider_places
                if isinstance(item, dict)
            ]
            # A cached road route is keyed by canonical provider place ids and
            # intentionally ignores how the user spelled a stop. Preserve the
            # current lookup's Tencent-backed correction evidence when cached
            # normalized places replace this turn's resolved candidates.
            if len(resolved_stops) == len(current_resolution):
                for resolved, current in zip(resolved_stops, current_resolution):
                    correction = current.get("query_correction")
                    if isinstance(correction, dict):
                        resolved["query_correction"] = copy.deepcopy(correction)
                    else:
                        resolved.pop("query_correction", None)
            await save_route_cache(
                store,
                user_id,
                resolved_stops,
                False,
                route,
                mode=selected_route_mode,
                strategy=selected_route_strategy,
                near_time_tolerance_minutes=map_near_time_tolerance,
            )
        distance_meters = float(route.get("distance_meters") or 0)
        duration_seconds = float(route.get("duration_seconds") or 0)
        query_corrections = [
            copy.deepcopy(place.get("query_correction"))
            for place in resolved_stops
            if isinstance(place.get("query_correction"), dict)
        ]
        for place in resolved_stops:
            if not place.get("ephemeral"):
                candidates[str(place["place_id"])] = place
        route_plan_id = "routeplan-" + hashlib.sha256(
            (
                "|".join(str(place.get("place_id") or "") for place in resolved_stops)
                + f":{time.time_ns()}"
            ).encode()
        ).hexdigest()[:16]
        persisted_route_stops = [
            (
                {
                    "place_id": str(place.get("place_id") or ""),
                    "name": str(place.get("name") or ""),
                    "provider": str(place.get("provider") or "browser"),
                    "ephemeral": True,
                }
                if place.get("ephemeral")
                else copy.deepcopy(place)
            )
            for place in resolved_stops
        ]
        route_plan = {
            "id": route_plan_id,
            "created_at": int(time.time()),
            "ordered_stops": persisted_route_stops,
            "implicit_browser_origin": bool(
                should_use_current_location or edited_uses_current_location
            ),
            "explicit_origin_is_departure": bool(
                not (should_use_current_location or edited_uses_current_location)
                and route_origin_is_departure
            ),
            "query_corrections": query_corrections,
            "distance_meters": round(distance_meters),
            "duration_seconds": round(duration_seconds),
            "mode": selected_route_mode,
            "strategy": selected_route_strategy,
            "selection": copy.deepcopy(route.get("selection") or {}),
            "legs": [
                _route_plan_leg_summary(leg, selected_route_mode)
                for leg in (route.get("legs") or [])
                if isinstance(leg, dict)
            ][:11],
            "calendar_hint": str(planned_route_calendar_hint or "").strip()[:240],
        }
        state["latest_route_plan"] = route_plan
        route_plans = state.setdefault("route_plans", {})
        route_plans[route_plan_id] = copy.deepcopy(route_plan)
        state["route_plans"] = dict(sorted(
            (
                (plan_id, plan)
                for plan_id, plan in route_plans.items()
                if isinstance(plan, dict) and str(plan.get("id") or "") == plan_id
            ),
            key=lambda item: int(item[1].get("created_at") or 0),
            reverse=True,
        )[:8])
        map_action = new_action(
            "map_recommendation",
            {
                "title": (
                    f"{resolved_stops[0].get('name') or text('route.origin', response_language)}"
                    f" → {resolved_stops[-1].get('name') or text('route.destination', response_language)}"
                ),
                "action_text": text("route.action_text", response_language),
                "places": resolved_stops,
                "route_plan_id": route_plan_id,
                "route_mode": selected_route_mode,
                "route_strategy": selected_route_strategy,
                # Publish the exact Tencent-verified geometry that grounded
                # this answer. Clients must reuse this component snapshot
                # instead of paying for and potentially displaying a
                # different second /routes plan when the card is opened.
                "route": copy.deepcopy(route),
                "preference_signal": (
                    {
                        **({"mode": explicit_route_mode} if explicit_route_mode else {}),
                        **(
                            {"strategy": explicit_route_strategy}
                            if explicit_route_strategy else {}
                        ),
                    }
                    if map_learn_route_preferences
                    and (explicit_route_mode or explicit_route_strategy)
                    else {}
                ),
                "show_route": True,
                # The route remains independently useful. When Calendar is
                # enabled, the same durable route card can explicitly start a
                # second turn that reuses this verified route and prepares a
                # separate confirmation proposal.
                "calendar_offer": bool(
                    calendar_skill_id
                    and (
                        enabled_skills is None
                        or calendar_skill_id in enabled_skills
                    )
                ),
            },
            requires_confirmation=False,
        )
        put_action(state, map_action)
        await _save_state(state)
        model_action = copy.deepcopy(map_action)
        model_action.get("payload", {}).pop("route", None)
        return json.dumps({
            "ui_action": "map_action",
            # Keep provider geometry out of the model-visible ToolMessage.
            # The stream layer restores the durable action from Maker state
            # before publishing it to clients.
            "action": model_action,
            "route_plan_id": route_plan_id,
            "origin": resolved_stops[0],
            "destination": resolved_stops[-1],
            "ordered_stops": resolved_stops,
            "route": {
                "provider": route.get("provider"),
                "mode": route.get("mode") or "driving",
                "distance_meters": round(distance_meters),
                "distance_kilometers": round(distance_meters / 1000, 1),
                "duration_seconds": round(duration_seconds),
                "duration_minutes": max(1, round(duration_seconds / 60)),
                "fare": route.get("fare") or {},
                "transit": route.get("transit") or {},
                "selection": route.get("selection") or {},
            },
            "evidence_contract": {
                "strict": True,
                "aggregate_only": [
                    "route.distance_meters",
                    "route.distance_kilometers",
                    "route.duration_seconds",
                    "route.duration_minutes",
                    "route.transit.walking_distance_meters",
                ],
                "permitted_transit_segment_fields": [
                    "line", "vehicle", "geton", "getoff", "station_count",
                ],
                "unknown_fields": [
                    "operating_hours",
                    "service_days",
                    "service_frequency",
                    "travel_direction",
                    "roads",
                    "entrance_rules",
                    "walking_segment_distances",
                    "alternative_lines",
                ],
                "instruction": (
                    "Only claims directly represented by the route object are "
                    "grounded. Aggregate-only values must never be assigned to "
                    "one leg. Unknown fields must not be inferred or mentioned."
                ),
            },
            "response_constraint": text(
                "model.route.response_constraint", response_language,
                count=len(resolved_stops), mode=selected_route_mode,
                strategy=selected_route_strategy,
                tolerance=map_near_time_tolerance,
                correction_clause=text(
                    "model.route.correction_clause", response_language,
                ) if query_corrections else "",
            ),
        }, ensure_ascii=False)

    return plan_route_between_places
