"""Skill base classes and registry."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from agent.contracts import (
    AgentPlan,
    ConfirmationPolicy,
    FailurePolicy,
    PermissionLevel,
    RiskLevel,
    SkillSchema,
)


@dataclass
class SkillResult:
    """Unified skill result rendered by transports such as WebSocket."""

    intent: str
    mode: str = "suggest"
    content: str = ""
    icon: str = "✨"
    action_label: str = "执行"
    params: dict[str, Any] = field(default_factory=dict)
    data: dict[str, Any] = field(default_factory=dict)


class BaseSkill(ABC):
    """Base class for all Agent skills.

    A skill owns its schema, permissions, planning hints, failure behavior, and
    default rendering. The orchestrator should not need to know per-skill safety
    rules except through this contract.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Stable skill identifier, for example travel or meeting."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Human/LLM-readable capability description."""

    @property
    @abstractmethod
    def trigger_keywords(self) -> list[str]:
        """Fast keyword fallback for intent routing."""

    @property
    def schema(self) -> SkillSchema:
        return SkillSchema(intent=self.name, description=self.description)

    @property
    def icon(self) -> str:
        return "✨"

    @property
    def action_label(self) -> str:
        return "执行"

    @property
    def mode(self) -> str:
        return "suggest"

    @property
    def permission_level(self) -> PermissionLevel:
        if self.mode == "auto":
            return PermissionLevel.AUTO
        if self.mode == "immediate":
            return PermissionLevel.AUTO
        return PermissionLevel.SUGGEST

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.LOW

    @property
    def confirmation_policy(self) -> ConfirmationPolicy:
        return ConfirmationPolicy(
            required=self.permission_level == PermissionLevel.CONFIRM,
            action_label=self.action_label,
        )

    @property
    def failure_policy(self) -> FailurePolicy:
        return FailurePolicy(max_retries=0, user_visible=True)

    @property
    def planner_steps(self) -> list[str]:
        return ["prepare", "execute", "respond"]

    async def can_handle(self, message: str, params: dict[str, Any]) -> bool:
        return True

    async def create_plan(
        self,
        *,
        run_id: str,
        session_id: str,
        event_type: str,
        message: str,
        params: dict[str, Any],
        rationale: str = "",
    ) -> AgentPlan:
        return AgentPlan(
            run_id=run_id,
            session_id=session_id,
            event_type=event_type,
            user_message=message,
            intent=self.name,
            skill_name=self.name,
            params=params,
            schema=self.schema,
            permission_level=self.permission_level,
            risk_level=self.risk_level,
            confirmation=self.confirmation_policy,
            failure_policy=self.failure_policy,
            steps=self.planner_steps,
            rationale=rationale,
        )

    async def execute(self, message: str, params: dict[str, Any], session_id: str) -> SkillResult:
        return await self.handle(message, params, session_id)

    async def render(self, result: SkillResult) -> SkillResult:
        return result

    async def failure_result(self, message: str, params: dict[str, Any], error: Exception) -> SkillResult:
        return SkillResult(
            intent=self.name,
            mode="immediate",
            content=f"处理 {self.name} 时出错：{type(error).__name__}: {error}",
            icon=self.icon,
            action_label=self.action_label,
            params=params,
            data={"error_type": type(error).__name__},
        )

    @abstractmethod
    async def suggest(self, message: str, params: dict[str, Any]) -> SkillResult:
        """Create a user-visible suggestion or immediate result."""

    async def handle(self, message: str, params: dict[str, Any], session_id: str) -> SkillResult:
        return await self.suggest(message, params)


class SkillRegistry:
    """Registry for all skills."""

    def __init__(self) -> None:
        self._skills: dict[str, BaseSkill] = {}

    def register(self, skill: BaseSkill) -> None:
        self._skills[skill.name] = skill

    def get(self, name: str) -> BaseSkill | None:
        return self._skills.get(name)

    def all_skills(self) -> list[BaseSkill]:
        return list(self._skills.values())

    def keyword_check(self, text: str) -> str | None:
        for skill in self._skills.values():
            for kw in skill.trigger_keywords:
                if kw in text:
                    return skill.name
        return None

    def build_llm_description(self) -> str:
        return "\n".join(f"- **{skill.name}**: {skill.schema.to_prompt()}" for skill in self._skills.values())