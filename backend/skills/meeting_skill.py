"""腾讯会议创建技能。"""
from __future__ import annotations

from typing import Any

from skills.base_skill import BaseSkill, SkillResult


class MeetingSkill(BaseSkill):
    """创建腾讯会议：自动提取主题、时间、时长。"""

    @property
    def name(self) -> str:
        return "meeting"

    @property
    def description(self) -> str:
        return "创建腾讯会议（自动提取会议时间、主题）。用户提到开会、会议、碰头、评审、约会议等"

    @property
    def trigger_keywords(self) -> list[str]:
        return ["开会", "会议", "碰头", "评审", "约个会", "拉个会"]

    @property
    def icon(self) -> str:
        return "📅"

    @property
    def action_label(self) -> str:
        return "创建腾讯会议"

    @property
    def mode(self) -> str:
        return "suggest"  # 需用户确认后才创建

    async def suggest(self, message: str, params: dict[str, Any]) -> SkillResult:
        subject = params.get("subject", "")
        time_str = params.get("start_time", "")
        prompt_parts = ["检测到你想创建会议"]
        if subject:
            prompt_parts.append(f"「{subject}」")
        if time_str:
            prompt_parts.append(f"，时间 {time_str}")
        prompt_parts.append("。需要我帮你创建腾讯会议吗？")
        prompt = "".join(prompt_parts)

        return SkillResult(
            intent=self.name,
            mode=self.mode,
            content=prompt,
            icon=self.icon,
            action_label=self.action_label,
            params={**params, "message": message},
        )
