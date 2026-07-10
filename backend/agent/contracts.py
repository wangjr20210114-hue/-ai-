"""Core Agent contracts.

These dataclasses are the backbone of the runtime. They keep the pipeline explicit:
classify -> plan -> policy -> execute -> observe -> respond.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


class PermissionLevel(str, Enum):
    AUTO = "auto"          # Execute without extra confirmation.
    SUGGEST = "suggest"    # Render a suggestion card or guided assistant.
    CONFIRM = "confirm"    # User confirmation required before side effects.
    DENY = "deny"          # Do not execute.


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ExecutionStatus(str, Enum):
    CREATED = "created"
    CLASSIFIED = "classified"
    PLANNED = "planned"
    POLICY_CHECKED = "policy_checked"
    EXECUTING = "executing"
    WAITING_CONFIRMATION = "waiting_confirmation"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class ResponseType(str, Enum):
    NONE = "none"
    STREAM = "stream"
    SUGGESTION = "suggestion"
    SKILL_RESULT = "skill_result"
    ERROR = "error"


@dataclass(slots=True)
class SkillParameter:
    name: str
    type: str = "string"
    description: str = ""
    required: bool = False
    default: Any = None
    enum: list[Any] = field(default_factory=list)


@dataclass(slots=True)
class SkillSchema:
    intent: str
    description: str
    parameters: list[SkillParameter] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)
    output_modes: list[str] = field(default_factory=list)

    def to_prompt(self) -> str:
        params = []
        for p in self.parameters:
            required = "required" if p.required else "optional"
            enum = f" enum={p.enum}" if p.enum else ""
            params.append(f"{p.name}:{p.type}({required}) {p.description}{enum}")
        joined = "; ".join(params) if params else "no structured params"
        return f"{self.intent}: {self.description}. Params: {joined}"


@dataclass(slots=True)
class ConfirmationPolicy:
    required: bool = False
    reason: str = ""
    action_label: str = "执行"
    reversible: bool = True


@dataclass(slots=True)
class FailurePolicy:
    max_retries: int = 0
    retry_backoff_seconds: float = 0.0
    user_visible: bool = True
    fallback_intent: str = "chat"


@dataclass(slots=True)
class AgentPlan:
    run_id: str
    session_id: str
    event_type: str
    user_message: str
    intent: str
    params: dict[str, Any] = field(default_factory=dict)
    skill_name: str = ""
    schema: SkillSchema | None = None
    permission_level: PermissionLevel = PermissionLevel.SUGGEST
    risk_level: RiskLevel = RiskLevel.LOW
    confirmation: ConfirmationPolicy = field(default_factory=ConfirmationPolicy)
    failure_policy: FailurePolicy = field(default_factory=FailurePolicy)
    steps: list[str] = field(default_factory=list)
    rationale: str = ""
    created_at: float = field(default_factory=time.time)


@dataclass(slots=True)
class PolicyDecision:
    permission_level: PermissionLevel
    allowed: bool
    requires_confirmation: bool = False
    reason: str = ""
    risk_level: RiskLevel = RiskLevel.LOW
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AgentObservation:
    run_id: str
    session_id: str
    status: ExecutionStatus
    intent: str = ""
    step: str = ""
    message: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    ts: float = field(default_factory=time.time)


@dataclass(slots=True)
class AgentResponse:
    run_id: str
    response_type: ResponseType = ResponseType.NONE
    payload: dict[str, Any] = field(default_factory=dict)
    handled_by_transport: bool = False
    observation: AgentObservation | None = None