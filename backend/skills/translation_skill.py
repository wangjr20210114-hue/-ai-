"""Translation skill."""
from __future__ import annotations

import re
from typing import Any

from agent.contracts import FailurePolicy, PermissionLevel, RiskLevel, SkillParameter, SkillSchema
from skills.base_skill import BaseSkill, SkillResult


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


class TranslationSkill(BaseSkill):
    @property
    def name(self) -> str:
        return "translation"

    @property
    def description(self) -> str:
        return "翻译外文。用户输入英文/日文/韩文等外文，或明确要求翻译"

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
            examples=["translate this paragraph", "这句英文什么意思"],
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
    def failure_policy(self) -> FailurePolicy:
        return FailurePolicy(max_retries=1, retry_backoff_seconds=0.2, user_visible=True)

    @property
    def planner_steps(self) -> list[str]:
        return ["detect_language", "translate", "respond"]

    async def suggest(self, message: str, params: dict[str, Any]) -> SkillResult:
        lang = params.get("source_lang") or _detect_foreign_language(message)
        if lang:
            lang_label = {"en": "英文", "ja": "日文", "ko": "韩文"}.get(lang, "外文")
            content = f"检测到你输入了{lang_label}，我来帮你翻译成中文。"
        else:
            content = "我来帮你翻译。"
        return SkillResult(
            intent=self.name,
            mode=self.mode,
            content=content,
            icon=self.icon,
            action_label=self.action_label,
            params={**params, "text": message, "source_lang": lang, "target_lang": "zh"},
        )