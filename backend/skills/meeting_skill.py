"""Tencent meeting creation skill."""
from __future__ import annotations

from typing import Any

from agent.contracts import ConfirmationPolicy, FailurePolicy, PermissionLevel, RiskLevel, SkillParameter, SkillSchema
from skills.base_skill import BaseSkill, SkillResult


class MeetingSkill(BaseSkill):
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
    def schema(self) -> SkillSchema:
        return SkillSchema(
            intent=self.name,
            description=self.description,
            parameters=[
                SkillParameter("subject", "string", "会议主题", False),
                SkillParameter("start_time", "datetime", "会议开始时间 ISO 8601", True),
                SkillParameter("duration_minutes", "integer", "会议时长分钟", False, 60),
            ],
            examples=["明天下午三点拉个需求评审会", "帮我约周五十点开会"],
            output_modes=["confirmation_card", "meeting_result"],
        )

    @property
    def icon(self) -> str:
        return "📅"

    @property
    def action_label(self) -> str:
        return "创建腾讯会议"

    @property
    def mode(self) -> str:
        return "suggest"

    @property
    def permission_level(self) -> PermissionLevel:
        return PermissionLevel.CONFIRM

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.HIGH

    @property
    def confirmation_policy(self) -> ConfirmationPolicy:
        return ConfirmationPolicy(
            required=True,
            reason="创建会议会调用外部服务并产生真实日程/会议链接",
            action_label=self.action_label,
            reversible=False,
        )

    @property
    def failure_policy(self) -> FailurePolicy:
        return FailurePolicy(max_retries=0, user_visible=True)

    @property
    def planner_steps(self) -> list[str]:
        return ["extract_meeting_slots", "ask_confirmation", "create_meeting", "respond_with_link"]

    async def suggest(self, message: str, params: dict[str, Any]) -> SkillResult:
        subject = params.get("subject", "")
        time_str = params.get("start_time", "")
        prompt_parts = ["检测到你想创建会议"]
        if subject:
            prompt_parts.append(f"「{subject}」")
        if time_str:
            prompt_parts.append(f"，时间 {time_str}")
        prompt_parts.append("。需要我帮你创建腾讯会议吗？")
        return SkillResult(
            intent=self.name,
            mode=self.mode,
            content="".join(prompt_parts),
            icon=self.icon,
            action_label=self.action_label,
            params={**params, "message": message},
        )