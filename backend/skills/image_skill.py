"""AI 生图技能（占位实现，后续接入混元文生图 API）。"""
from __future__ import annotations

from typing import Any

from skills.base_skill import BaseSkill, SkillResult


class ImageSkill(BaseSkill):
    """调用混元生图能力，给用户图文并茂的回答。"""

    @property
    def name(self) -> str:
        return "image"

    @property
    def description(self) -> str:
        return "生成图片（混元文生图）。用户想生成图片、画图、AI作画"

    @property
    def trigger_keywords(self) -> list[str]:
        return ["画", "生成图片", "生图", "作画", "画一张"]

    @property
    def icon(self) -> str:
        return "🎨"

    @property
    def action_label(self) -> str:
        return "生成图片"

    @property
    def mode(self) -> str:
        return "suggest"

    async def suggest(self, message: str, params: dict[str, Any]) -> SkillResult:
        prompt = params.get("prompt", message)
        return SkillResult(
            intent=self.name,
            mode=self.mode,
            content=f"需要我帮你生成一张「{prompt[:20]}...」的图片吗？",
            icon=self.icon,
            action_label=self.action_label,
            params={**params, "prompt": prompt},
            data={"todo": "接入混元文生图 API"},
        )
