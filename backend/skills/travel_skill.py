"""Travel planning skill."""
from __future__ import annotations

from typing import Any

from agent.contracts import FailurePolicy, PermissionLevel, RiskLevel, SkillParameter, SkillSchema
from skills.base_skill import BaseSkill, SkillResult


class TravelSkill(BaseSkill):
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
    def schema(self) -> SkillSchema:
        return SkillSchema(
            intent=self.name,
            description=self.description,
            parameters=[
                SkillParameter("destination", "string", "目的地城市", False),
                SkillParameter("departure", "string", "出发城市", False),
                SkillParameter("start_date", "date", "出发日期 YYYY-MM-DD", False),
                SkillParameter("end_date", "date", "结束日期 YYYY-MM-DD", False),
                SkillParameter("days", "integer", "旅行天数", False),
                SkillParameter("travel_style", "string", "旅行风格", False),
                SkillParameter("scenery_preference", "string", "景色/体验偏好", False),
            ],
            examples=["我想下周去杭州玩三天", "帮我规划北京到西安的亲子游"],
            output_modes=["suggestion", "guided_form", "schedule"],
        )

    @property
    def icon(self) -> str:
        return "✈️"

    @property
    def action_label(self) -> str:
        return "规划行程"

    @property
    def mode(self) -> str:
        return "auto"

    @property
    def permission_level(self) -> PermissionLevel:
        return PermissionLevel.SUGGEST

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.MEDIUM

    @property
    def failure_policy(self) -> FailurePolicy:
        return FailurePolicy(max_retries=1, retry_backoff_seconds=0.2, user_visible=True)

    @property
    def planner_steps(self) -> list[str]:
        return ["collect_travel_slots", "generate_plan", "parse_schedule", "respond_with_assistant"]

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