"""Skill base classes and registry.

Skills describe capabilities and execute validated inputs.  They never mutate Run
state and never write directly to a transport.  Side-effecting skills must expose
a versioned Pydantic input model and an idempotency strategy.
"""
from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, TypeVar

from pydantic import BaseModel

from agent.cancellation import CancellationToken
from agent.contracts import (
    AgentPlan,
    ConfirmationPolicy,
    FailurePolicy,
    PermissionLevel,
    RiskLevel,
    SkillSchema,
)


class ActionInputError(ValueError):
    """The proposed side effect is missing fields required for confirmation."""


@dataclass(slots=True)
class SkillExecutionContext:
    run_id: str
    action_id: str
    idempotency_key: str
    user_id: str = "local-user"


@dataclass(slots=True)
class SkillExecutionResult:
    content: str
    data: dict[str, Any] = field(default_factory=dict)
    provider_request_id: str = ""
    usage: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SkillStreamEvent:
    """Transport-neutral event emitted by a streaming skill.

    Skills only emit semantic stream events. The Executor owns persistence, Run
    completion, and best-effort delivery to WebSocket or future transports.
    """

    delta: str = ""
    event_type: str = ""
    done: bool = False
    content: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    usage: dict[str, Any] = field(default_factory=dict)
    provider_request_id: str = ""


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


ActionModel = TypeVar("ActionModel", bound=BaseModel)


class BaseSkill(ABC):
    """Base class for all Agent skills."""

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
        if self.mode in {"auto", "immediate"}:
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

    @property
    def side_effect(self) -> bool:
        return False

    @property
    def streaming(self) -> bool:
        return False

    @property
    def action_input_model(self) -> type[BaseModel] | None:
        return None

    def estimated_cost_cny(self, input_model: BaseModel) -> float:
        del input_model
        return 0.0

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
            side_effect=self.side_effect,
        )

    async def execute(self, message: str, params: dict[str, Any], session_id: str) -> SkillResult:
        return await self.handle(message, params, session_id)

    async def stream(
        self,
        message: str,
        params: dict[str, Any],
        session_id: str,
        history: list[str],
        *,
        run_id: str,
        cancellation: CancellationToken | None = None,
    ) -> AsyncIterator[SkillStreamEvent]:
        del message, params, session_id, history, run_id, cancellation
        raise RuntimeError(f"skill {self.name} does not implement streaming")
        if False:  # pragma: no cover - keeps this method an async generator
            yield SkillStreamEvent()

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

    async def prepare_action_input(self, message: str, params: dict[str, Any]) -> BaseModel:
        raise ActionInputError(f"skill {self.name} does not support side-effect actions")

    def action_idempotency_key(self, input_model: BaseModel, run_id: str) -> str:
        canonical = json.dumps(input_model.model_dump(mode="json"), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]
        return f"{self.name}:{run_id}:{digest}"

    async def execute_action(
        self,
        input_model: BaseModel,
        context: SkillExecutionContext,
    ) -> SkillExecutionResult:
        raise RuntimeError(f"skill {self.name} has no side-effect executor")

    @abstractmethod
    async def suggest(self, message: str, params: dict[str, Any]) -> SkillResult:
        """Create a user-visible suggestion or immediate result."""

    async def handle(self, message: str, params: dict[str, Any], session_id: str) -> SkillResult:
        return await self.suggest(message, params)

    async def generate_follow_ups(self, user_message: str, ai_content: str) -> list[str]:
        """Generate 3 follow-up questions. Shared implementation for all skills."""
        try:
            import json as _json
            import httpx
            from config import settings
            msgs = [
                {"role": "system", "content": "根据对话上下文，推测用户接下来可能想问的 3 个问题。简短（10字以内），自然口语。输出 JSON 数组 [\"问题1\",\"问题2\",\"问题3\"]"},
                {"role": "user", "content": f"用户问：{user_message}\n\nAI回答：{ai_content[:500]}"},
            ]
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{settings.deepseek_base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {settings.deepseek_api_key}"},
                    json={"model": settings.deepseek_model, "messages": msgs, "max_tokens": 200, "temperature": 0.8},
                )
                resp.raise_for_status()
                content = resp.json()["choices"][0]["message"]["content"].strip().strip("`").strip()
                if content.startswith("json"):
                    content = content[4:].strip()
                result = _json.loads(content)
                if isinstance(result, list):
                    return [str(q) for q in result[:3]]
        except Exception:
            pass
        return []


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
            for keyword in skill.trigger_keywords:
                if keyword in text:
                    return skill.name
        return None

    def build_llm_description(self) -> str:
        return "\n".join(f"- **{skill.name}**: {skill.schema.to_prompt()}" for skill in self._skills.values())
