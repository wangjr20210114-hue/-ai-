"""Typed service ports available to trusted system Skill adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from ..search.search_use_case import SearchExecution, SearchRequest


class SearchService(Protocol):
    async def search(
        self,
        request: SearchRequest,
        *,
        on_media=None,
    ) -> SearchExecution: ...


class MapsService(Protocol):
    async def invoke(
        self,
        operation: str,
        payload: Mapping[str, Any],
    ) -> Mapping[str, Any]: ...


class CalendarService(Protocol):
    async def propose(
        self,
        payload: Mapping[str, Any],
    ) -> Mapping[str, Any]: ...


class WorkspaceService(Protocol):
    async def propose(
        self,
        kind: str,
        payload: Mapping[str, Any],
    ) -> Mapping[str, Any]: ...


class GenericSkillService(Protocol):
    async def invoke(
        self,
        operation: str,
        payload: Mapping[str, Any],
    ) -> Mapping[str, Any]: ...


SERVICE_PERMISSIONS = {
    "search": "components.search",
    "maps": "components.maps",
    "calendar": "components.calendar",
    "meeting": "components.calendar",
    "image": "components.image",
    "vision": "components.search",
    "papers": "components.files",
    "workspace": "components.workspace",
}


@dataclass(frozen=True, slots=True)
class SkillServices:
    search: SearchService | None = None
    maps: MapsService | None = None
    calendar: CalendarService | None = None
    meeting: GenericSkillService | None = None
    image: GenericSkillService | None = None
    vision: GenericSkillService | None = None
    papers: GenericSkillService | None = None
    workspace: WorkspaceService | None = None

    def get(self, name: str) -> Any:
        if name not in SERVICE_PERMISSIONS:
            raise ValueError(f"Unknown Skill service {name!r}")
        return getattr(self, name)

