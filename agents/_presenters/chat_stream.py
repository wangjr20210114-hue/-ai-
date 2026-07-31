"""Single owner of the public chat SSE wire protocol."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

from agents._domain.search.evidence import SearchEvidence


PROGRESS_STAGES = frozenset({
    "planning",
    "retrieval",
    "verification",
    "synthesis",
    "finalizing",
    "complete",
})
PROGRESS_STATUSES = frozenset({"active", "completed", "skipped"})
PROGRESS_ACTIVITIES = frozenset({
    "general",
    "web_search",
    "paper_search",
    "place_search",
    "route_planning",
    "calendar_preparation",
    "meeting_preparation",
    "image_generation",
    "image_review",
    "component_action",
})
_TOOL_ACTIVITIES = {
    "rich_search": ("retrieval", "web_search"),
    "search_arxiv": ("retrieval", "paper_search"),
    "search_places": ("retrieval", "place_search"),
    "recommend_places_on_map": ("retrieval", "place_search"),
    "recommend_nearby_places_on_map": ("retrieval", "place_search"),
    "plan_route_between_places": ("verification", "route_planning"),
    "propose_calendar_changes": ("verification", "calendar_preparation"),
    "propose_meeting": ("verification", "meeting_preparation"),
    "propose_image": ("verification", "image_generation"),
    "image_generation_planning": ("planning", "image_generation"),
    "collect_page_images": ("retrieval", "image_review"),
    "search_rich_images": ("retrieval", "image_review"),
    "analyze_images_parallel": ("verification", "image_review"),
}
_PUBLIC_STAGE_DETAIL_KEYS = frozenset({
    "activity",
    "cache_hit",
    "coalesced",
    "provider",
    "source_count",
    "status",
})
_EVENT_NAME = re.compile(r"^[a-z][a-z0-9_]*$")


def progress_event(
    stage: str,
    status: str,
    *,
    activity: str = "general",
) -> dict[str, Any]:
    """Build controller-owned progress without accepting free-form reasoning."""
    if stage not in PROGRESS_STAGES:
        raise ValueError(f"Unknown progress stage {stage!r}")
    if status not in PROGRESS_STATUSES:
        raise ValueError(f"Unknown progress status {status!r}")
    if activity not in PROGRESS_ACTIVITIES:
        raise ValueError(f"Unknown progress activity {activity!r}")
    return {
        "type": "progress_event",
        "payload": {
            "schema_version": 1,
            "stage": stage,
            "status": status,
            "activity": activity,
            "source": "controller",
        },
    }


def tool_progress_event(tool_name: str, status: str) -> dict[str, Any]:
    stage, activity = _TOOL_ACTIVITIES.get(
        str(tool_name or ""),
        ("verification", "component_action"),
    )
    return progress_event(stage, status, activity=activity)


def _evidence_payload(
    evidence: SearchEvidence | Mapping[str, Any],
) -> dict[str, Any]:
    if isinstance(evidence, SearchEvidence):
        return {
            "query": evidence.query,
            "results": [source.to_dict() for source in evidence.sources],
            "media": [item.to_dict() for item in evidence.media],
            "images": [item.url for item in evidence.media],
            "total": evidence.total,
            "media_pending": evidence.media_pending,
        }
    return dict(evidence)


class ChatStreamPresenter:
    """Serialize all chat events while retaining the established JSON schema."""

    def frame(
        self,
        payload: Mapping[str, Any],
        *,
        event: str | None = None,
    ) -> bytes:
        body = dict(payload)
        event_name = str(event or body.get("type") or "message")
        if not _EVENT_NAME.fullmatch(event_name):
            raise ValueError(f"Invalid SSE event name {event_name!r}")
        serialized = json.dumps(
            body,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        return f"event: {event_name}\ndata: {serialized}\n\n".encode("utf-8")

    def stage(
        self,
        name: str,
        detail: Mapping[str, Any] | None = None,
        elapsed_ms: int = 0,
    ) -> bytes:
        public_detail = {
            key: value
            for key, value in dict(detail or {}).items()
            if key in _PUBLIC_STAGE_DETAIL_KEYS
        }
        status = str(public_detail.pop("status", "active"))
        activity = str(public_detail.pop("activity", "general"))
        payload = progress_event(name, status, activity=activity)
        payload["payload"].update(public_detail)
        payload["payload"]["elapsed_ms"] = max(0, int(elapsed_ms))
        return self.frame(payload, event="stage")

    def sources(
        self,
        evidence: SearchEvidence | Mapping[str, Any],
    ) -> bytes:
        return self.frame(
            {
                "type": "search_results",
                "payload": _evidence_payload(evidence),
            },
            event="sources",
        )

    def token(self, text: str) -> bytes:
        return self.frame(
            {"type": "ai_response", "content": str(text or "")},
            event="token",
        )

    def media(
        self,
        evidence: SearchEvidence | Mapping[str, Any],
    ) -> bytes:
        return self.frame(
            {
                "type": "search_media",
                "payload": _evidence_payload(evidence),
            },
            event="media",
        )

    def error(self, code: str, message: str) -> bytes:
        return self.frame(
            {
                "type": "error_message",
                "code": str(code or "internal_error"),
                "content": str(message or "请求失败"),
            },
            event="error",
        )

    def done(self, turn_id: str = "") -> bytes:
        return self.frame(
            {
                "type": "answer_complete",
                "payload": {"turn_id": str(turn_id or "")},
            },
            event="done",
        )

    @staticmethod
    def transport_done() -> bytes:
        return b"data: [DONE]\n\n"
