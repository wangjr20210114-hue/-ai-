"""旅游规划技能。"""
from __future__ import annotations

from typing import Any

from skills.base_skill import BaseSkill, SkillResult


class TravelSkill(BaseSkill):
    """旅游规划：路线规划、景点推荐、费用估算。"""

    @property
    def name(self) -> str:
        return "travel"

    @property
    def description(self) -> str:
        return "旅游规划（路线、景点、酒店、费用估算）。用户提到旅游、旅行、游玩、行程、景点、攻略等"

    @property
    def trigger_keywords(self) -> list[str]:
        return ["旅游", "旅行", "游玩", "行程", "攻略", "景点", "去玩"]

    @property
    def icon(self) -> str:
        return "✈️"

    @property
    def action_label(self) -> str:
        return "规划行程"

    @property
    def mode(self) -> str:
        return "auto"  # 前端自动展开 TravelChatAssistant

    async def suggest(self, message: str, params: dict[str, Any]) -> SkillResult:
        dest = params.get("destination", "")
        prompt = f"好呀！我来帮你规划{dest + '的' if dest else ''}旅游行程吧 😊"
        return SkillResult(
            intent=self.name,
            mode=self.mode,
            content=prompt,
            icon=self.icon,
            action_label=self.action_label,
            params={**params, "user_message": message},
            data={"destination": dest},
        )
