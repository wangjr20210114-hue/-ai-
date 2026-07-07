"""翻译技能（占位实现，后续接入翻译 API 或 LLM 翻译）。"""
from __future__ import annotations

import re
from typing import Any

from skills.base_skill import BaseSkill, SkillResult


def _detect_foreign_language(text: str) -> str | None:
    """检测文本是否包含大量外文（拉丁字母），返回语言代码或 None。"""
    latin = sum(1 for c in text if "\u0041" <= c <= "\u007a" or "\u0041" <= c.upper() <= "\u005a")
    cjk = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    if latin > 5 and cjk < latin // 2:
        return "en"
    # 日文假名
    kana = sum(1 for c in text if "\u3040" <= c <= "\u30ff")
    if kana > 3:
        return "ja"
    # 韩文
    hangul = sum(1 for c in text if "\uac00" <= c <= "\ud7af")
    if hangul > 3:
        return "ko"
    return None


class TranslationSkill(BaseSkill):
    """翻译外文：自动检测语言并提供翻译。"""

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
    def icon(self) -> str:
        return "🔤"

    @property
    def action_label(self) -> str:
        return "翻译"

    @property
    def mode(self) -> str:
        return "suggest"

    async def suggest(self, message: str, params: dict[str, Any]) -> SkillResult:
        # 自动检测语言
        lang = params.get("source_lang") or _detect_foreign_language(message)
        if lang:
            lang_label = {"en": "英文", "ja": "日文", "ko": "韩文"}.get(lang, "外文")
            content = f"检测到你输入了{lang_label}，需要我帮你翻译成中文吗？"
        else:
            content = "需要我帮你翻译吗？"

        return SkillResult(
            intent=self.name,
            mode=self.mode,
            content=content,
            icon=self.icon,
            action_label=self.action_label,
            params={**params, "text": message, "source_lang": lang, "target_lang": "zh"},
            data={"todo": "接入翻译 API 或 LLM 翻译"},
        )
