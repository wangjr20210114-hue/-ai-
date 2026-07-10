"""Travel constraint parsing and preference weights."""
from __future__ import annotations

from agents.travel.models import TravelConstraints


def normalize_constraints(raw: dict) -> TravelConstraints:
    days = raw.get("days") or 0
    if not days and raw.get("start_date") and raw.get("end_date"):
        try:
            from datetime import datetime
            d1 = datetime.strptime(raw["start_date"], "%Y-%m-%d")
            d2 = datetime.strptime(raw["end_date"], "%Y-%m-%d")
            days = max(1, (d2 - d1).days + 1)
        except Exception:
            days = 1
    return TravelConstraints(
        destination=raw.get("destination") or raw.get("city") or "",
        departure=raw.get("departure", ""),
        start_date=raw.get("start_date", ""),
        end_date=raw.get("end_date", ""),
        days=int(days or 1),
        travel_style=raw.get("travel_style", "深度游"),
        scenery_preference=raw.get("scenery_preference", "人文景观"),
        budget=raw.get("budget", ""),
        extra_notes=raw.get("extra_notes", ""),
        must_visit=raw.get("must_visit", []) or [],
        avoid=raw.get("avoid", []) or [],
    )


def preference_weights(constraints: TravelConstraints) -> dict[str, float]:
    style = constraints.travel_style
    pref = constraints.scenery_preference
    weights = {"popularity": 0.18, "rating": 0.18, "cost": 0.12, "compact": 0.12, "tag_match": 0.22, "comfort": 0.10, "crowd_penalty": 0.08}
    if "特种兵" in style:
        weights.update({"cost": 0.18, "compact": 0.22, "tag_match": 0.20, "comfort": 0.03, "crowd_penalty": 0.05})
    elif "休闲" in style or "亲子" in style:
        weights.update({"comfort": 0.22, "crowd_penalty": 0.14, "compact": 0.08, "cost": 0.08})
    if "自然" in pref or "人文" in pref or "博物馆" in pref:
        weights["tag_match"] += 0.05
    return weights