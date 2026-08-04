"""Application contracts exposed by trusted built-in Skill components."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ClarificationFieldInput(BaseModel):
    """Strong schema shown to the model for every clarification field."""

    id: str = Field(description="Stable semantic field id derived from the unresolved part of the user's request")
    label: str = Field(
        description=(
            "Short user-visible question grounded in the current request, recent dialogue, "
            "or a directly relevant safe memory; never invent a generic profile question"
        ),
    )
    type: Literal["single", "multi", "boolean", "text", "date", "time", "datetime"] = Field(
        description=(
            "Interaction type. Prefer single/multi for finite choices, boolean for yes/no, "
            "date for a missing date, time when the date is already known, datetime when both "
            "are missing, and text only when the answer cannot be enumerated."
        ),
    )
    required: bool = Field(default=True, description="Whether the user must answer this field")
    options: list[str] = Field(
        default_factory=list,
        description="Two to eight natural-language options for single or multi; empty for other types",
    )
    placeholder: str = Field(
        default="",
        description="Short example only for a text field; do not use it for choices or dates",
    )


class RouteStopInput(BaseModel):
    """A single ordered route stop exposed to the model as a strict schema."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(
        min_length=1,
        max_length=160,
        description=(
            "Standalone place name or resolved dialogue reference. The first "
            "list item is the origin; preserve every user-requested stop."
        ),
    )
    near_query: str = Field(
        default="",
        max_length=160,
        description=(
            "Separate anchor for a place described relative to another place, "
            "for example query=锦江之星 and near_query=北京301医院."
        ),
    )


class RoutePlanInput(BaseModel):
    """Validated LangChain input contract for two-point and multi-stop routes."""

    model_config = ConfigDict(extra="forbid")

    origin_query: str = Field(
        default="",
        max_length=160,
        description="Origin for a two-place route; do not use when ordered_stops is supplied.",
    )
    destination_query: str = Field(
        default="",
        max_length=160,
        description="Destination for a two-place route; do not use when ordered_stops is supplied.",
    )
    city: str = Field(
        default="全国",
        max_length=80,
        description=(
            "Search city shared by the user's route. If the request or an earlier "
            "verified stop provides a city, pass that city instead of 全国 so later "
            "same-city POIs are not mixed with unrelated national results. Use "
            "全国 only when the conversation provides no reliable city."
        ),
    )
    origin_near_query: str = Field(default="", max_length=160)
    destination_near_query: str = Field(default="", max_length=160)
    nearby_radius_meters: int = Field(default=5_000, ge=500, le=20_000)
    route_mode: Literal["default", "driving", "transit", "walking", "bicycling"] = Field(
        default="default",
        description=(
            "Travel mode explicitly requested by the user. Use default to honor "
            "the user's saved map preference."
        ),
    )
    route_strategy: Literal[
        "default", "time_then_cost", "least_time", "least_cost",
    ] = Field(
        default="default",
        description=(
            "Explicit route tradeoff. Use default when unstated; the saved and "
            "learned preference then applies."
        ),
    )
    use_current_location_as_origin: bool = Field(
        default=False,
        description=(
            "Use the fresh browser location supplied for this request as the origin. "
            "Never invent coordinates or use it when the user stated another origin."
        ),
    )
    ordered_stops: list[RouteStopInput] = Field(
        default_factory=list,
        min_length=0,
        max_length=12,
        description=(
            "For a multi-stop trip, every stop in the user's exact order. "
            "The first item must be the stated origin and the last item the destination."
        ),
    )

    @model_validator(mode="after")
    def validate_endpoints(self):
        if self.ordered_stops:
            if len(self.ordered_stops) < 2 and not self.use_current_location_as_origin:
                raise ValueError("有序路线至少需要起点和终点")
            return self
        if (
            not self.destination_query.strip()
            or (not self.origin_query.strip() and not self.use_current_location_as_origin)
        ):
            raise ValueError("两点路线必须同时提供起点和终点")
        return self


class ProviderPlaceDecision(BaseModel):
    """Bounded semantic review of one Tencent candidate set."""

    model_config = ConfigDict(extra="forbid")

    unique_intent: bool = Field(
        default=False,
        description=(
            "True only when one supplied Tencent POI is a near-certain "
            "interpretation of the user's place text."
        ),
    )
    selected_place_id: str = Field(
        default="",
        description="One exact supplied place_id when unique_intent is true.",
    )


class PaperKnowledgeCandidate(BaseModel):
    """A paper identity recalled by the fast model, pending official verification."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(
        default="",
        max_length=300,
        description="Exact paper title if confidently known.",
    )
    arxiv_id: str = Field(
        default="",
        max_length=80,
        description="Exact arXiv identifier only; empty when it is not confidently known.",
    )
    authors: list[str] = Field(
        default_factory=list,
        max_length=20,
        description="Known authors, used only as supporting context.",
    )
    year: int = Field(default=0, ge=0, le=2200)


class PaperKnowledgeCandidates(BaseModel):
    """Bounded internal-knowledge proposal; candidates are not yet facts."""

    model_config = ConfigDict(extra="forbid")

    candidates: list[PaperKnowledgeCandidate] = Field(
        default_factory=list,
        max_length=8,
    )


class PaperSearchEvidenceCandidate(BaseModel):
    """A paper selected from one exact Makers SearchPro source record."""

    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(
        default="",
        max_length=80,
        description="Exact source id from the supplied SearchPro evidence.",
    )
    title: str = Field(default="", max_length=300)
    authors: list[str] = Field(default_factory=list, max_length=20)
    year: int = Field(default=0, ge=0, le=2200)
    arxiv_id: str = Field(
        default="",
        max_length=80,
        description=(
            "Exact arXiv identifier only when it appears verbatim in the supplied "
            "source URL, title, or snippet; empty otherwise."
        ),
    )


class PaperSearchEvidenceCandidates(BaseModel):
    """Bounded source-grounded fallback extraction."""

    model_config = ConfigDict(extra="forbid")

    candidates: list[PaperSearchEvidenceCandidate] = Field(
        default_factory=list,
        max_length=8,
    )


__all__ = (
    "ClarificationFieldInput",
    "RouteStopInput",
    "RoutePlanInput",
    "ProviderPlaceDecision",
    "PaperKnowledgeCandidate",
    "PaperKnowledgeCandidates",
    "PaperSearchEvidenceCandidate",
    "PaperSearchEvidenceCandidates",
)
