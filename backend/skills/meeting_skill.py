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
        return "创建腾讯会议（提取会议时间、主题并直接创建）"

    @property
    def trigger_keywords(self) -> list[str]:
        return ["开会", "会议", "碰头", "评审", "约个会", "拉个会", "改到", "改一下会议", "重新预约", "调整会议", "推迟会议"]

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
        return "auto"

    @property
    def permission_level(self) -> PermissionLevel:
        return PermissionLevel.AUTO

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.HIGH

    @property
    def side_effect(self) -> bool:
        return False  # Meeting creation is handled directly in suggest() for natural UX

    @property
    def action_input_model(self) -> type[BaseModel]:
        return MeetingActionInput

    @property
    def confirmation_policy(self) -> ConfirmationPolicy:
        return ConfirmationPolicy(
            required=False,
            reason="",
            action_label=self.action_label,
            reversible=True,
        )

    @property
    def failure_policy(self) -> FailurePolicy:
        return FailurePolicy(max_retries=0, user_visible=True)

    @property
    def planner_steps(self) -> list[str]:
        return ["parse_meeting_params", "create_meeting", "respond_with_result"]

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
        """Create or update meeting based on user intent."""
        start_raw = str(params.get("start_time") or "").strip()
        subject = str(params.get("subject") or "").strip() or "快速会议"
        duration = int(params.get("duration_minutes") or 60)

        # Detect reschedule intent
        reschedule_keywords = ["改到", "改一下", "重新预约", "调整", "推迟", "移到", "换到"]
        is_reschedule = any(kw in message for kw in reschedule_keywords)

        # If no start time, ask naturally
        if not start_raw:
            if is_reschedule:
                return SkillResult(
                    intent=self.name, mode="immediate",
                    content="好的，你想改到什么时间？告诉我新的日期和时间就行，比如「明天下午3点」 😊",
                    icon=self.icon, action_label=self.action_label,
                    params={**params, "user_message": message},
                    data={"need_time": True, "is_reschedule": True},
                )
            return SkillResult(
                intent=self.name,
                mode="immediate",
                content="好的，你想什么时候开会？告诉我具体日期和时间就行，比如「明天下午3点」 😊",
                icon=self.icon,
                action_label=self.action_label,
                params={**params, "user_message": message},
                data={"need_time": True},
            )

        # Parse time
        try:
            start = datetime.fromisoformat(start_raw.replace("Z", "+00:00"))
        except ValueError:
            return SkillResult(
                intent=self.name,
                mode="immediate",
                content=f'我没理解对时间「{start_raw}」，能再说一次吗？比如「7月13日下午3点」 😊',
                icon=self.icon,
                action_label=self.action_label,
                params={**params, "user_message": message},
                data={"time_parse_error": True},
            )

        if start.tzinfo is None:
            start = start.replace(tzinfo=LOCAL_TZ)
        end = start + timedelta(minutes=duration)
        time_desc = start.strftime("%m月%d日 %H:%M")

        # Reschedule: find and update existing meeting
        if is_reschedule:
            try:
                from services.meeting_service import meeting_service
                list_result = await meeting_service.list_meetings()
                if list_result.get("ok") and list_result.get("meetings"):
                    meetings = list_result["meetings"]
                    target = None
                    if subject and subject != "快速会议":
                        for m in meetings:
                            m_subject = str(m.get("subject") or m.get("meeting_subject") or "")
                            if subject in m_subject or m_subject in subject:
                                target = m
                                break
                    if target is None and meetings:
                        target = meetings[0]
                    if target:
                        meeting_id = str(target.get("meeting_id") or target.get("meetingId") or "")
                        if meeting_id:
                            update_result = await meeting_service.update_meeting(
                                meeting_id,
                                subject=subject if subject != "快速会议" else None,
                                start_iso=start.isoformat(),
                                end_iso=end.isoformat(),
                            )
                            if update_result.get("ok"):
                                content = f"已将会议改到 {time_desc}。\n\n会议号：{target.get('meeting_code', '')}"
                                join_url = str(target.get("join_url") or "")
                                if join_url:
                                    content += f"\n\n[点击加入会议]({join_url})"
                                return SkillResult(
                                    intent=self.name, mode="immediate", content=content,
                                    icon=self.icon, action_label=self.action_label,
                                    params={**params, "user_message": message},
                                    data={"meeting_id": meeting_id, "is_reschedule": True, "follow_ups": await self.generate_follow_ups(message, content)},
                                )
                            else:
                                error = update_result.get("error", "修改失败")
                                return SkillResult(
                                    intent=self.name, mode="immediate",
                                    content=f"修改会议时出了问题：{error}",
                                    icon=self.icon, action_label=self.action_label,
                                    params={**params, "user_message": message},
                                    data={"error": error},
                                )
            except Exception:
                pass  # Fall through to create new meeting

        # Create new meeting
        try:
            from services.meeting_service import meeting_service
            result = await meeting_service.create_meeting(
                subject,
                start.isoformat(),
                end.isoformat(),
            )
        except Exception as e:
            return SkillResult(
                intent=self.name,
                mode="immediate",
                content=f"创建会议时出了点问题：{type(e).__name__}: {e}",
                icon=self.icon,
                action_label=self.action_label,
                params={**params, "user_message": message},
                data={"error": str(e)},
            )

        if result.get("ok"):
            meeting_code = result.get("meeting_code", "")
            join_url = result.get("join_url", "")
            content = f"已创建腾讯会议「{subject}」，时间是 {time_desc}。\n\n"
            if meeting_code:
                content += f"会议号：{meeting_code}\n"
            if join_url:
                content += f"\n[点击加入会议]({join_url})"
            return SkillResult(
                intent=self.name,
                mode="immediate",
                content=content,
                icon=self.icon,
                action_label=self.action_label,
                params={**params, "user_message": message},
                data={"meeting_code": meeting_code, "join_url": join_url, "subject": subject, "follow_ups": await self.generate_follow_ups(message, content)},
            )
        else:
            error = result.get("error", "创建失败")
            need_auth = result.get("need_auth", False)
            if need_auth:
                content = f"腾讯会议还没授权，请在终端运行 `tmeet auth login` 完成授权后重试。"
            else:
                content = f"创建会议失败了：{error}"
            return SkillResult(
                intent=self.name,
                mode="immediate",
                content=content,
                icon=self.icon,
                action_label=self.action_label,
                params={**params, "user_message": message},
                data={"error": error, "need_auth": need_auth},
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
