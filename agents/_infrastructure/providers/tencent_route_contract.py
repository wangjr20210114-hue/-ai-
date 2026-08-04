"""Normalize Tencent route snapshots for every Floris client."""

from __future__ import annotations

import copy
from typing import Any


def route_section_mode(value: Any, fallback: str) -> str:
    normalized = str(value or "").strip().upper()
    if normalized == "WALKING":
        return "walking"
    if normalized in {"BICYCLING", "BICYCLE", "BIKE"}:
        return "bicycling"
    if normalized in {"RAIL", "SUBWAY", "METRO", "TRAIN"}:
        return "rail"
    if normalized in {"BUS", "COACH"}:
        return "bus"
    if normalized in {"DRIVING", "CAR", "TAXI"}:
        return "driving"
    if normalized in {"TRANSIT", "PUBLIC_TRANSPORT"}:
        return "transit"
    return fallback


def route_leg_scope(
    origin: dict[str, Any], destination: dict[str, Any],
) -> str:
    """Classify one leg exclusively from provider-returned city metadata."""
    origin_city = str(origin.get("city") or "").strip().casefold()
    destination_city = str(destination.get("city") or "").strip().casefold()
    if not origin_city or not destination_city:
        return "unknown"
    return "local" if origin_city == destination_city else "intercity"


def append_unique(values: list[str], value: Any) -> None:
    normalized = str(value or "").strip().lower()
    if normalized and normalized not in values:
        values.append(normalized)


def _transit_modes(payload: dict[str, Any]) -> list[str]:
    """Derive transport modes only from provider-backed route structure."""
    modes: list[str] = []
    transit = payload.get("transit")
    if not isinstance(transit, dict):
        transit = {}
    raw_modes = transit.get("modes")
    if isinstance(raw_modes, list):
        for mode in raw_modes:
            append_unique(modes, mode)
    for section in payload.get("sections") or []:
        if isinstance(section, dict):
            append_unique(modes, section.get("mode"))
    for segment in transit.get("segments") or []:
        if isinstance(segment, dict):
            append_unique(
                modes,
                route_section_mode(segment.get("vehicle"), "transit"),
            )
    try:
        walking_distance = float(transit.get("walking_distance_meters") or 0)
    except (TypeError, ValueError):
        walking_distance = 0
    if walking_distance > 0:
        append_unique(modes, "walking")
    return modes


def _enrich_route_place(
    place: dict[str, Any], references: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    enriched = copy.deepcopy(place)
    reference = references.get(str(place.get("place_id") or "")) or {}
    for field in ("name", "address", "city", "category"):
        if not enriched.get(field) and reference.get(field):
            enriched[field] = copy.deepcopy(reference[field])
    return enriched


def normalize_route_contract(
    route: dict[str, Any],
    reference_places: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Upgrade current or cached routes to the cross-client component API."""
    normalized = copy.deepcopy(route)
    references = {
        str(place.get("place_id") or ""): place
        for place in (reference_places or [])
        if isinstance(place, dict) and str(place.get("place_id") or "")
    }
    places = [
        place for place in (normalized.get("places") or [])
        if isinstance(place, dict)
    ]
    places = [_enrich_route_place(place, references) for place in places]
    if not places and references:
        places = [
            copy.deepcopy(place) for place in (reference_places or [])
            if isinstance(place, dict)
        ]
    normalized["places"] = places
    legs = [
        leg for leg in (normalized.get("legs") or [])
        if isinstance(leg, dict)
    ]
    for index, leg in enumerate(legs):
        origin = leg.get("from") if isinstance(leg.get("from"), dict) else {}
        destination = leg.get("to") if isinstance(leg.get("to"), dict) else {}
        if not origin and index < len(places):
            origin = places[index]
        if not destination and index + 1 < len(places):
            destination = places[index + 1]
        origin = _enrich_route_place(origin, references)
        destination = _enrich_route_place(destination, references)
        leg["from"] = origin
        leg["to"] = destination
        current_scope = str(leg.get("scope") or "")
        if current_scope not in {"intercity", "local"}:
            # ``unknown`` is a recoverable legacy value, not an immutable
            # decision. Promote it when newer Provider metadata is available.
            leg["scope"] = route_leg_scope(origin, destination)
        if str(leg.get("mode") or normalized.get("mode") or "") == "transit":
            leg_transit = leg.setdefault("transit", {})
            if isinstance(leg_transit, dict):
                leg_transit.pop("coverage", None)
                modes = _transit_modes(leg)
                if modes:
                    leg_transit["modes"] = modes
    normalized["legs"] = legs
    if str(normalized.get("mode") or "") == "transit":
        transit = normalized.setdefault("transit", {})
        if isinstance(transit, dict):
            transit.pop("coverage", None)
            modes = _transit_modes(normalized)
            for leg in legs:
                for mode in _transit_modes(leg):
                    append_unique(modes, mode)
            if modes:
                transit["modes"] = modes
    return normalized
