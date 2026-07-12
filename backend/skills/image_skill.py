"""Image generation side-effect skill."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ValidationError

from agent.contracts import ConfirmationPolicy, FailurePolicy, PermissionLevel, RiskLevel, SkillParameter, SkillSchema
from skills.action_models import ImageActionInput
from skills.base_skill import (
    ActionInputError,
    BaseSkill,
    SkillExecutionContext,
    SkillExecutionResult,
    SkillResult,
)


class ImageSkill(BaseSkill):
    @property
    def name(self) -> str:
        return "image"

    @property
    def description(self) -> str:
        return "生成图片（混元文生图，直接执行）"

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
            output_modes=["image"],
        )

    @property
    def icon(self) -> str:
        return "🎨"

    @property
    def action_label(self) -> str:
        return "生成图片"

    @property
    def mode(self) -> str:
        return "auto"

    @property
    def permission_level(self) -> PermissionLevel:
        return PermissionLevel.AUTO

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.MEDIUM

    @property
    def side_effect(self) -> bool:
        return False

    @property
    def action_input_model(self) -> type[BaseModel]:
        return ImageActionInput

    def estimated_cost_cny(self, input_model: BaseModel) -> float:
        del input_model
        from config import settings
        return max(0.0, settings.image_generation_estimated_cost_cny)

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
        return ["generate_image", "persist_result"]

    async def prepare_action_input(self, message: str, params: dict[str, Any]) -> ImageActionInput:
        prompt = str(params.get("prompt") or message).strip()
        try:
            return ImageActionInput(prompt=prompt)
        except ValidationError as error:
            raise ActionInputError("生图提示词不能为空，且不能超过 4000 字") from error

    async def suggest(self, message: str, params: dict[str, Any]) -> SkillResult:
        """Directly generate image — no confirmation card."""
        prompt = str(params.get("prompt") or message).strip()
        if not prompt:
            prompt = message.strip()
        try:
            from services.hunyuan_service import hunyuan_service
            image_url = await hunyuan_service.text_to_image(prompt)
        except Exception as e:
            return SkillResult(
                intent=self.name,
                mode="immediate",
                content=f"抱歉，生图失败了：{type(e).__name__}: {e}",
                icon=self.icon,
                action_label=self.action_label,
                params={**params, "prompt": prompt},
                data={"error": str(e)},
            )
        if not image_url:
            return SkillResult(
                intent=self.name,
                mode="immediate",
                content="抱歉，生图服务没有返回图片，请稍后重试。",
                icon=self.icon,
                action_label=self.action_label,
                params={**params, "prompt": prompt},
                data={"error": "empty_url"},
            )
        return SkillResult(
            intent=self.name,
            mode="immediate",
            content=f"已为你生成图片 🎨\n\n![{prompt}]({image_url})",
            icon=self.icon,
            action_label=self.action_label,
            params={**params, "prompt": prompt},
            data={"image_url": image_url, "prompt": prompt, "follow_ups": await self.generate_follow_ups(message, f"已生成图片: {prompt}")},
        )

    async def execute_action(
        self,
        input_model: BaseModel,
        context: SkillExecutionContext,
    ) -> SkillExecutionResult:
        action = ImageActionInput.model_validate(input_model)
        from services.hunyuan_service import hunyuan_service

        image_url = await hunyuan_service.text_to_image(action.prompt)
        if not image_url:
            raise RuntimeError("生图服务没有返回图片地址")
        return SkillExecutionResult(
            content=f"图片生成成功：\n\n![生成的图片]({image_url})",
            data={
                "image_url": image_url,
                "prompt": action.prompt,
                "idempotency_key": context.idempotency_key,
            },
            provider_request_id=image_url,
            usage={"image_generations": 1},
        )
