"""Recommendation feature scoring for travel places."""
from __future__ import annotations

from dataclasses import dataclass

from agents.travel.models import POICategory, TravelConstraints
from agents.travel.place_db.schema import PlaceRecord


@dataclass(slots=True)
class PlaceScore:
    record: PlaceRecord
    score: float
    reasons: list[str]


def score_record(record: PlaceRecord, constraints: TravelConstraints) -> PlaceScore:
    text = f"{constraints.travel_style} {constraints.scenery_preference} {constraints.budget} {constraints.extra_notes}"
    tags = set(record.tags) | set(record.recommended_for)
    reasons: list[str] = []

    tag_hits = [tag for tag in tags if tag and tag in text]
    tag_score = min(1.0, len(tag_hits) / 3) if tag_hits else 0.18
    if tag_hits:
        reasons.append("匹配偏好：" + "、".join(tag_hits[:3]))

    budget_score = _budget_score(record, text)
    if budget_score >= 0.8:
        reasons.append("预算匹配")

    quality = record.rating / 5 * 0.45 + record.popularity * 0.25 + record.local_recommend_score * 0.2 + record.source_confidence * 0.1
    compact = 0.72 if record.cluster_id else 0.45
    weather = 1.0 - record.weather_sensitivity
    comfort = 1.0 - record.energy_cost
    crowd = 1.0 - max(record.crowd_level, record.queue_risk * 0.8)

    weights = _weights(text)
    score = (
        quality * weights["quality"]
        + tag_score * weights["tag"]
        + budget_score * weights["budget"]
        + compact * weights["compact"]
        + weather * weights["weather"]
        + comfort * weights["comfort"]
        + crowd * weights["crowd"]
        + record.photo_score * weights["photo"]
    )
    if record.name in constraints.must_visit:
        score += 0.35
        reasons.append("用户指定必去")
    if record.name in constraints.avoid or any(tag in text for tag in record.avoid_for):
        score -= 1.0
        reasons.append("用户不感兴趣")
    if record.rating >= 4.6:
        reasons.append("口碑高")
    if record.cluster_id:
        reasons.append("周边点位密集")
    if record.category == POICategory.RESTAURANT and record.local_recommend_score >= 0.7:
        reasons.append("适合路线中插入用餐")

    return PlaceScore(record=record, score=round(score, 4), reasons=reasons[:4])


def _budget_score(record: PlaceRecord, text: str) -> float:
    cost = max(record.avg_cost, record.ticket_price)
    if any(word in text for word in ["低预算", "省钱", "便宜", "特种兵"]):
        return 1.0 - min(1.0, cost / 180)
    if any(word in text for word in ["高品质", "舒适", "品质"]):
        return min(1.0, 0.45 + record.rating / 5 * 0.45 + record.source_confidence * 0.1)
    return 1.0 - min(0.6, cost / 500)


def _weights(text: str) -> dict[str, float]:
    if "特种兵" in text:
        return {"quality": 0.22, "tag": 0.18, "budget": 0.18, "compact": 0.18, "weather": 0.05, "comfort": 0.04, "crowd": 0.1, "photo": 0.05}
    if "亲子" in text or "老人" in text:
        return {"quality": 0.2, "tag": 0.18, "budget": 0.1, "compact": 0.14, "weather": 0.14, "comfort": 0.14, "crowd": 0.08, "photo": 0.02}
    if "摄影" in text or "拍照" in text:
        return {"quality": 0.2, "tag": 0.16, "budget": 0.08, "compact": 0.12, "weather": 0.08, "comfort": 0.06, "crowd": 0.08, "photo": 0.22}
    return {"quality": 0.24, "tag": 0.16, "budget": 0.12, "compact": 0.14, "weather": 0.1, "comfort": 0.1, "crowd": 0.1, "photo": 0.04}
