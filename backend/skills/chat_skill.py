"""General conversational skill backed by the unified model gateway."""
from __future__ import annotations

from typing import Any, AsyncIterator

from agent.cancellation import CancellationToken
from agent.contracts import FailurePolicy, PermissionLevel, RiskLevel, SkillSchema
from config import settings
from services.model_gateway import CallContext, ModelGateway, ModelRequest
from skills.base_skill import BaseSkill, SkillResult, SkillStreamEvent


def _history_messages(history: list[str], current_message: str) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    for line in history[-14:]:
        if line.startswith("用户: "):
            content = line[4:]
            # WebSocket context already contains the incoming user line. The
            # current request is appended once below to avoid duplicated turns.
            if content == current_message and line == history[-1]:
                continue
            messages.append({"role": "user", "content": content})
        elif line.startswith("AI("):
            separator = line.find("): ")
            if separator > 0:
                messages.append({"role": "assistant", "content": line[separator + 3 :]})
    return messages


class ChatSkill(BaseSkill):
    def __init__(self, gateway: ModelGateway | None = None) -> None:
        self.gateway = gateway

    @property
    def name(self) -> str:
        return "chat"

    @property
    def description(self) -> str:
        return "处理不属于其他专用能力的普通对话、解释、建议与问答"

    @property
    def trigger_keywords(self) -> list[str]:
        return []

    @property
    def schema(self) -> SkillSchema:
        return SkillSchema(
            intent=self.name,
            description=self.description,
            examples=["你好", "解释一下这个概念", "给我一些建议"],
            output_modes=["stream", "markdown"],
        )

    @property
    def mode(self) -> str:
        return "auto"

    @property
    def permission_level(self) -> PermissionLevel:
        return PermissionLevel.AUTO

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.LOW

    @property
    def streaming(self) -> bool:
        return True

    @property
    def failure_policy(self) -> FailurePolicy:
        return FailurePolicy(max_retries=1, retry_backoff_seconds=0.5, user_visible=True)

    @property
    def planner_steps(self) -> list[str]:
        return ["load_context", "generate_response", "persist_response"]

    async def suggest(self, message: str, params: dict[str, Any]) -> SkillResult:
        del message, params
        return SkillResult(intent=self.name, mode="auto", content="正在回答。")

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
        del params
        if self.gateway is None:
            raise RuntimeError("ChatSkill requires ModelGateway in execution runtime")
        messages: list[dict[str, str]] = [
            {
                "role": "system",
                "content": (
                    "你是元宝主动式 Agent。回答应准确、自然、可执行，并明确区分事实、推断和建议。"
                    "除非用户要求，否则保持简洁；使用 Markdown；不要声称已经执行未实际执行的操作。"
                ),
            },
            *_history_messages(history, message),
            {"role": "user", "content": message},
        ]
        full_text = ""
        async for chunk in self.gateway.stream_text(
            ModelRequest(
                messages=messages,
                provider=settings.llm_provider,
                model=settings.llm_model,
                max_tokens=1800,
                temperature=0.7,
                operation="chat",
            ),
            CallContext(run_id=run_id, conversation_id=session_id, skill_name=self.name),
            cancellation,
        ):
            if chunk.delta:
                full_text += chunk.delta
                yield SkillStreamEvent(delta=chunk.delta)
            if chunk.done:
                yield SkillStreamEvent(
                    done=True,
                    content=full_text,
                    data={"provider": chunk.provider, "model": chunk.model},
                    usage=chunk.usage.to_dict(),
                    provider_request_id=chunk.provider_request_id,
                )
