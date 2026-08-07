"""Application contracts exposed by trusted built-in Skill components."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..i18n import text


def _schema(key: str) -> str:
    return text(f"model.tool_schema.{key}", "zh-CN")


class ClarificationFieldInput(BaseModel):
    """Strong schema shown to the model for every clarification field."""

    id: str = Field(description=_schema("field_01"))
    label: str = Field(
        description=_schema("field_02"),
    )
    type: Literal["single", "multi", "boolean", "text", "date", "time", "datetime"] = Field(
        description=_schema("field_03"),
    )
    required: bool = Field(default=True, description=_schema("field_04"))
    options: list[str] = Field(
        default_factory=list,
        description=_schema("field_05"),
    )
    placeholder: str = Field(
        default="",
        description=_schema("field_06"),
    )


class RouteStopInput(BaseModel):
    """A single ordered route stop exposed to the model as a strict schema."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(
        min_length=1,
        max_length=160,
        description=_schema("field_07"),
    )
    near_query: str = Field(
        default="",
        max_length=160,
        description=_schema("field_08"),
    )


class RoutePlaceEditInput(BaseModel):
    """One trusted edit against the latest verified route place set."""

    model_config = ConfigDict(extra="forbid")

    operation: Literal["add", "remove", "replace"] = Field(
        description=_schema("field_54"),
    )
    target_query: str = Field(
        default="",
        max_length=160,
        description=_schema("field_55"),
    )
    new_query: str = Field(
        default="",
        max_length=160,
        description=_schema("field_56"),
    )
    new_near_query: str = Field(
        default="",
        max_length=160,
        description=_schema("field_57"),
    )
    position: Literal["default", "start", "end", "before", "after"] = Field(
        default="default",
        description=_schema("field_58"),
    )


class RoutePlanInput(BaseModel):
    """Validated LangChain input contract for two-point and multi-stop routes."""

    model_config = ConfigDict(extra="forbid")

    origin_query: str = Field(
        default="",
        max_length=160,
        description=_schema("field_09"),
    )
    destination_query: str = Field(
        default="",
        max_length=160,
        description=_schema("field_10"),
    )
    city: str = Field(
        default="全国",
        max_length=80,
        description=_schema("field_11"),
    )
    origin_near_query: str = Field(default="", max_length=160)
    destination_near_query: str = Field(default="", max_length=160)
    nearby_radius_meters: int = Field(default=5_000, ge=500, le=20_000)
    route_mode: Literal["default", "driving", "transit", "walking", "bicycling"] = Field(
        default="default",
        description=_schema("field_12"),
    )
    route_strategy: Literal[
        "default", "time_then_cost", "least_time", "least_cost",
    ] = Field(
        default="default",
        description=_schema("field_13"),
    )
    use_current_location_as_origin: bool = Field(
        default=False,
        description=_schema("field_14"),
    )
    ordered_stops: list[RouteStopInput] = Field(
        default_factory=list,
        min_length=0,
        max_length=12,
        description=_schema("field_15"),
    )
    place_edits: list[RoutePlaceEditInput] = Field(
        default_factory=list,
        max_length=8,
        description=_schema("field_59"),
    )

    @model_validator(mode="after")
    def validate_endpoints(self):
        if self.place_edits:
            return self
        if self.ordered_stops:
            if len(self.ordered_stops) < 2 and not self.use_current_location_as_origin:
                raise ValueError(text("route.schema.ordered_stops", "zh-CN"))
            return self
        if (
            not self.destination_query.strip()
            or (not self.origin_query.strip() and not self.use_current_location_as_origin)
        ):
            raise ValueError(text("route.schema.endpoints", "zh-CN"))
        return self


class ProviderPlaceDecision(BaseModel):
    """Bounded semantic review of one Tencent candidate set."""

    model_config = ConfigDict(extra="forbid")

    unique_intent: bool = Field(
        default=False,
        description=_schema("field_16"),
    )
    selected_place_id: str = Field(
        default="",
        description=_schema("field_17"),
    )


class PaperKnowledgeCandidate(BaseModel):
    """A paper identity recalled by the fast model, pending official verification."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(
        default="",
        max_length=300,
        description=_schema("field_18"),
    )
    arxiv_id: str = Field(
        default="",
        max_length=80,
        description=_schema("field_19"),
    )
    authors: list[str] = Field(
        default_factory=list,
        max_length=20,
        description=_schema("field_20"),
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
        description=_schema("field_21"),
    )
    title: str = Field(default="", max_length=300)
    authors: list[str] = Field(default_factory=list, max_length=20)
    year: int = Field(default=0, ge=0, le=2200)
    arxiv_id: str = Field(
        default="",
        max_length=80,
        description=_schema("field_22"),
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
    "RoutePlaceEditInput",
    "RouteStopInput",
    "RoutePlanInput",
    "ProviderPlaceDecision",
    "PaperKnowledgeCandidate",
    "PaperKnowledgeCandidates",
    "PaperSearchEvidenceCandidate",
    "PaperSearchEvidenceCandidates",
)
