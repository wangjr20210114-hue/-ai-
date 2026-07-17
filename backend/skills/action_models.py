"""Versioned, validated inputs for side-effecting skills."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator


class VersionedActionInput(BaseModel):
    schema_version: int = Field(default=1, ge=1)


class MeetingActionInput(VersionedActionInput):
    subject: str = Field(min_length=1, max_length=120)
    start_time: datetime
    end_time: datetime
    duration_minutes: int = Field(default=60, ge=5, le=24 * 60)

    @field_validator("subject")
    @classmethod
    def clean_subject(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def validate_range(self) -> "MeetingActionInput":
        if self.end_time <= self.start_time:
            raise ValueError("meeting end_time must be after start_time")
        return self


class ImageActionInput(VersionedActionInput):
    prompt: str = Field(min_length=1, max_length=4000)

    @field_validator("prompt")
    @classmethod
    def clean_prompt(cls, value: str) -> str:
        return value.strip()
