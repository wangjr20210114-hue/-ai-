"""Pure proactive decision models."""

from pydantic import BaseModel, ConfigDict


class WeatherRiskDecision(BaseModel):
    """Semantic assessment over provider weather facts."""

    model_config = ConfigDict(extra="forbid")

    actionable: bool = False
    priority: str = "normal"
