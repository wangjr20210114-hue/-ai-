"""Intent classification through the shared ModelGateway with deterministic fallback."""
from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from agent import register_all_skills
from config import settings
from services.model_gateway import CallContext, ModelGateway, ModelRequest
from skills.base_skill import SkillRegistry

logger = logging.getLogger(__name__)


class IntentClassification(BaseModel):
    intent: str = "chat"
    params: dict[str, Any] = Field(default_factory=dict)
    confidence: float | None = None
    rationale: str = ""


class IntentRouter:
    def __init__(self, registry: SkillRegistry, gateway: ModelGateway | None) -> None:
        self.registry = registry
        self.gateway = gateway

    def fallback(self, message: str, *, reason: str) -> dict[str, Any]:
        keyword_match = self.registry.keyword_check(message)
        return {
            "intent": keyword_match or "chat",
            "params": {},
            "confidence": 0.0,
            "rationale": reason,
            "classification_mode": "keyword_fallback" if keyword_match else "chat_fallback",
        }

    async def classify(
        self,
        message: str,
        history: list[str] | None = None,
        *,
        run_id: str | None = None,
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        if self.gateway is None:
            return self.fallback(message, reason="model_gateway_not_injected")

        from prompts.templates import INTENT_CLASSIFICATION_PROMPT

        system_prompt = INTENT_CLASSIFICATION_PROMPT.replace(
            "{{SKILLS}}", self.registry.build_llm_description()
        )
        history_text = "\n".join((history or [])[-8:])
        user_content = f"用户消息：{message}"
        if history_text:
            user_content += f"\n\n对话历史：\n{history_text}"
        try:
            result = await self.gateway.complete_json(
                ModelRequest(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content},
                    ],
                    provider="deepseek",
                    model=settings.deepseek_model,
                    max_tokens=240,
                    temperature=0.1,
                    operation="intent_classification",
                ),
                IntentClassification,
                CallContext(
                    run_id=run_id,
                    conversation_id=conversation_id,
                    skill_name="intent_router",
                ),
            )
        except Exception as error:  # classification has a safe deterministic fallback
            logger.warning("intent classification fallback: %s: %s", type(error).__name__, error)
            return self.fallback(message, reason=f"{type(error).__name__}: {error}")

        if self.registry.get(result.intent) is None:
            return self.fallback(message, reason=f"unknown_intent:{result.intent}")
        return {
            **result.model_dump(),
            "classification_mode": "model_gateway",
        }


# Compatibility entry point for isolated callers and existing tests. Production
# composes one shared IntentRouter in main.lifespan and injects it into Orchestrator.
_schema_registry = SkillRegistry()
register_all_skills(_schema_registry)
_compat_router = IntentRouter(_schema_registry, gateway=None)


async def classify_intent(
    message: str,
    history: list[str] | None = None,
) -> dict[str, Any]:
    return await _compat_router.classify(message, history)
