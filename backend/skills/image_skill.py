"""Image generation skill."""
from __future__ import annotations

from typing import Any

from agent.contracts import ConfirmationPolicy, FailurePolicy, PermissionLevel, RiskLevel, SkillParameter, SkillSchema
from skills.base_skill import BaseSkill, SkillResult


class ImageSkill(BaseSkill):
    @property
    def name(self) -> str:
        return "image"

    @property
    def description(self) -> str:
        return "生成图片（混元文生图）。用户想生成图片、画图、AI作画"

    @property
    def trigger_keywords(self) -> list[str]:
        return ["画", "生成图片", "生图", "作画", "画一张", "画个", "帮我画"]

    @property
    def schema(self) -> SkillSchema:
        return SkillSchema(
            intent=self.name,
            description=self.description,
            parameters=[SkillParameter("prompt", "string", "图片生成提示词", True)],
            examples=["帮我画一张赛博朋克城市", "生成一张旅游海报"],
            output_modes=["confirmation_card", "image"],
        )

    @property
    def icon(self) -> str:
        return "🎨"

    @property
    def action_label(self) -> str:
        return "生成图片"

    @property
    def mode(self) -> str:
        return "suggest"

    @property
    def permission_level(self) -> PermissionLevel:
        return PermissionLevel.CONFIRM

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.MEDIUM

    @property
    def confirmation_policy(self) -> ConfirmationPolicy:
        return ConfirmationPolicy(required=True, reason="生图会消耗独立额度", action_label=self.action_label, reversible=False)

    @property
    def failure_policy(self) -> FailurePolicy:
        return FailurePolicy(max_retries=0, user_visible=True)

    @property
    def planner_steps(self) -> list[str]:
        return ["extract_image_prompt", "ask_confirmation", "generate_image", "render_image"]

    async def suggest(self, message: str, params: dict[str, Any]) -> SkillResult:
        prompt = params.get("prompt", message)
        return SkillResult(
            intent=self.name,
            mode=self.mode,
            content=f"需要我帮你生成一张「{prompt[:30]}...」的图片吗？",
            icon=self.icon,
            action_label=self.action_label,
            params={**params, "prompt": prompt},
            data={},
        )

    async def handle(self, message: str, params: dict[str, Any], session_id: str) -> SkillResult:
        prompt = params.get("prompt", message)
        from services.hunyuan_service import ApiNotConfiguredError, hunyuan_service
        try:
            image_url = await hunyuan_service.text_to_image(prompt)
            return SkillResult(
                intent=self.name,
                mode="immediate",
                content=f"已为你生成图片：\n\n![生成的图片]({image_url})",
                icon=self.icon,
                action_label=self.action_label,
                params={**params, "prompt": prompt},
                data={"image_url": image_url},
            )
        except ApiNotConfiguredError as e:
            return SkillResult(intent=self.name, mode="immediate", content=f"❌ {str(e)}", icon=self.icon, action_label=self.action_label, params=params)
        except Exception as e:
            return SkillResult(intent=self.name, mode="immediate", content=f"❌ 生图失败：{type(e).__name__}: {e}", icon=self.icon, action_label=self.action_label, params=params)