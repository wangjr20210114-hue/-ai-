"""Trusted calendar proposal operation backed by Makers user state."""

from __future__ import annotations

import asyncio
import copy
import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from ..._application.i18n import normalize_language, text
from ..._application.workspace.service import (
    apply_calendar_changes,
    calendar_change_warnings,
    new_action,
    put_action,
    validate_calendar_change_window,
)
from ..._domain.maps.route_chain import current_route_plan, route_plan_by_id
from ..._infrastructure.makers.route_repository import load_route_cache, save_route_cache
from .route_resolution import (
    _clarification_action,
    _normalized_place_name,
    _parse_datetime,
    _place_choice_field,
    _place_option_label,
    _place_resolution_with_provider_review,
)


def build_calendar_operation(
    *,
    _load_state,
    _plan_route_metered,
    _save_state,
    _search_places_metered,
    browser_current_location,
    conversation_id,
    enabled_skills,
    map_search_timeout,
    place_disambiguation_model,
    place_skill_id,
    planned_reuse_latest_route,
    provider_place_review_enabled,
    provider_schedule_limit,
    requested_route_plan_id,
    route_gap_hours,
    runtime_env,
    store,
    travel_buffer_minutes,
    user_id,
    response_language: object = "zh-CN",
):
    response_language = normalize_language(response_language)
    async def propose_calendar_changes(
        summary: str,
        changes: list[dict] | None = None,
        source_route_plan_id: str = "",
        route_start_time: str = "",
        route_stop_minutes: int = 90,
    ) -> str:
        """Prepare create/update/delete changes; the calendar is mutated only after UI confirmation."""
        state = await _load_state()
        changes = changes if isinstance(changes, list) else []
        candidates = state.get("place_candidates", {})
        latest_route = current_route_plan(state, conversation_id)
        route_source_id = str(
            requested_route_plan_id or source_route_plan_id or ""
        ).strip()
        if not route_source_id and planned_reuse_latest_route and isinstance(latest_route, dict):
            route_source_id = str(latest_route.get("id") or "").strip()
        if not route_source_id and isinstance(latest_route, dict):
            # Infer the route link before normalizing event durations. This
            # lets the adapter safely represent an instantaneous verified
            # departure/arrival marker even if the model omitted only the
            # redundant source id. Identity still comes exclusively from the
            # recent provider-backed route and submitted place ids.
            route_age = int(time.time()) - int(latest_route.get("created_at") or 0)
            route_place_ids = {
                str(item.get("place_id") or "")
                for item in (latest_route.get("ordered_stops") or [])
                if isinstance(item, dict) and str(item.get("place_id") or "")
            }
            submitted_place_ids = set()
            for raw_change in changes:
                if not isinstance(raw_change, dict):
                    continue
                raw_event = (
                    raw_change.get("event")
                    if isinstance(raw_change.get("event"), dict)
                    else raw_change
                )
                raw_place_id = str(
                    raw_event.get("place_id")
                    or raw_event.get("location_place_id")
                    or ""
                ).strip()
                if raw_place_id:
                    submitted_place_ids.add(raw_place_id)
            if (
                0 <= route_age <= 10_800
                and len(route_place_ids & submitted_place_ids) >= 2
            ):
                route_source_id = str(latest_route.get("id") or "")
        linked_route = route_plan_by_id(
            state, conversation_id, route_source_id,
        )
        if (
            not linked_route
            and route_source_id
            and isinstance(latest_route, dict)
            and route_source_id == str(latest_route.get("id") or "")
        ):
            # Workspaces created before route chains were introduced still
            # expose one valid migration source through the compatibility
            # view resolved above.
            linked_route = latest_route
        linked_calendar_stops = [
            stop
            for stop in (
                (linked_route.get("ordered_stops") or [])
                if isinstance(linked_route, dict)
                else []
            )
            if isinstance(stop, dict) and str(stop.get("place_id") or "")
        ]
        if (
            isinstance(linked_route, dict)
            and linked_route.get("implicit_browser_origin")
            and linked_calendar_stops
        ):
            linked_calendar_stops = linked_calendar_stops[1:]
        # The route continuation is a trusted adapter boundary. When the UI
        # carries the route id, do not make the model copy every stop and
        # schedule timestamp back into a fragile tool call. Ask only for the
        # missing user-owned timing choices, then derive the ordered proposal
        # from the provider-verified route below.
        route_continuation = bool(
            isinstance(linked_route, dict)
            and route_source_id
            and (planned_reuse_latest_route or requested_route_plan_id)
        )
        if route_continuation and linked_calendar_stops and route_start_time:
            stop_minutes = max(15, min(720, int(route_stop_minutes or 90)))
            start = _parse_datetime(route_start_time)
            leg_data = linked_route.get("legs") if isinstance(linked_route, dict) else []
            implicit_origin = bool(linked_route.get("implicit_browser_origin"))
            explicit_origin_is_departure = bool(
                linked_route.get("explicit_origin_is_departure")
            )
            all_route_stops = [
                stop
                for stop in (linked_route.get("ordered_stops") or [])
                if isinstance(stop, dict) and str(stop.get("place_id") or "")
            ]
            generated_changes: list[dict[str, Any]] = []
            current = start
            for index, stop in enumerate(linked_calendar_stops):
                if implicit_origin:
                    incoming_seconds = (
                        max(
                            0,
                            int(float((leg_data[index] or {}).get("duration_seconds") or 0)),
                        )
                        if isinstance(leg_data, list) and index < len(leg_data)
                        else 0
                    )
                    arrival = current + timedelta(seconds=incoming_seconds)
                    end = arrival + timedelta(minutes=stop_minutes)
                    previous_stop = (
                        all_route_stops[index]
                        if index < len(all_route_stops)
                        else {}
                    )
                    generated_changes.append({
                        "operation": "create",
                        "event": {
                            "title": text(
                                "calendar.route_event.travel_title",
                                response_language,
                                origin=str(
                                    previous_stop.get("name")
                                    or text(
                                        "calendar.route_event.current_origin",
                                        response_language,
                                    )
                                )[:100],
                                place=str(
                                    stop.get("name")
                                    or text(
                                        "calendar.route_event.default_place",
                                        response_language,
                                    )
                                )[:100],
                            ),
                            # Block the complete journey from departure through
                            # the destination stay. The transient browser origin
                            # remains only a display label; its coordinates and
                            # address are never copied into Calendar state.
                            "start_time": current.isoformat(),
                            "end_time": end.isoformat(),
                            "place_id": str(stop.get("place_id") or ""),
                            "location_kind": "physical",
                            "description": text(
                                "calendar.route_event.travel_description",
                                response_language,
                            ),
                        },
                    })
                    current = end
                    continue
                # For an explicit route, the first stop is the departure
                # point—not a sight to visit for ``route_stop_minutes``. Keep
                # a one-minute departure marker, then start the first Tencent
                # travel leg at the user's requested departure time.
                departure_marker = (
                    not implicit_origin
                    and explicit_origin_is_departure
                    and index == 0
                )
                end = current + timedelta(
                    minutes=1 if departure_marker else stop_minutes
                )
                generated_changes.append({
                    "operation": "create",
                    "event": {
                        "title": text(
                            (
                                "calendar.route_event.departure_title"
                                if departure_marker
                                else "calendar.route_event.title"
                            ),
                            response_language,
                            index=index + 1,
                            place=str(
                                stop.get("name")
                                or text(
                                    "calendar.route_event.default_place",
                                    response_language,
                                )
                            )[:100],
                        ),
                        "start_time": current.isoformat(),
                        "end_time": end.isoformat(),
                        "place_id": str(stop.get("place_id") or ""),
                        "location_kind": "physical",
                        "description": text(
                            (
                                "calendar.route_event.departure_description"
                                if departure_marker
                                else "calendar.route_event.description"
                            ),
                            response_language,
                        ),
                    },
                })
                current = current if departure_marker else end
                leg_index = index + (1 if implicit_origin else 0)
                if isinstance(leg_data, list) and leg_index < len(leg_data):
                    current += timedelta(
                        seconds=max(0, int(float((leg_data[leg_index] or {}).get("duration_seconds") or 0)))
                    )
            changes = generated_changes
        elif route_continuation and linked_calendar_stops and (
            len(changes) != len(linked_calendar_stops)
        ):
            return _clarification_action(
                conversation_id,
                title=text("calendar.route_schedule.title", response_language),
                prompt=text("calendar.route_schedule.prompt", response_language),
                fields=[
                    {
                        "id": "route_calendar_start",
                        "label": text(
                            "calendar.route_schedule.departure", response_language,
                        ),
                        "type": "datetime",
                        "required": True,
                        "options": [],
                        "placeholder": text(
                            "calendar.route_schedule.departure_placeholder",
                            response_language,
                        ),
                    },
                    {
                        "id": "route_calendar_stop_minutes",
                        "label": text(
                            "calendar.route_schedule.stay", response_language,
                        ),
                        "type": "single",
                        "required": True,
                        "options": [
                            text(
                                "calendar.route_schedule.minutes",
                                response_language,
                                minutes=minutes,
                            )
                            for minutes in (60, 90, 120)
                        ],
                        "option_values": {
                            text(
                                "calendar.route_schedule.minutes",
                                response_language,
                                minutes=minutes,
                            ): str(minutes)
                            for minutes in (60, 90, 120)
                        },
                    },
                ],
            )
        if not 1 <= len(changes) <= 24:
            raise ValueError(text("calendar.error.change_count", response_language))
        if isinstance(linked_route, dict):
            for stop in linked_route.get("ordered_stops") or []:
                if not isinstance(stop, dict) or stop.get("ephemeral"):
                    continue
                stop_id = str(stop.get("place_id") or "").strip()
                if stop_id:
                    candidates.setdefault(stop_id, copy.deepcopy(stop))
        implicit_route_origin = (
            (linked_route.get("ordered_stops") or [None])[0]
            if (
                isinstance(linked_route, dict)
                and linked_route.get("implicit_browser_origin")
                and (linked_route.get("ordered_stops") or [])
            )
            else None
        )
        ephemeral_place_ids = {
            str(place.get("place_id") or "")
            for place in (browser_current_location, implicit_route_origin)
            if isinstance(place, dict) and str(place.get("place_id") or "")
        }
        linked_route_place_ids = {
            str(place.get("place_id") or "")
            for place in (
                (linked_route.get("ordered_stops") or [])
                if isinstance(linked_route, dict)
                else []
            )
            if isinstance(place, dict) and str(place.get("place_id") or "")
        }
        submitted_create_count = sum(
            1
            for raw_change in changes
            if isinstance(raw_change, dict)
            and str(raw_change.get("operation") or "create") == "create"
        )
        can_bind_route_order = bool(
            route_source_id
            and linked_calendar_stops
            and submitted_create_count == len(linked_calendar_stops)
        )
        linked_create_index = 0
        normalization_warnings: list[str] = []
        skipped_changes: list[dict[str, str]] = []
        normalized = []
        for change_index, raw in enumerate(changes, 1):
            if not isinstance(raw, dict):
                raise ValueError(text(
                    "calendar.error.change_format", response_language,
                ))
            operation = str(raw.get("operation") or "create")
            if operation not in {"create", "update", "delete"}:
                raise ValueError(text(
                    "calendar.error.operation", response_language,
                ))
            change: dict[str, Any] = {"operation": operation}
            previous_event: dict[str, Any] = {}
            if operation in {"update", "delete"}:
                schedule_id = str(raw.get("schedule_id") or "")
                if schedule_id not in state.get("schedules", {}):
                    event = raw.get("event") if isinstance(raw.get("event"), dict) else {}
                    label = str(
                        event.get("title")
                        or raw.get("title")
                        or schedule_id
                        or text(
                            "calendar.change.default_target", response_language,
                            index=change_index,
                        )
                    ).strip()[:120]
                    skipped_changes.append({
                        "operation": operation,
                        "target": label,
                        "reason": text(
                            "calendar.change.missing", response_language,
                        ),
                    })
                    continue
                change["schedule_id"] = schedule_id
                previous_event = state.get("schedules", {}).get(schedule_id) or {}
            if operation != "delete":
                nested_event = raw.get("event")
                # Some tool-calling models flatten list-item fields. Accept
                # both wire shapes, then normalize into the canonical contract.
                event = nested_event if isinstance(nested_event, dict) else raw
                title = str(event.get("title") or event.get("name") or "").strip()[:120]
                start_value = str(event.get("start_time") or event.get("start") or "").strip()
                if operation == "create" and (not title or not start_value):
                    raise ValueError(text(
                        "calendar.error.create_fields", response_language,
                    ))
                event_place_id = str(
                    event.get("place_id") or event.get("location_place_id") or ""
                ).strip()
                if operation == "create" and can_bind_route_order:
                    expected_stop = linked_calendar_stops[linked_create_index]
                    linked_create_index += 1
                    expected_place_id = str(expected_stop.get("place_id") or "")
                    if event_place_id != expected_place_id:
                        # The route id and complete event count freeze the
                        # provider-backed station sequence. Repairing transport
                        # omissions here avoids a second model round without
                        # inferring anything from titles or place-language rules.
                        event_place_id = expected_place_id
                        warning = text(
                            "calendar.warning.route_places", response_language,
                        )
                        if warning not in normalization_warnings:
                            normalization_warnings.append(warning)
                normalized_event: dict[str, Any] = {}
                if title:
                    normalized_event["title"] = title
                end_value = str(event.get("end_time") or event.get("end") or "").strip()
                if start_value:
                    start = _parse_datetime(start_value)
                    normalized_event["start_time"] = int(start.timestamp())
                    if end_value:
                        end = _parse_datetime(end_value)
                    elif operation == "update":
                        end = start + timedelta(
                            minutes=max(1, int(previous_event.get("duration_minutes") or 60))
                        )
                    else:
                        end = start + timedelta(hours=1)
                    if (
                        end == start
                        and operation == "create"
                        and event_place_id in linked_route_place_ids
                    ):
                        # Calendar storage requires a positive interval, while
                        # route-derived departure/arrival markers are naturally
                        # instantaneous. Preserve the selected timestamp and
                        # verified stop at the minimum calendar granularity.
                        # The proposal remains editable and still needs consent.
                        end = start + timedelta(minutes=1)
                        normalization_warnings.append(text(
                            "calendar.warning.instant_event", response_language,
                        ))
                    if end <= start:
                        raise ValueError(text(
                            "calendar.error.end_before_start", response_language,
                            title=title,
                        ))
                    normalized_event["duration_minutes"] = max(1, int((end - start).total_seconds() // 60))
                elif end_value and operation == "update":
                    start = datetime.fromtimestamp(int(previous_event.get("start_time") or 0), timezone.utc)
                    end = _parse_datetime(end_value)
                    if end <= start:
                        raise ValueError(text(
                            "calendar.error.end_before_start", response_language,
                            title=(
                                title
                                or previous_event.get("title")
                                or text("calendar.event.default", response_language)
                            ),
                        ))
                    normalized_event["duration_minutes"] = max(1, int((end - start).total_seconds() // 60))
                elif "duration_minutes" in event:
                    normalized_event["duration_minutes"] = max(1, min(10_080, int(event.get("duration_minutes") or 60)))
                for key in ("category", "description", "done"):
                    if key in event:
                        normalized_event[key] = event[key]
                place_id = event_place_id
                location_text = str(event.get("location") or "").strip()
                if place_id and place_id in ephemeral_place_ids:
                    # Browser coordinates are request-scoped routing input.
                    # Keep a useful departure reminder, but never persist its
                    # transient place object or readable address in a calendar.
                    place_id = ""
                    location_text = ""
                    normalized_event["location"] = ""
                clear_location = bool(event.get("clear_location", False))
                location_kind = str(event.get("location_kind") or "").strip().lower()
                if location_kind not in {"", "physical", "online"}:
                    raise ValueError(text(
                        "calendar.error.location_kind", response_language,
                    ))
                online_location = bool(location_text and location_kind == "online")
                if clear_location:
                    place_id = ""
                    location_text = ""
                    normalized_event["place"] = None
                    normalized_event["location"] = ""
                elif online_location:
                    normalized_event["location"] = location_text
                    normalized_event["location_kind"] = "online"
                if location_text and not place_id:
                    if online_location:
                        change["event"] = normalized_event
                        normalized.append(change)
                        continue
                    # A route or place tool in an earlier turn has already
                    # persisted verified candidates.  Reuse an unambiguous
                    # match instead of making the model transport a fragile
                    # provider id across turns.  This remains provider-backed:
                    # free-form locations that were never verified are refused.
                    normalized_location = _normalized_place_name(location_text)
                    matched = [
                        (candidate_id, candidate)
                        for candidate_id, candidate in candidates.items()
                        if isinstance(candidate, dict)
                        and normalized_location
                        and _normalized_place_name(candidate.get("name"))
                        and (
                            normalized_location == _normalized_place_name(candidate.get("name"))
                            or normalized_location == _normalized_place_name(candidate.get("address"))
                            or normalized_location == _normalized_place_name(
                                _place_option_label(candidate)
                            )
                        )
                    ]
                    if len(matched) == 1:
                        place_id = str(matched[0][0])
                    elif len(matched) > 1:
                        raise ValueError(text(
                            "calendar.error.ambiguous_place", response_language,
                            place=location_text,
                        ))
                    else:
                        # A semantic planner normally schedules search_places
                        # before this tool. Keep the Action reliable when that
                        # optional hint omits needs_places: the calendar tool
                        # safely reuses the same Tencent/OSM adapter once,
                        # rather than failing and leaving a phantom card.
                        maps_enabled = (
                            enabled_skills is None
                            or place_skill_id in enabled_skills
                        )
                        if not maps_enabled:
                            raise ValueError(text(
                                "calendar.error.map_required", response_language,
                                place=location_text,
                            ))
                        verified = await _search_places_metered(
                            str(
                                runtime_env.get("TENCENT_MAP_SERVER_KEY")
                                or runtime_env.get("TENCENT_MAP_KEY")
                                or runtime_env.get("VITE_TENCENT_MAP_KEY")
                                or ""
                            ),
                            location_text,
                            city="全国",
                            limit=6,
                        )
                        if not verified:
                            raise ValueError(text(
                                "calendar.error.place_not_found", response_language,
                                place=location_text,
                            ))
                        for candidate in verified:
                            candidate_id = str(candidate.get("place_id") or "").strip()
                            if candidate_id:
                                candidates[candidate_id] = candidate
                        if len(verified) > 1:
                            decision, selected, _reason = await _place_resolution_with_provider_review(
                                place_disambiguation_model,
                                location_text,
                                verified,
                                context="calendar event location",
                                enabled=provider_place_review_enabled,
                                timeout_seconds=min(8.0, map_search_timeout),
                                response_language=response_language,
                            )
                            if decision == "auto_use" and isinstance(selected, dict):
                                place_id = str(selected.get("place_id") or "")
                            else:
                                return _clarification_action(
                                    conversation_id,
                                    title=text(
                                        "calendar.place_choice.title",
                                        response_language,
                                    ),
                                    prompt=text(
                                        "calendar.place_choice.prompt",
                                        response_language,
                                    ),
                                    fields=[_place_choice_field(
                                        "calendar_place",
                                        location_text,
                                        verified,
                                        response_language,
                                    )],
                                )
                        if not place_id:
                            place_id = str(verified[0].get("place_id") or "")
                if place_id:
                    place = candidates.get(place_id)
                    if not isinstance(place, dict) and location_text:
                        # Tool-calling models occasionally copy a display id
                        # incorrectly. Resolve the explicit user-visible
                        # location instead of accepting or persisting that id.
                        maps_enabled = (
                            enabled_skills is None
                            or place_skill_id in enabled_skills
                        )
                        if maps_enabled:
                            verified = await _search_places_metered(
                                str(
                                    runtime_env.get("TENCENT_MAP_SERVER_KEY")
                                    or runtime_env.get("TENCENT_MAP_KEY")
                                    or runtime_env.get("VITE_TENCENT_MAP_KEY")
                                    or ""
                                ),
                                location_text,
                                city="全国",
                                limit=6,
                            )
                            for candidate in verified:
                                candidate_id = str(candidate.get("place_id") or "").strip()
                                if candidate_id:
                                    candidates[candidate_id] = candidate
                            if len(verified) > 1:
                                decision, selected, _reason = await _place_resolution_with_provider_review(
                                    place_disambiguation_model,
                                    location_text,
                                    verified,
                                    context="calendar event location",
                                    enabled=provider_place_review_enabled,
                                    timeout_seconds=min(8.0, map_search_timeout),
                                    response_language=response_language,
                                )
                                if decision == "choose":
                                    return _clarification_action(
                                        conversation_id,
                                        title=text(
                                            "calendar.place_choice.title",
                                            response_language,
                                        ),
                                        prompt=text(
                                            "calendar.place_choice.prompt",
                                            response_language,
                                        ),
                                        fields=[_place_choice_field(
                                            "calendar_place",
                                            location_text,
                                            verified,
                                            response_language,
                                        )],
                                    )
                                if isinstance(selected, dict):
                                    place_id = str(selected.get("place_id") or "")
                                    place = selected
                            if verified and not place_id:
                                place_id = str(verified[0].get("place_id") or "")
                                place = candidates.get(place_id)
                    if not isinstance(place, dict):
                        raise ValueError(text(
                            "calendar.error.place_id", response_language,
                            place_id=place_id,
                        ))
                    normalized_event["place"] = place
                    normalized_event["location"] = place.get("address") or place.get("name")
                change["event"] = normalized_event
            normalized.append(change)
        if not normalized:
            return json.dumps({
                "ui_action": "calendar_change_report",
                "applied_count": 0,
                "proposed_count": 0,
                "skipped_changes": skipped_changes,
                "calendar_snapshot": {
                    "revision": int(state.get("revision") or 0),
                    "schedule_count": len(state.get("schedules") or {}),
                },
                "response_constraint": text(
                    "model.calendar.no_delta_constraint", response_language,
                ),
            }, ensure_ascii=False)
        if not route_source_id and isinstance(latest_route, dict):
            # If a proposal contains at least two places from a very recent
            # verified route, it is semantically a route-derived calendar
            # proposal even when the model omitted the explicit source id.
            # Enforce completeness instead of silently accepting a compressed
            # two-event version of a four-stop itinerary.
            route_age = int(time.time()) - int(latest_route.get("created_at") or 0)
            route_place_ids = {
                str(item.get("place_id") or "")
                for item in (latest_route.get("ordered_stops") or [])
                if isinstance(item, dict) and str(item.get("place_id") or "")
            }
            proposed_place_ids = {
                str(((change.get("event") or {}).get("place") or {}).get("place_id") or "")
                for change in normalized
                if change.get("operation") == "create"
            }
            if 0 <= route_age <= 10_800 and len(route_place_ids & proposed_place_ids) >= 2:
                route_source_id = str(latest_route.get("id") or "")
                linked_route = latest_route

        if route_source_id:
            if not isinstance(linked_route, dict):
                raise ValueError(text(
                    "calendar.error.route_changed", response_language,
                ))
            route_stops = [
                item for item in (linked_route.get("ordered_stops") or [])
                if isinstance(item, dict) and str(item.get("place_id") or "")
            ]
            required_stops = (
                route_stops[1:]
                if linked_route.get("implicit_browser_origin") and route_stops
                else route_stops
            )
            required_ids = [str(item.get("place_id") or "") for item in required_stops]
            created = [
                change for change in normalized if change.get("operation") == "create"
            ]
            created.sort(key=lambda change: int(
                ((change.get("event") or {}).get("start_time") or 0)
            ))
            proposed_ids = [
                str(((change.get("event") or {}).get("place") or {}).get("place_id") or "")
                for change in created
            ]
            missing_names = [
                str(
                    stop.get("name")
                    or text("calendar.unnamed_place", response_language)
                )
                for stop, place_id in zip(required_stops, required_ids)
                if place_id not in proposed_ids
            ]
            proposed_route_order = [
                place_id for place_id in proposed_ids if place_id in set(required_ids)
            ]
            if len(created) < len(required_ids) or missing_names:
                raise ValueError(text(
                    "calendar.error.route_incomplete", response_language,
                    count=len(required_ids),
                    missing=(
                        "、".join(missing_names)
                        or text("calendar.partial_stops", response_language)
                    ),
                ))
            if proposed_route_order[:len(required_ids)] != required_ids:
                raise ValueError(text(
                    "calendar.error.route_order", response_language,
                ))

        validate_calendar_change_window(state, normalized)
        warnings = calendar_change_warnings(state, normalized)
        warnings.extend(normalization_warnings)
        warnings.extend(
            f"{item['operation']}“{item['target']}”：{item['reason']}"
            for item in skipped_changes
        )
        warnings = list(dict.fromkeys(warnings))[:8]

        # Preview route feasibility before confirmation. The mutation remains
        # independent: route failure never writes or cancels the calendar
        # proposal, but users see whether travel time was verified.
        preview = copy.deepcopy(state)
        preview_changed = apply_calendar_changes(preview, normalized)
        changed_ids = {
            str(item.get("id") or "")
            for item in preview_changed
            if not item.get("deleted")
        }
        preview_schedules = sorted(
            (
                item for item in (preview.get("schedules") or {}).values()
                if (
                    isinstance(item, dict)
                    and not item.get("done")
                    and int(item.get("start_time") or 0) >= int(time.time()) - 24 * 60 * 60
                )
            ),
            key=lambda item: int(item.get("start_time") or 0),
        )[:provider_schedule_limit]
        route_pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for previous, current in zip(preview_schedules, preview_schedules[1:]):
            if (
                str(previous.get("id") or "") not in changed_ids
                and str(current.get("id") or "") not in changed_ids
            ):
                continue
            available = (
                int(current.get("start_time") or 0)
                - int(previous.get("start_time") or 0)
                - max(1, int(previous.get("duration_minutes") or 60)) * 60
            )
            if not 0 < available <= route_gap_hours * 3600:
                continue
            previous_place = (
                (previous.get("extra") or {}).get("place")
                if isinstance(previous.get("extra"), dict) else None
            )
            current_place = (
                (current.get("extra") or {}).get("place")
                if isinstance(current.get("extra"), dict) else None
            )
            if isinstance(previous_place, dict) and isinstance(current_place, dict):
                route_pairs.append((previous, current))
            if len(route_pairs) >= 3:
                break

        map_key = str(
            runtime_env.get("TENCENT_MAP_SERVER_KEY")
            or runtime_env.get("TENCENT_MAP_KEY")
            or runtime_env.get("VITE_TENCENT_MAP_KEY")
            or ""
        )

        async def preview_route_pair(
            previous: dict[str, Any], current: dict[str, Any],
        ) -> str:
            previous_place = (previous.get("extra") or {}).get("place")
            current_place = (current.get("extra") or {}).get("place")
            available = (
                int(current.get("start_time") or 0)
                - int(previous.get("start_time") or 0)
                - max(1, int(previous.get("duration_minutes") or 60)) * 60
            )
            try:
                route = await load_route_cache(
                    store, user_id, [previous_place, current_place], False,
                )
                if route is None:
                    route = await _plan_route_metered(
                        map_key, [previous_place, current_place], optimize=False,
                    )
                    await save_route_cache(
                        store, user_id, [previous_place, current_place], False, route,
                    )
                route_minutes = max(1, round(float(route.get("duration_seconds") or 0) / 60))
                required_minutes = route_minutes + travel_buffer_minutes
                available_minutes = max(0, available // 60)
                if required_minutes > available_minutes:
                    return text(
                        "calendar.warning.travel_time", response_language,
                        previous=(
                            previous.get("title")
                            or text("calendar.previous_event", response_language)
                        ),
                        current=(
                            current.get("title")
                            or text("calendar.next_event", response_language)
                        ),
                        route_minutes=route_minutes,
                        buffer=travel_buffer_minutes,
                        required=required_minutes,
                        available=available_minutes,
                    )
            except Exception:
                return text(
                    "calendar.warning.travel_unverified", response_language,
                    previous=(
                        previous.get("title")
                        or text("calendar.previous_event", response_language)
                    ),
                    current=(
                        current.get("title")
                        or text("calendar.next_event", response_language)
                    ),
                )
            return ""

        if route_pairs:
            route_warning_results = await asyncio.gather(*(
                preview_route_pair(previous, current)
                for previous, current in route_pairs
            ))
            warnings.extend(value for value in route_warning_results if value)
            warnings = list(dict.fromkeys(warnings))[:8]
        action = new_action(
            "calendar_changes",
            {
                "summary": str(
                    summary or text("calendar.summary.default", response_language)
                )[:300],
                "changes": normalized,
                "warnings": warnings,
                "skipped_changes": skipped_changes,
                "calendar_snapshot": {
                    "revision": int(state.get("revision") or 0),
                    "schedule_count": len(state.get("schedules") or {}),
                },
                **({"source_route_plan_id": route_source_id} if route_source_id else {}),
            },
            requires_confirmation=True,
        )
        put_action(state, action)
        await _save_state(state)
        return json.dumps({"ui_action": "calendar_action", "action": action}, ensure_ascii=False)

    return propose_calendar_changes
