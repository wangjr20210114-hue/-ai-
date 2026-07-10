"""Rule based enrichment for imported places."""
from __future__ import annotations

from dataclasses import replace

from agents.travel.models import IndoorOutdoor, POICategory
from agents.travel.place_db.schema import PlaceRecord


def enrich_tags(record: PlaceRecord) -> PlaceRecord:
    tags = set(record.tags)
    name_blob = " ".join([record.name, record.sub_category, record.scene_type, record.address]).lower()

    if record.ticket_price == 0 and record.category in {POICategory.SCENIC, POICategory.MUSEUM, POICategory.ACTIVITY}:
        tags.add("免费")
    if record.indoor_outdoor == IndoorOutdoor.INDOOR:
        tags.update({"室内", "雨天"})
    if record.indoor_outdoor == IndoorOutdoor.OUTDOOR:
        tags.add("户外")
    if record.rating >= 4.6:
        tags.add("高分")
    if record.review_count >= 1000 or record.popularity >= 0.8:
        tags.add("热门")
    if record.crowd_level <= 0.35:
        tags.add("小众")
    if record.queue_risk >= 0.7:
        tags.add("排队风险")
    if record.energy_cost <= 0.35:
        tags.add("低体力")
    if record.photo_score >= 0.75:
        tags.add("拍照")
    if record.family_friendly >= 0.7:
        tags.add("亲子")
    if record.elderly_friendly >= 0.7:
        tags.add("老人友好")
    if record.category == POICategory.RESTAURANT:
        tags.add("餐饮")
    if record.category == POICategory.HOTEL:
        tags.add("住宿")
    if any(word in name_blob for word in ["museum", "gallery", "博物馆", "美术馆", "展览"]):
        tags.update({"人文", "室内"})
    if record.category in {POICategory.SCENIC, POICategory.ACTIVITY} and any(word in name_blob for word in ["park", "lake", "mountain", "公园", "湖", "山"]):
        tags.update({"自然", "户外"})
    if any(word in name_blob for word in ["night", "bar", "夜", "灯光"]):
        tags.add("夜景")

    recommended_for = set(record.recommended_for)
    if "亲子" in tags:
        recommended_for.add("亲子")
    if "小众" in tags:
        recommended_for.add("小众避人")
    if "低体力" in tags or record.elderly_friendly >= 0.7:
        recommended_for.add("老人友好")
    if record.avg_cost <= 50 and record.ticket_price <= 30:
        recommended_for.add("低预算")
    if record.photo_score >= 0.75:
        recommended_for.add("摄影打卡")

    return replace(record, tags=sorted(tags), recommended_for=sorted(recommended_for))


def normalize_quality(record: PlaceRecord) -> PlaceRecord:
    popularity = record.popularity
    if popularity == 0.5 and record.review_count:
        popularity = min(1.0, 0.3 + record.review_count / 5000)

    local_score = record.local_recommend_score
    if local_score <= 0:
        local_score = min(1.0, record.rating / 5 * 0.55 + popularity * 0.35 + record.source_confidence * 0.1)

    return replace(
        record,
        popularity=max(0.0, min(1.0, popularity)),
        local_recommend_score=max(0.0, min(1.0, local_score)),
        crowd_level=max(0.0, min(1.0, record.crowd_level)),
        queue_risk=max(0.0, min(1.0, record.queue_risk)),
        energy_cost=max(0.0, min(1.0, record.energy_cost)),
        weather_sensitivity=max(0.0, min(1.0, record.weather_sensitivity)),
        source_confidence=max(0.0, min(1.0, record.source_confidence)),
    )


def clean_record(record: PlaceRecord) -> PlaceRecord | None:
    if not record.name or not record.city:
        return None
    if record.lat and not (-90 <= record.lat <= 90):
        return None
    if record.lng and not (-180 <= record.lng <= 180):
        return None
    return enrich_tags(normalize_quality(record))
