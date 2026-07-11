"""Tencent Meeting side-effect skill."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ValidationError

from agent.contracts import ConfirmationPolicy, FailurePolicy, PermissionLevel, RiskLevel, SkillParameter, SkillSchema
from skills.action_models import MeetingActionInput
from skills.base_skill import (
    ActionInputError,
    BaseSkill,
    SkillExecutionContext,
    SkillExecutionResult,
    SkillResult,
)

LOCAL_TZ = ZoneInfo("Asia/Shanghai")


class MeetingSkill(BaseSkill):
    @property
    def name(self) -> str:
        return "meeting"

    @property
    def description(self) -> str:
        return "创建腾讯会议（提取会议时间、主题，并在用户确认后执行）"

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
    def side_effect(self) -> bool:
        return True

    @property
    def action_input_model(self) -> type[BaseModel]:
        return MeetingActionInput

    @property
    def confirmation_policy(self) -> ConfirmationPolicy:
        return ConfirmationPolicy(
            required=True,
            reason="创建会议会调用外部服务并产生真实会议链接",
            action_label=self.action_label,
            reversible=False,
        )

    @property
    def failure_policy(self) -> FailurePolicy:
        # Unknown external results must be reconciled, so automatic retry is disabled.
        return FailurePolicy(max_retries=0, user_visible=True)

    @property
    def planner_steps(self) -> list[str]:
        return ["validate_meeting_input", "persist_confirmation_snapshot", "create_meeting", "notify_result"]

    async def prepare_action_input(self, message: str, params: dict[str, Any]) -> MeetingActionInput:
        start_raw = str(params.get("start_time") or "").strip()
        if not start_raw:
            raise ActionInputError("创建会议前需要明确开始时间，请补充具体日期和时间")
        try:
            start = datetime.fromisoformat(start_raw.replace("Z", "+00:00"))
        except ValueError as error:
            raise ActionInputError("会议开始时间格式无效，请使用明确日期和时间") from error
        if start.tzinfo is None:
            start = start.replace(tzinfo=LOCAL_TZ)
        duration = int(params.get("duration_minutes") or 60)
        subject = str(params.get("subject") or "快速会议").strip() or "快速会议"
        try:
            return MeetingActionInput(
                subject=subject,
                start_time=start,
                end_time=start + timedelta(minutes=duration),
                duration_minutes=duration,
            )
        except (ValidationError, ValueError) as error:
            raise ActionInputError(str(error)) from error

    async def suggest(self, message: str, params: dict[str, Any]) -> SkillResult:
        subject = params.get("subject", "快速会议")
        time_str = params.get("start_time", "")
        return SkillResult(
            intent=self.name,
            mode=self.mode,
            content=f"准备创建腾讯会议「{subject}」，开始时间 {time_str}。确认后将严格按此参数执行。",
            icon=self.icon,
            action_label=self.action_label,
            params={},
        )

    async def execute_action(
        self,
        input_model: BaseModel,
        context: SkillExecutionContext,
    ) -> SkillExecutionResult:
        action = MeetingActionInput.model_validate(input_model)
        from services.meeting_service import meeting_service

        result = await meeting_service.create_meeting(
            action.subject,
            action.start_time.isoformat(),
            action.end_time.isoformat(),
        )
        if not result.get("ok"):
            raise RuntimeError(result.get("error") or "腾讯会议创建失败")
        meeting_id = str(result.get("meeting_id") or result.get("meeting_code") or "")
        join_url = str(result.get("join_url") or "")
        content = f"腾讯会议「{action.subject}」创建成功。"
        if join_url:
            content += f"\n\n[加入会议]({join_url})"
        return SkillExecutionResult(
            content=content,
            data={**result, "idempotency_key": context.idempotency_key},
            provider_request_id=meeting_id,
        )
