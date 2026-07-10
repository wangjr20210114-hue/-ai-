"""Multi-objective POI scoring."""
from __future__ import annotations

from agents.travel.constraints import preference_weights
from agents.travel.models import POI, ScoredPOI, TravelConstraints


def _norm(value: float, max_value: float = 1.0) -> float:
    if max_value <= 0:
        return 0.0
    return max(0.0, min(1.0, value / max_value))


def score_poi(poi: POI, constraints: TravelConstraints) -> ScoredPOI:
    weights = preference_weights(constraints)
    reasons: list[str] = []
    pref_text = f"{constraints.travel_style} {constraints.scenery_preference} {constraints.budget} {constraints.extra_notes}"
    tag_space = set(poi.tags) | set(poi.recommended_for)
    tag_hits = [t for t in tag_space if t and t in pref_text]
    tag_score = min(1.0, len(tag_hits) / 2) if tag_hits else 0.2
    if tag_hits:
        reasons.append("匹配偏好：" + "、".join(tag_hits[:3]))

    popularity = max(poi.popularity, min(1.0, poi.review_count / 5000) if poi.review_count else 0)
    rating = _norm(poi.rating, 5.0)
    local_quality = poi.local_recommend_score or (rating * 0.6 + popularity * 0.4)
    cost_score = 1.0 - min(1.0, poi.total_cost / (160.0 if "特种兵" in pref_text or "省钱" in pref_text else 260.0))
    comfort = 1.0 - (poi.energy_cost * 0.5 + poi.weather_sensitivity * 0.2 + poi.queue_risk * 0.2)
    crowd_penalty = max(poi.crowd_level, poi.queue_risk * 0.8)
    compact = 0.75 if poi.cluster_id or poi.nearby_poi_ids or poi.nearby_area else 0.45
    photo = poi.photo_score if ("拍照" in pref_text or "摄影" in pref_text) else 0.0

    if "免费" in poi.tags or poi.ticket_price == 0:
        reasons.append("成本友好")
    if "室内" in poi.tags or poi.indoor_outdoor.value == "indoor":
        reasons.append("天气风险低")
    if poi.rating >= 4.6:
        reasons.append("口碑高")
    if poi.cluster_id:
        reasons.append("周边点位密集")

    score = (
        popularity * weights["popularity"]
        + rating * weights["rating"]
        + cost_score * weights["cost"]
        + compact * weights["compact"]
        + tag_score * weights["tag_match"]
        + comfort * weights["comfort"]
        + local_quality * 0.12
        + photo * 0.08
        - crowd_penalty * weights["crowd_penalty"]
    )
    if poi.name in constraints.must_visit:
        score += 0.3
        reasons.append("用户指定必去")
    if poi.name in constraints.avoid:
        score -= 1.0
        reasons.append("用户不感兴趣")
    return ScoredPOI(poi=poi, score=round(score, 4), reasons=reasons[:4])
