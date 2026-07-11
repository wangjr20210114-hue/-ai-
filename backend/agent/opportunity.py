"""Deterministic opportunity detection for proactive signals."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Opportunity:
    intent: str
    title: str
    body: str
    reason: str
    source_label: str
    priority: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


class OpportunityDetector:
    """Converts normalized events into user-facing opportunities.

    Detection is intentionally deterministic. LLMs may enrich wording later, but
    they cannot decide whether a notification is allowed or bypass dedup/policy.
    """

    def detect(self, event: dict[str, Any]) -> Opportunity | None:
        payload = dict(event.get("payload") or {})
        event_type = str(event.get("type") or "")
        if event_type in {"schedule.due", "schedule.upcoming"}:
            title = str(payload.get("title") or "即将开始的日程")
            minutes = int(payload.get("minutes_until") or 0)
            location = str(payload.get("location") or "")
            body = f"{title}将在约 {max(0, minutes)} 分钟后开始。"
            if location:
                body += f" 地点：{location}。"
            return Opportunity(
                intent="schedule_reminder",
                title=f"日程提醒：{title}",
                body=body,
                reason="schedule_starting_soon",
                source_label="日程",
                priority=60,
                metadata=payload,
            )
        if event_type == "schedule.overdue":
            title = str(payload.get("title") or "未完成日程")
            minutes = int(payload.get("minutes_overdue") or 0)
            return Opportunity(
                intent="schedule_overdue",
                title=f"日程已逾期：{title}",
                body=f"{title} 已超过开始时间约 {minutes} 分钟，是否需要标记完成或重新安排？",
                reason="schedule_start_time_passed",
                source_label="日程",
                priority=50,
                metadata=payload,
            )
        if event_type == "schedule.conflict":
            left = dict(payload.get("left") or {})
            right = dict(payload.get("right") or {})
            return Opportunity(
                intent="schedule_conflict",
                title="发现日程冲突",
                body=f"{left.get('title') or '日程一'} 与 {right.get('title') or '日程二'} 的时间重叠，请检查安排。",
                reason="schedule_time_overlap",
                source_label="日程",
                priority=80,
                metadata=payload,
            )
        if event_type == "file.uploaded":
            name = str(payload.get("original_name") or "PDF 文件")
            pages = int(payload.get("page_count") or 0)
            body = f"已安全保存 {name}"
            if pages:
                body += f"（{pages} 页）"
            body += "，现在可以继续进行总结、翻译、问答或论文分析。"
            return Opportunity(
                intent="file_ready",
                title="文件已就绪",
                body=body,
                reason="new_file_available",
                source_label="文件",
                priority=20,
                metadata=payload,
            )
        if event_type in {"weather.changed", "travel.weather_changed", "travel.outdoor_risk"}:
            city = str(payload.get("city") or "目的地")
            summary = str(payload.get("summary") or "天气发生明显变化")
            outdoor_risk = event_type == "travel.outdoor_risk"
            return Opportunity(
                intent="travel_outdoor_risk" if outdoor_risk else "travel_weather_alert",
                title=f"{city}{'户外行程风险' if outdoor_risk else '天气变化'}",
                body=(
                    summary + (" 系统已标记受影响的户外日程，可据此生成室内替代草案。" if outdoor_risk else "")
                ),
                reason="outdoor_weather_risk" if outdoor_risk else "material_weather_change",
                source_label="旅行天气",
                priority=85 if outdoor_risk else 70,
                metadata=payload,
            )
        return None
