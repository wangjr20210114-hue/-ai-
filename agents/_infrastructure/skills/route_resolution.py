"""Deterministic route and place-resolution helpers for trusted map components."""

from __future__ import annotations

import copy
import asyncio
import hashlib
import json
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

from pydantic import BaseModel

from ..._application.i18n import normalize_language, text
from ..._application.skills.tool_contracts import ProviderPlaceDecision


def preserve_planned_route_stops(
    model_stops: list[tuple[str, str]],
    planned_stops: list[dict[str, str]] | None,
    _user_message: str = "",
) -> list[tuple[str, str]]:
    """Keep the capability planner's ordered, user-authored stop handoff.

    The semantic capability model sees the original goal and records the exact
    ordered list. That structured handoff wins wholesale; Tencent remains the
    only component allowed to resolve aliases and corrections. No phrase or
    fuzzy-matching rule rewrites the user's place names.
    """
    normalized_plan = [
        (
            str(item.get("query") or "").strip(),
            str(item.get("near_query") or "").strip(),
        )
        for item in (planned_stops or [])
        if isinstance(item, dict) and str(item.get("query") or "").strip()
    ][:12]
    if normalized_plan:
        return normalized_plan
    return [
        (str(query or "").strip(), str(near_query or "").strip())
        for query, near_query in model_stops
        if str(query or "").strip()
    ]


def _parse_datetime(value: str) -> datetime:
    normalized = str(value or "").strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone(timedelta(hours=8)))
    return parsed


def _message_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(str(block.get("text", "")) for block in content if isinstance(block, dict))
    return str(content or "")


def _clarification_action(
    conversation_id: str,
    *,
    title: str,
    prompt: str,
    fields: list[dict[str, Any]],
) -> str:
    prompt_id = hashlib.sha256(
        f"{conversation_id}:{time.time_ns()}:{title}".encode()
    ).hexdigest()[:16]
    return json.dumps({
        "ui_action": "clarification_action",
        "clarification": {
            "id": f"clarify-{prompt_id}",
            "title": str(title).strip()[:120],
            "prompt": str(prompt).strip()[:300],
            "fields": fields[:12],
        },
    }, ensure_ascii=False)


def _merge_clarification_actions(
    conversation_id: str,
    clarifications: list[str],
    *,
    title: str = "",
    response_language: object = "zh-CN",
) -> str:
    """Merge independently discovered blockers into one resumable card group.

    Place resolution is intentionally parallel. Returning the first ambiguous
    stop discarded the other completed lookups and forced the user through one
    interruption per stop. This adapter keeps every provider-backed field and
    lets the frontend submit the complete answer set in one protocol message.
    """
    response_language = normalize_language(response_language)
    fields: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    source_titles: list[str] = []
    source_prompts: list[str] = []
    for clarification in clarifications:
        try:
            payload = json.loads(str(clarification or ""))
        except (TypeError, ValueError):
            continue
        card = payload.get("clarification") if isinstance(payload, dict) else None
        if not isinstance(card, dict):
            continue
        card_title = str(card.get("title") or "").strip()
        card_prompt = str(card.get("prompt") or "").strip()
        if card_title and card_title not in source_titles:
            source_titles.append(card_title)
        if card_prompt and card_prompt not in source_prompts:
            source_prompts.append(card_prompt)
        for raw in card.get("fields") or []:
            if not isinstance(raw, dict):
                continue
            field_id = str(raw.get("id") or "").strip()
            if not field_id or field_id in seen_ids:
                continue
            seen_ids.add(field_id)
            fields.append(copy.deepcopy(raw))
            if len(fields) >= 12:
                break
        if len(fields) >= 12:
            break
    if not fields:
        raise ValueError(text("place.merge.failed", response_language))
    count = len(fields)
    if count == 1:
        return _clarification_action(
            conversation_id,
            title=(
                source_titles[0]
                if source_titles
                else text("place.merge.single_title", response_language)
            ),
            prompt=(
                source_prompts[0]
                if source_prompts
                else text("place.merge.single_prompt", response_language)
            ),
            fields=fields,
        )
    evidence = " ".join(source_prompts)[:190]
    return _clarification_action(
        conversation_id,
        title=title or text("place.merge.title", response_language),
        prompt=text(
            "place.merge.prompt", response_language,
            count=count, evidence=f" {evidence}" if evidence else "",
        ),
        fields=fields,
    )


def _normalized_place_name(value: Any) -> str:
    return "".join(re.findall(r"[\w\u4e00-\u9fff]+", str(value or "").lower()))


def _provider_city_name(place: dict[str, Any]) -> str:
    return _normalized_place_name(place.get("city"))


def _prioritize_provider_candidates_for_city(
    places: list[dict[str, Any]],
    city: str,
) -> list[dict[str, Any]]:
    """Keep provider ranking, but move candidates from the proven city first."""
    clean_city = _normalized_place_name(city)
    if not clean_city or clean_city in {"全国", "中国"}:
        return places

    def is_same_city(place: dict[str, Any]) -> bool:
        place_city = _provider_city_name(place)
        return bool(
            place_city
            and (clean_city in place_city or place_city in clean_city)
        )

    same_city = [place for place in places if is_same_city(place)]
    if not same_city:
        return places
    return [
        *same_city,
        *(place for place in places if not is_same_city(place)),
    ]


def _scope_provider_candidates_for_city(
    places: list[dict[str, Any]],
    city: str,
) -> list[dict[str, Any]]:
    """Keep candidates inside a proven city when the provider confirms some."""
    ranked = _prioritize_provider_candidates_for_city(places, city)
    clean_city = _normalized_place_name(city)
    if not clean_city or clean_city in {"全国", "中国"}:
        return ranked
    same_city = [
        place for place in ranked
        if (
            (place_city := _provider_city_name(place))
            and (clean_city in place_city or place_city in clean_city)
        )
    ]
    return same_city or ranked


def _provider_city_consensus(
    places: list[dict[str, Any]],
) -> str:
    """Return a city only when all resolved provider stops agree."""
    cities = [
        city
        for place in places
        if isinstance(place, dict)
        if (city := _provider_city_name(place))
    ]
    return cities[0] if cities and len(set(cities)) == 1 else ""


def _prioritize_clarification_options_for_city(
    clarification: str,
    candidates: dict[str, Any],
    city: str,
    response_language: object = "zh-CN",
) -> str:
    """Reorder provider-backed card options without another model/provider call."""
    clean_city = _normalized_place_name(city)
    if not clean_city:
        return clarification
    try:
        card = json.loads(clarification)
    except (TypeError, ValueError):
        return clarification
    fields = (
        card.get("clarification", {}).get("fields", [])
        if isinstance(card, dict)
        else []
    )
    option_cities = {
        _place_choice_option(candidate, response_language): _provider_city_name(candidate)
        for candidate in candidates.values()
        if isinstance(candidate, dict)
    }
    changed = False
    for field in fields:
        if not isinstance(field, dict) or field.get("type") != "single":
            continue
        options = field.get("options")
        if not isinstance(options, list):
            continue
        prioritized = sorted(
            (str(option) for option in options),
            key=lambda option: (
                0
                if (
                    option_cities.get(option)
                    and (
                        clean_city in option_cities[option]
                        or option_cities[option] in clean_city
                    )
                )
                else 1
            ),
        )
        if prioritized != options:
            field["options"] = prioritized
            changed = True
    return (
        json.dumps(card, ensure_ascii=False)
        if changed
        else clarification
    )


def _verified_candidate_matches(
    query: str,
    place: dict[str, Any],
    city: str,
) -> bool:
    """Reject provider fallbacks that do not match the requested POI or city."""
    clean_query = _normalized_place_name(query)
    clean_name = _normalized_place_name(place.get("name"))
    if not clean_query or not clean_name:
        return False
    correction = place.get("query_correction")
    correction_query = (
        _normalized_place_name(correction.get("original_query"))
        if isinstance(correction, dict)
        else ""
    )
    correction_evidence = (
        str(correction.get("evidence") or "")
        if isinstance(correction, dict)
        else ""
    )
    verified_correction = bool(
        correction_query == clean_query
        and correction_evidence.startswith("tencent_")
    )
    if not (
        clean_query == clean_name
        or verified_correction
    ):
        return False
    clean_city = _normalized_place_name(city)
    if not clean_city or clean_city in {"全国", "中国"}:
        return True
    locality = _normalized_place_name(
        f"{place.get('city') or ''}{place.get('address') or ''}"
    )
    return clean_city in locality


_PLACE_CHOICE_VALUE_PREFIX = "floris-place:"


def _place_choice_value(place: dict[str, Any]) -> str:
    """Return the opaque wire value for an already verified place candidate."""
    place_id = str(place.get("place_id") or "").strip()
    return (
        f"{_PLACE_CHOICE_VALUE_PREFIX}{place_id}"[:240]
        if place_id
        else _place_choice_option(place)
    )


def _selected_place_candidate(
    value: Any,
    candidates: dict[str, Any],
) -> dict[str, Any] | None:
    """Resolve a card answer by stable provider identity without searching again."""
    clean_value = str(value or "").strip()
    if not clean_value.startswith(_PLACE_CHOICE_VALUE_PREFIX):
        return None
    place_id = clean_value[len(_PLACE_CHOICE_VALUE_PREFIX):].strip()
    candidate = candidates.get(place_id)
    if (
        not place_id
        or not isinstance(candidate, dict)
        or str(candidate.get("place_id") or "").strip() != place_id
    ):
        return None
    return copy.deepcopy(candidate)


def _rank_verified_workspace_matches(
    query: str,
    candidates: dict[str, Any],
    city: str,
    *,
    limit: int = 6,
) -> list[dict[str, Any]]:
    """Reuse only an explicit prior choice.

    A bare canonical name may still have multiple real branches. Reusing one
    workspace record by name—or a prior unconfirmed correction—would silently
    collapse that ambiguity across conversations. New cards submit an opaque
    provider-backed value; exact legacy option labels remain compatible. Every
    other name goes through the provider search/cache again.
    """
    selected = _selected_place_candidate(query, candidates)
    if selected is not None:
        return [selected]
    clean_query = _normalized_place_name(query)
    ranked: list[tuple[int, str, dict[str, Any]]] = []
    for place_id, raw_place in candidates.items():
        if not isinstance(raw_place, dict) or not str(raw_place.get("place_id") or place_id):
            continue
        clean_option = _normalized_place_name(_place_option_label(raw_place))
        clean_choice_option = _normalized_place_name(
            _place_choice_option(raw_place)
        )
        if clean_query not in {clean_option, clean_choice_option}:
            continue
        exact_rank = (
            0 if clean_query == clean_choice_option
            else 1
        )
        current_place = copy.deepcopy(raw_place)
        ranked.append((
            exact_rank,
            str(place_id),
            current_place,
        ))
    ranked.sort(key=lambda item: (item[0], item[1]))
    return [item[2] for item in ranked[:max(1, min(12, int(limit or 6)))]]


def _place_choice_field(
    field_id: str,
    label: str,
    places: list[dict[str, Any]],
    response_language: object = "zh-CN",
) -> dict[str, Any]:
    response_language = normalize_language(response_language)
    options: list[str] = []
    option_values: dict[str, str] = {}
    for place in places[:6]:
        base_option = _place_choice_option(place, response_language)
        option = base_option
        duplicate_index = 2
        while option in option_values:
            suffix = text(
                "place.choice.duplicate", response_language,
                index=duplicate_index,
            )
            option = f"{base_option[:max(1, 240 - len(suffix))]}{suffix}"
            duplicate_index += 1
        options.append(option)
        option_values[option] = _place_choice_value(place)
    return {
        "id": field_id,
        "label": label,
        "type": "single",
        "required": True,
        "options": options,
        "option_values": option_values,
        "allow_custom_input": True,
        "custom_placeholder": text(
            "place.choice.custom_placeholder",
            response_language,
        ),
    }


def _place_choice_option(
    place: dict[str, Any],
    response_language: object = "zh-CN",
) -> str:
    distance = place.get("distance_to_anchor_meters")
    distance_text = (
        text(
            "place.choice.distance", response_language,
            meters=max(1, round(float(distance))),
        )
        if isinstance(distance, (int, float))
        else ""
    )
    return (
        f"{place.get('name') or text('place.unnamed', response_language)}｜"
        f"{place.get('address') or text('place.address_missing', response_language)}{distance_text}"
    )[:240]


def _place_option_label(
    place: dict[str, Any],
    response_language: object = "zh-CN",
) -> str:
    return (
        f"{place.get('name') or text('place.unnamed', response_language)}｜"
        f"{place.get('address') or text('place.address_missing', response_language)}"
    )[:240]


def _place_resolution(
    query: str,
    places: list[dict[str, Any]],
) -> tuple[str, dict[str, Any] | None, str]:
    """Return the deterministic three-level decision for a side-effect place.

    A single provider candidate is safe to use. Multiple records carrying
    Tencent's native suggestion evidence are eligible for the caller's bounded
    semantic review; other multi-candidate cases remain a finite user choice,
    and no candidates require free text.
    """
    if len(places) == 1:
        correction = places[0].get("query_correction")
        return (
            "auto_use",
            places[0],
            "unique_verified_correction"
            if isinstance(correction, dict)
            else "unique_verified_candidate",
        )
    clean_query = _normalized_place_name(query)
    if clean_query:
        corrections = [
            place for place in places
            if (
                isinstance(place.get("query_correction"), dict)
                and _normalized_place_name(
                    place["query_correction"].get("original_query")
                ) == clean_query
                and str(place["query_correction"].get("evidence") or "")
                == "tencent_place_suggestion"
            )
        ]
        if places and len(corrections) == len(places):
            return (
                "auto_use",
                places[0],
                "tencent_provider_ranked_correction",
            )
    if places:
        return "choose", None, "multiple_verified_candidates"
    return "fill", None, "no_verified_candidate"


async def _place_resolution_with_provider_review(
    model,
    query: str,
    places: list[dict[str, Any]],
    *,
    context: str = "",
    enabled: bool = True,
    timeout_seconds: float = 8.0,
    response_language: object = "zh-CN",
) -> tuple[str, dict[str, Any] | None, str]:
    """Review only ambiguous Tencent suggestion sets with a fast model.

    Provider lookup remains authoritative. The model can select only one
    supplied place id and cannot invent or rewrite a POI. A failed or
    non-unique review falls back to the provider candidate card.
    """
    decision, selected, reason = _place_resolution(query, places)
    if (
        not enabled
        or model is None
        or decision not in {"auto_use", "choose"}
        or len(places) < 2
    ):
        return decision, selected, reason

    evidence = [
        {
            "provider_rank": index,
            "place_id": str(place.get("place_id") or ""),
            "name": str(place.get("name") or "")[:160],
            "address": str(place.get("address") or "")[:240],
            "city": str(place.get("city") or "")[:80],
            "category": str(place.get("category") or "")[:120],
            "latitude": place.get("latitude"),
            "longitude": place.get("longitude"),
        }
        for index, place in enumerate(places[:8], 1)
        if isinstance(place, dict) and str(place.get("place_id") or "")
    ]
    if len(evidence) < 2:
        return decision, selected, reason

    prompt = text("model.place.provider_review", response_language)
    payload = json.dumps({
        "context": str(context or "place")[:120],
        "user_query": str(query or "")[:160],
        "tencent_candidates": evidence,
    }, ensure_ascii=False, default=str)[:8_000]
    started_at = time.monotonic()
    try:
        reviewer = model.with_structured_output(
            ProviderPlaceDecision,
            method="function_calling",
            include_raw=True,
        )
        response = await asyncio.wait_for(
            reviewer.ainvoke([
                {"role": "system", "content": prompt},
                {"role": "user", "content": payload},
            ]),
            timeout=max(1.0, min(10.0, float(timeout_seconds))),
        )
        parsed = response.get("parsed") if isinstance(response, dict) else response
        if isinstance(parsed, BaseModel):
            parsed = parsed.model_dump()
        selected_id = (
            str(parsed.get("selected_place_id") or "").strip()
            if isinstance(parsed, dict) and parsed.get("unique_intent")
            else ""
        )
        reviewed = next(
            (
                place for place in places
                if str(place.get("place_id") or "") == selected_id
            ),
            None,
        )
        logging.info(
            "provider place review unique=%s candidates=%s elapsed_ms=%s",
            bool(reviewed),
            len(evidence),
            round((time.monotonic() - started_at) * 1000),
        )
        if isinstance(reviewed, dict):
            return "auto_use", reviewed, "fast_semantic_provider_review"
    except Exception as exc:
        logging.warning(
            "provider place review unavailable error_type=%s candidates=%s elapsed_ms=%s",
            type(exc).__name__,
            len(evidence),
            round((time.monotonic() - started_at) * 1000),
        )
    return "choose", None, "provider_review_requires_choice"


def _learned_route_preference(
    learning: dict[str, Any],
    key: str,
    allowed: set[str],
) -> str:
    counts = learning.get(key) if isinstance(learning, dict) else None
    if not isinstance(counts, dict):
        return ""
    ranked = sorted(
        (
            (str(value), max(0, int(count)))
            for value, count in counts.items()
            if str(value) in allowed
        ),
        key=lambda item: (-item[1], item[0]),
    )
    total = sum(count for _value, count in ranked)
    if not ranked or total < 3 or ranked[0][1] / total < 0.6:
        return ""
    return ranked[0][0]


def _route_plan_leg_summary(leg: Any, fallback_mode: str) -> dict[str, Any]:
    """Keep the provider's per-stop transport composition in durable context.

    A route leg is the journey between two recommended places.  Tencent may
    describe that one leg as several sections (for example walk -> bus ->
    subway -> walk).  The full geometry is fetched again by ``/routes`` when a
    map is opened, so the workspace stores only the bounded, model-safe facts
    needed by calendar continuation and a later map action.
    """
    if not isinstance(leg, dict):
        return {"mode": fallback_mode, "sections": []}
    summary: dict[str, Any] = {
        "mode": str(leg.get("mode") or fallback_mode),
        "scope": str(leg.get("scope") or "unknown"),
        "distance_meters": round(float(leg.get("distance_meters") or 0)),
        "duration_seconds": round(float(leg.get("duration_seconds") or 0)),
    }
    sections: list[dict[str, Any]] = []
    for section in (leg.get("sections") or [])[:8]:
        if not isinstance(section, dict):
            continue
        item: dict[str, Any] = {
            "mode": str(section.get("mode") or summary["mode"]),
            "distance_meters": round(float(section.get("distance_meters") or 0)),
            "duration_seconds": round(float(section.get("duration_seconds") or 0)),
        }
        for key in ("line", "vehicle", "geton", "getoff", "station_count", "instruction"):
            value = section.get(key)
            if value not in (None, ""):
                item[key] = str(value)[:240] if key != "station_count" else max(0, int(value or 0))
        sections.append(item)
    if sections:
        summary["sections"] = sections
    for key in ("fare", "transit"):
        value = leg.get(key)
        if isinstance(value, dict):
            summary[key] = copy.deepcopy(value)
    return summary


async def verify_place_queries_parallel(
    provider: Callable[..., Awaitable[list[dict[str, Any]]]],
    map_key: str,
    queries: list[str],
    *,
    city: str = "全国",
    timeout_seconds: float = 10.0,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    """Verify independent model-selected places concurrently, preserving query order."""
    timeout = max(3.0, min(15.0, float(timeout_seconds)))

    async def verify(query: str) -> tuple[str, list[dict[str, Any]]]:
        try:
            matches = await asyncio.wait_for(
                provider(map_key, query, city=city or "全国", limit=3),
                timeout=timeout,
            )
        except Exception:
            matches = []
        return query, matches

    results = await asyncio.gather(*(verify(query) for query in queries))
    selected: list[dict[str, Any]] = []
    all_candidates: list[dict[str, Any]] = []
    missing: list[str] = []
    for query, matches in results:
        verified_matches = [
            place for place in matches
            if isinstance(place, dict)
            and _verified_candidate_matches(query, place, city)
        ]
        if verified_matches:
            selected.append(verified_matches[0])
            all_candidates.extend(verified_matches)
        else:
            missing.append(query)
    return selected, all_candidates, missing


__all__ = (
    "preserve_planned_route_stops",
    "_parse_datetime",
    "_message_text",
    "_clarification_action",
    "_merge_clarification_actions",
    "_normalized_place_name",
    "_provider_city_name",
    "_prioritize_provider_candidates_for_city",
    "_scope_provider_candidates_for_city",
    "_provider_city_consensus",
    "_prioritize_clarification_options_for_city",
    "_verified_candidate_matches",
    "_place_choice_value",
    "_selected_place_candidate",
    "_rank_verified_workspace_matches",
    "_place_choice_field",
    "_place_choice_option",
    "_place_option_label",
    "_place_resolution",
    "_place_resolution_with_provider_review",
    "_learned_route_preference",
    "_route_plan_leg_summary",
    "verify_place_queries_parallel",
)
