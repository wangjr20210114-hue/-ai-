"""Localized, evidence-grounded fallbacks for completed chat tools."""

from __future__ import annotations

import json
from typing import Iterable

from ._protocol import action_fallback_content
from .._application.i18n import normalize_language, text
from .._application.skills.registry import skill_manifests, tool_skill_map


SKILL_DISPLAY_NAMES = {
    manifest.id: dict(manifest.names)
    for manifest in skill_manifests()
}

TOOL_CAPABILITIES = tool_skill_map()


def _hidden_clarification_answer(message) -> bool:
    """Return whether a user message only carries a structured-card answer."""
    if getattr(message, "type", "") not in {"human", "user"}:
        return False
    additional = getattr(message, "additional_kwargs", None) or {}
    return (
        isinstance(additional, dict)
        and additional.get("floris_interaction") == "clarification"
    )


def _capability_names(capability_ids: Iterable[str], response_language: str) -> str:
    language = normalize_language(response_language)
    names = []
    for capability_id in capability_ids:
        skill_id = TOOL_CAPABILITIES.get(capability_id, capability_id)
        localized = SKILL_DISPLAY_NAMES.get(skill_id, {}).get(language)
        name = localized or SKILL_DISPLAY_NAMES.get(skill_id, {}).get("zh-CN") or text(
            "chat.capability.fallback_name", language,
        )
        if name not in names:
            names.append(name)
    separator = ", " if language == "en" else "、"
    return separator.join(names) or text("chat.capability.fallback_name", language)


def blocked_capability_response(
    capability_ids: Iterable[str],
    response_language: str = "zh-CN",
    *,
    configured: bool = False,
) -> str:
    """Return one truthful terminal response after the LLM planner finds a blocked capability."""
    language = normalize_language(response_language)
    names = _capability_names(capability_ids, language)
    state_key = "unconfigured" if configured else "disabled"
    return text(
        "chat.capability.blocked", language,
        names=names,
        state=text(f"chat.capability.state.{state_key}", language),
        next_step=text(f"chat.capability.next.{state_key}", language),
    )


def _logical_turn_messages(messages: Iterable) -> list:
    """Return messages belonging to the current user goal.

    Hidden structured-card answers continue their original goal. A route can
    legitimately require several successive POI choices, so cross every hidden
    answer until the first normal user message rather than only one boundary.
    """
    logical_turn_messages: list = []
    for message in reversed(list(messages)):
        if getattr(message, "type", "") in {"human", "user"}:
            if _hidden_clarification_answer(message):
                continue
            break
        logical_turn_messages.append(message)
    return logical_turn_messages


def action_completion_fallback(
    messages: Iterable,
    response_language: object = "zh-CN",
) -> str:
    """Return prose only for an Action that was actually created this turn.

    Looking only at the called tool name is unsafe: ToolNode records a
    ToolMessage even when argument validation or a provider call failed. That
    previously let a failed calendar proposal claim that a confirmation card
    was ready although no durable Action existed.
    """
    actions: list[dict] = []
    workflow_ready = False
    for message in reversed(_logical_turn_messages(messages)):
        if getattr(message, "type", "") != "tool":
            continue
        try:
            payload = json.loads(str(getattr(message, "content", "") or ""))
        except (TypeError, json.JSONDecodeError):
            continue
        if (
            isinstance(payload, dict)
            and payload.get("ui_action") in {
                "map_action", "calendar_action", "side_effect_action",
            }
            and isinstance(payload.get("action"), dict)
        ):
            actions.append(payload)
        workflow_ready = workflow_ready or (
            isinstance(payload, dict)
            and isinstance(payload.get("workflow_proposal"), dict)
        )
    if actions:
        return action_fallback_content(actions, response_language)
    if workflow_ready:
        return text("chat.fallback.workflow_ready", response_language)
    return ""


def tool_failure_fallback(
    messages: Iterable,
    response_language: object = "zh-CN",
) -> str:
    """Expose the real validation failure if both model synthesis passes are empty."""
    for message in _logical_turn_messages(messages):
        if getattr(message, "type", "") != "tool":
            continue
        content = str(getattr(message, "content", "") or "").strip()
        try:
            payload = json.loads(content)
        except (TypeError, json.JSONDecodeError):
            continue
        failure = payload.get("tool_error") if isinstance(payload, dict) else None
        if not isinstance(failure, dict):
            continue
        detail = str(failure.get("detail") or "").strip()
        if detail:
            if getattr(message, "name", "") == "rich_search":
                return text("chat.fallback.search_failed", response_language)
            if getattr(message, "name", "") == "get_current_location":
                return text(
                    "chat.fallback.location_failed", response_language,
                    detail=detail,
                )
            if getattr(message, "name", "") == "recommend_nearby_places_on_map":
                return text(
                    "chat.fallback.nearby_failed", response_language,
                    detail=detail,
                )
            if getattr(message, "name", "") == "plan_route_between_places":
                return text(
                    "chat.fallback.route_failed", response_language,
                    detail=detail,
                )
            if failure.get("kind") == "runtime":
                return text("chat.fallback.required_failed", response_language)
            return text(
                "chat.fallback.action_failed", response_language,
                detail=detail,
            )
    return ""


def tool_result_fallback(
    messages: Iterable,
    response_language: object = "zh-CN",
) -> str:
    """Build a truthful minimal answer from successful structured tool output.

    This is used only after both the normal synthesis pass and its clean
    tool-free retry return no public prose. It prevents a completed provider
    lookup from collapsing into the generic empty-answer error.
    """
    logical_turn_messages = _logical_turn_messages(messages)

    for message in logical_turn_messages:
        if (
            getattr(message, "type", "") != "tool"
            or getattr(message, "name", "") != "propose_calendar_changes"
        ):
            continue
        try:
            payload = json.loads(str(getattr(message, "content", "") or ""))
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict) or payload.get("ui_action") != "calendar_change_report":
            continue
        skipped = payload.get("skipped_changes")
        skipped = skipped if isinstance(skipped, list) else []
        if skipped:
            lines = [
                text(
                    "chat.fallback.calendar_item", response_language,
                    operation=str(item.get("operation") or text(
                        "chat.fallback.operation", response_language,
                    )),
                    target=str(item.get("target") or text(
                        "chat.fallback.target", response_language,
                    )),
                    reason=str(item.get("reason") or text(
                        "chat.fallback.not_executed", response_language,
                    )),
                )
                for item in skipped
                if isinstance(item, dict)
            ]
            return text(
                "chat.fallback.calendar_no_delta", response_language,
                items="\n".join(lines),
            )

    for message in logical_turn_messages:
        if (
            getattr(message, "type", "") != "tool"
            or getattr(message, "name", "") != "get_current_location"
        ):
            continue
        try:
            payload = json.loads(str(getattr(message, "content", "") or ""))
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        if not payload.get("location_available"):
            return text("chat.fallback.location_missing", response_language)
        location = payload.get("location")
        if not isinstance(location, dict):
            continue
        address = str(location.get("address") or "").strip()
        locality = "".join(
            str(location.get(key) or "").strip()
            for key in ("province", "city", "district", "street", "street_number")
        )
        landmark = str(location.get("nearby_landmark") or "").strip()
        readable = address or locality
        if readable:
            suffix = text(
                "chat.fallback.location_landmark", response_language,
                landmark=landmark,
            ) if landmark else ""
            return text(
                "chat.fallback.location_resolved", response_language,
                location=readable,
                landmark=suffix,
            )

    paper_payload = None
    rich_search_payload = None
    for message in logical_turn_messages:
        if getattr(message, "type", "") != "tool":
            continue
        try:
            payload = json.loads(str(getattr(message, "content", "") or ""))
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        tool_name = getattr(message, "name", "")
        if (
            tool_name == "search_arxiv"
            and payload.get("ui_action") == "paper_results"
            and paper_payload is None
        ):
            paper_payload = payload
        elif (
            tool_name == "rich_search"
            and payload.get("ui_action") == "rich_search_results"
            and rich_search_payload is None
        ):
            rich_search_payload = payload

    paper_items = (
        paper_payload.get("papers")
        if isinstance(paper_payload, dict)
        and isinstance(paper_payload.get("papers"), list)
        else []
    )
    if paper_items:
        paper_answer = _paper_result_answer(
            paper_payload, response_language=response_language,
        )
        if paper_answer:
            return paper_answer

    # A supplementary academic lookup may legitimately return no papers after
    # a successful web search. Never let that empty secondary source replace
    # the primary result with an unrelated author/institution failure message.
    search_metadata = (
        rich_search_payload.get("search_results")
        if isinstance(rich_search_payload, dict)
        and isinstance(rich_search_payload.get("search_results"), dict)
        else {}
    )
    search_results = (
        search_metadata.get("results")
        if isinstance(search_metadata.get("results"), list)
        else []
    )
    verified_sources = [
        {
            "title": str(item.get("title") or "").strip(),
            "url": str(item.get("url") or "").strip(),
        }
        for item in search_results
        if isinstance(item, dict)
        and str(item.get("title") or "").strip()
        and str(item.get("url") or "").startswith(("https://", "http://"))
    ][:5]
    if verified_sources:
        links = "\n".join(
            f"- [{item['title']}]({item['url']})"
            for item in verified_sources
        )
        return text(
            "chat.fallback.search_sources", response_language,
            links=links,
        )

    paper_answer = _paper_result_answer(
        paper_payload, response_language=response_language,
    )
    if paper_answer:
        return paper_answer

    places: list[dict] = []
    seen: set[str] = set()
    nearby_failure = False
    for message in logical_turn_messages:
        if getattr(message, "type", "") != "tool":
            continue
        tool_name = getattr(message, "name", "")
        if tool_name not in {
            "search_places",
            "search_places_batch",
            "recommend_nearby_places_on_map",
        }:
            continue
        raw_content = str(getattr(message, "content", "") or "")
        try:
            payload = json.loads(raw_content)
        except (TypeError, json.JSONDecodeError):
            continue
        if (
            tool_name == "recommend_nearby_places_on_map"
            and isinstance(payload, dict)
            and isinstance(payload.get("tool_error"), dict)
        ):
            nearby_failure = True
            continue
        candidates = payload.get("places") if isinstance(payload, dict) else []
        if not isinstance(candidates, list):
            continue
        for place in candidates:
            if not isinstance(place, dict):
                continue
            name = str(place.get("name") or "").strip()
            address = str(place.get("address") or "").strip()
            if not name:
                continue
            identity = str(place.get("place_id") or f"{name}|{address}")
            if identity in seen:
                continue
            seen.add(identity)
            places.append({"name": name, "address": address})
        if places:
            break
    if not places and nearby_failure:
        return text("chat.fallback.no_nearby", response_language)
    if not places:
        return ""
    visible = places[:5]
    lines = [
        f"- **{place['name']}**" + (f" — {place['address']}" if place["address"] else "")
        for place in visible
    ]
    suffix = text(
        "chat.fallback.more_places", response_language,
        count=len(places) - len(visible),
    ) if len(places) > len(visible) else ""
    return text(
        "chat.fallback.places", response_language,
        items="\n".join(lines), suffix=suffix,
    )


def _paper_result_answer(
    payload: dict | None,
    *,
    cards_enabled: bool = True,
    response_language: object = "zh-CN",
) -> str:
    if not isinstance(payload, dict) or payload.get("ui_action") != "paper_results":
        return ""
    papers = payload.get("papers")
    paper_titles = [
        str(paper.get("title") or "").strip()
        for paper in (papers if isinstance(papers, list) else [])
        if isinstance(paper, dict) and str(paper.get("title") or "").strip()
    ]
    if not paper_titles:
        return text("chat.fallback.papers_empty", response_language)
    sources = {
        str(paper.get("source") or "arXiv")
        for paper in papers
        if isinstance(paper, dict)
    }
    source_copy = "、".join(sorted(sources))
    if not cards_enabled:
        lines = []
        for index, paper in enumerate(papers[:8], start=1):
            if not isinstance(paper, dict):
                continue
            title = str(paper.get("title") or "").strip()
            if not title:
                continue
            authors = str(paper.get("authors") or "").strip()
            year = int(paper.get("year") or 0)
            source_url = str(
                paper.get("source_url")
                or paper.get("arxiv_url")
                or ""
            ).strip()
            label = f"{index}. **{title}**"
            details = " · ".join(
                value for value in (
                    str(year) if year else "",
                    authors,
                ) if value
            )
            if details:
                label += f"\n   {details}"
            if source_url.startswith("https://"):
                label += (
                    f"\n   [{text('chat.fallback.view_source', response_language)}]"
                    f"({source_url})"
                )
            lines.append(label)
        return text(
            "chat.fallback.papers_plain", response_language,
            sources=source_copy,
            count=len(lines),
            items="\n\n".join(lines),
        )
    return text(
        "chat.fallback.papers_cards", response_language,
        sources=source_copy,
        count=len(paper_titles),
    )


def _route_result_answer(
    payload: dict | None,
    response_language: object = "zh-CN",
) -> str:
    """Render verified route facts without spending another model round."""
    if not isinstance(payload, dict) or payload.get("ui_action") != "map_action":
        return ""
    route = payload.get("route")
    stops = payload.get("ordered_stops")
    if not isinstance(route, dict) or not isinstance(stops, list) or len(stops) < 2:
        return ""
    valid_stops = [
        stop for stop in stops
        if isinstance(stop, dict) and str(stop.get("name") or "").strip()
    ]
    if len(valid_stops) < 2:
        return ""
    distance = route.get("distance_kilometers")
    duration = route.get("duration_minutes")
    if not isinstance(distance, (int, float)) or not isinstance(duration, (int, float)):
        return ""

    mode = str(route.get("mode") or "").strip().lower()
    mode_name = {
        name: text(f"chat.fallback.mode.{name}", response_language)
        for name in ("driving", "transit", "walking", "bicycling")
    }.get(mode, text("chat.fallback.mode.generic", response_language))
    corrections = []
    for stop in valid_stops:
        correction = stop.get("query_correction")
        if not isinstance(correction, dict):
            continue
        original = str(correction.get("original_query") or "").strip()
        corrected = str(correction.get("corrected_name") or stop.get("name") or "").strip()
        if original and corrected and original != corrected:
            corrections.append(text(
                "chat.fallback.route_correction", response_language,
                original=original, corrected=corrected,
            ))

    lines = []
    if corrections:
        lines.append(text(
            "chat.fallback.route_corrections", response_language,
            corrections="、".join(corrections),
        ))
    stop_names = " → ".join(str(stop.get("name") or "").strip() for stop in valid_stops)
    lines.append(text(
        "chat.fallback.route_summary", response_language,
        stops=stop_names, mode=mode_name, distance=f"{float(distance):g}",
        duration=max(1, round(float(duration))),
    ))

    if mode == "transit":
        transit = route.get("transit") if isinstance(route.get("transit"), dict) else {}
        transit_lines = [
            str(line).strip() for line in (transit.get("lines") or [])
            if str(line).strip()
        ]
        if transit_lines:
            lines.append(text(
                "chat.fallback.route_lines", response_language,
                lines="、".join(transit_lines[:6]),
            ))
        walking_distance = transit.get("walking_distance_meters")
        if isinstance(walking_distance, (int, float)) and walking_distance > 0:
            lines.append(text(
                "chat.fallback.route_walking", response_language,
                meters=round(float(walking_distance)),
            ))
        fare = route.get("fare") if isinstance(route.get("fare"), dict) else {}
        transit_fare = fare.get("transit") if isinstance(fare.get("transit"), dict) else {}
        estimate = transit_fare.get("estimate")
        if (
            transit_fare.get("provider_estimate")
            and isinstance(estimate, (int, float))
        ):
            lines.append(text(
                "chat.fallback.route_fare", response_language,
                fare=f"{float(estimate):g}",
            ))

    lines.append(text("chat.fallback.route_card", response_language))
    return "\n\n".join(lines)


def _route_result_with_calendar_degraded(
    payload: dict | None,
    response_language: object = "zh-CN",
) -> str:
    """Preserve a completed route when its independent calendar stage fails."""
    route_answer = _route_result_answer(payload, response_language)
    if not route_answer:
        return ""
    return text(
        "chat.fallback.route_calendar_degraded", response_language,
        route=route_answer,
    )


def _linked_trip_result_answer(
    route_payload: dict | None,
    calendar_payload: dict | None,
    response_language: object = "zh-CN",
) -> str:
    """Summarize a verified route and its one editable calendar Action."""
    if (
        not isinstance(route_payload, dict)
        or route_payload.get("ui_action") != "map_action"
        or not isinstance(calendar_payload, dict)
        or calendar_payload.get("ui_action") != "calendar_action"
    ):
        return ""
    route = route_payload.get("route")
    stops = route_payload.get("ordered_stops")
    calendar_action = calendar_payload.get("action")
    if (
        not isinstance(route, dict)
        or not isinstance(stops, list)
        or len(stops) < 2
        or not isinstance(calendar_action, dict)
    ):
        return ""
    action_payload = calendar_action.get("payload")
    changes = (
        action_payload.get("changes")
        if isinstance(action_payload, dict)
        else None
    )
    if not isinstance(changes, list) or not changes:
        return ""
    route_id = str(route_payload.get("route_plan_id") or "")
    source_route_id = (
        str(action_payload.get("source_route_plan_id") or "")
        if isinstance(action_payload, dict)
        else ""
    )
    route_link_mismatch = bool(
        route_id and source_route_id and route_id != source_route_id
    )

    correction_lines = []
    for stop in stops:
        correction = stop.get("query_correction") if isinstance(stop, dict) else None
        if not isinstance(correction, dict):
            continue
        original = str(correction.get("original_query") or "").strip()
        corrected = str(correction.get("corrected_name") or "").strip()
        if original and corrected and original != corrected:
            correction_lines.append(text(
                "chat.fallback.route_correction", response_language,
                original=original, corrected=corrected,
            ))

    names = [
        str(stop.get("name") or "").strip()
        for stop in stops
        if isinstance(stop, dict) and str(stop.get("name") or "").strip()
    ]
    distance = route.get("distance_kilometers")
    duration = route.get("duration_minutes")
    mode_name = {
        name: text(f"chat.fallback.mode.{name}", response_language)
        for name in ("driving", "transit", "walking", "bicycling")
    }.get(
        str(route.get("mode") or "").lower(),
        text("chat.fallback.mode.generic", response_language),
    )
    lines = []
    if correction_lines:
        lines.append(text(
            "chat.fallback.route_corrections", response_language,
            corrections="、".join(correction_lines),
        ))
    if (
        names
        and isinstance(distance, (int, float))
        and isinstance(duration, (int, float))
    ):
        lines.append(text(
            "chat.fallback.linked_route", response_language,
            count=len(names), stops=" → ".join(names), mode=mode_name,
            distance=f"{float(distance):g}",
            duration=max(1, round(float(duration))),
        ))
    else:
        lines.append(text(
            "chat.fallback.linked_route_without_metrics", response_language,
            count=len(names),
        ))
    warning_count = len(
        action_payload.get("warnings") or []
    ) if isinstance(action_payload, dict) else 0
    warning_text = (
        text(
            "chat.fallback.calendar_warnings", response_language,
            count=warning_count,
        )
        if warning_count
        else ""
    )
    lines.append(text(
        "chat.fallback.calendar_proposal", response_language,
        count=len(changes), warnings=warning_text,
    ))
    if route_link_mismatch:
        lines.append(text("chat.fallback.route_link_mismatch", response_language))
    lines.append(text("chat.fallback.route_calendar_independent", response_language))
    return "\n\n".join(lines)


def grounded_route_action_answer(
    actions: list[dict],
    response_language: object = "zh-CN",
) -> str:
    """Render the last verified route, optionally with its real calendar card.

    This pure output-boundary helper is shared by the graph and the SSE
    adapter. The graph normally finalizes structured route turns itself; the
    adapter remains the final guard if a runtime still streams a later model
    answer after the structured Actions have completed.
    """
    route_payload = next((
        item
        for item in reversed(actions)
        if isinstance(item, dict)
        and item.get("ui_action") == "map_action"
        and isinstance(item.get("route"), dict)
    ), None)
    calendar_payload = next((
        item
        for item in reversed(actions)
        if isinstance(item, dict)
        and item.get("ui_action") == "calendar_action"
        and isinstance(item.get("action"), dict)
    ), None)
    if route_payload is None:
        return ""
    if calendar_payload is not None:
        linked_answer = _linked_trip_result_answer(
            route_payload,
            calendar_payload,
            response_language,
        )
        if linked_answer:
            return linked_answer
    return _route_result_answer(route_payload, response_language)


def grounded_route_stream_answer(
    actions: list[dict],
    *,
    calendar_required: bool,
    clarification_emitted: bool,
    run_error: str,
    response_language: object = "zh-CN",
) -> str:
    """Apply the completion rules before replacing buffered route prose."""
    if clarification_emitted or str(run_error or "").strip():
        return ""
    calendar_payload = next((
        action
        for action in reversed(actions)
        if isinstance(action, dict)
        and action.get("ui_action") == "calendar_action"
        and isinstance(action.get("action"), dict)
    ), None)
    if calendar_required:
        if calendar_payload is None:
            return ""
        route_answer = grounded_route_action_answer(actions, response_language)
        if route_answer:
            return route_answer
        payload = calendar_payload["action"].get("payload") or {}
        changes = payload.get("changes") or []
        if not isinstance(changes, list) or not changes:
            return ""
        warning_count = len(payload.get("warnings") or [])
        warning_text = (
            text(
                "chat.fallback.calendar_warnings", response_language,
                count=warning_count,
            )
            if warning_count
            else ""
        )
        # A route-calendar continuation may contain only the newly prepared
        # calendar Action in this turn. Keep its structured card authoritative
        # instead of letting prose recalculate and contradict frozen times.
        return text(
            "chat.fallback.calendar_proposal", response_language,
            count=len(changes), warnings=warning_text,
        )
    return grounded_route_action_answer(actions, response_language)
