"""Trusted structured progress View for chat SSE.

Events describe controller lifecycle only. They never accept model prose,
hidden reasoning, prompts, tool arguments, or chain-of-thought.
"""

from __future__ import annotations


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


def progress_event(
    stage: str,
    status: str,
    *,
    activity: str = "general",
) -> dict:
    """Build a fixed-schema event from controller-owned enum values only."""
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


def tool_progress_event(tool_name: str, status: str) -> dict:
    stage, activity = _TOOL_ACTIVITIES.get(
        str(tool_name or ""),
        ("verification", "component_action"),
    )
    return progress_event(stage, status, activity=activity)
