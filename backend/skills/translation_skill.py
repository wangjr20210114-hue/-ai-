"""Translation skill backed by the unified model gateway."""
from __future__ import annotations

from typing import Any, AsyncIterator

from agent.cancellation import CancellationToken
from agent.contracts import FailurePolicy, PermissionLevel, RiskLevel, SkillParameter, SkillSchema
from config import settings
from services.model_gateway import CallContext, ModelGateway, ModelRequest
from skills.base_skill import BaseSkill, SkillResult, SkillStreamEvent


def _detect_foreign_language(text: str) -> str | None:
    latin = sum(1 for c in text if "\u0041" <= c <= "\u007a" or "\u0041" <= c.upper() <= "\u005a")
    cjk = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    if latin > 5 and cjk < latin // 2:
        return "en"
    kana = sum(1 for c in text if "\u3040" <= c <= "\u30ff")
    if kana > 3:
        return "ja"
    hangul = sum(1 for c in text if "\uac00" <= c <= "\ud7af")
    if hangul > 3:
        return "ko"
    return None


_LANGUAGE_LABELS = {
    "zh": "中文",
    "en": "英文",
    "ja": "日文",
    "ko": "韩文",
    "fr": "法文",
    "de": "德文",
    "es": "西班牙文",
}


class TranslationSkill(BaseSkill):
    def __init__(self, gateway: ModelGateway | None = None) -> None:
        self.gateway = gateway

    @property
    def name(self) -> str:
        return "translation"

    @property
    def description(self) -> str:
        return "翻译外文或按用户指定的目标语言翻译文本"

    @property
    def trigger_keywords(self) -> list[str]:
        return ["翻译", "translate", "什么意思", "怎么说"]

    @property
    def schema(self) -> SkillSchema:
        return SkillSchema(
            intent=self.name,
            description=self.description,
            parameters=[
                SkillParameter("text", "string", "待翻译文本", True),
                SkillParameter("source_lang", "string", "源语言", False),
                SkillParameter("target_lang", "string", "目标语言", False, "zh"),
            ],
            examples=["translate this paragraph", "把这段话翻译成日文"],
            output_modes=["stream", "translation"],
        )

    @property
    def icon(self) -> str:
        return "🔤"

    @property
    def action_label(self) -> str:
        return "翻译"

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
        return FailurePolicy(max_retries=1, retry_backoff_seconds=0.2, user_visible=True)

    @property
    def planner_steps(self) -> list[str]:
        return ["validate_text", "translate", "persist_response"]

    async def suggest(self, message: str, params: dict[str, Any]) -> SkillResult:
        source = params.get("source_lang") or _detect_foreign_language(str(params.get("text") or message))
        target = str(params.get("target_lang") or "zh")
        return SkillResult(
            intent=self.name,
            mode=self.mode,
            content=f"正在翻译为{_LANGUAGE_LABELS.get(target, target)}。",
            icon=self.icon,
            action_label=self.action_label,
            params={**params, "source_lang": source, "target_lang": target},
        )

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
        del history
        if self.gateway is None:
            raise RuntimeError("TranslationSkill requires ModelGateway in execution runtime")
        text = str(params.get("text") or message).strip()
        if not text:
            raise ValueError("待翻译文本不能为空")
        source = str(params.get("source_lang") or _detect_foreign_language(text) or "auto")
        target = str(params.get("target_lang") or "zh")
        target_label = _LANGUAGE_LABELS.get(target, target)
        full_text = ""
        async for chunk in self.gateway.stream_text(
            ModelRequest(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            f"你是专业翻译。把用户提供的文本翻译成{target_label}。"
                            "准确保留专有名词、数字、格式和语气；只输出译文，不添加说明。"
                        ),
                    },
                    {"role": "user", "content": text},
                ],
                provider="deepseek",
                model=settings.deepseek_model,
                max_tokens=1800,
                temperature=0.2,
                operation="translation",
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
                    data={
                        "source_lang": source,
                        "target_lang": target,
                        "provider": chunk.provider,
                        "model": chunk.model,
                    },
                    usage=chunk.usage.to_dict(),
                    provider_request_id=chunk.provider_request_id,
                )
