"""Agent capability composition helpers.

Imports are intentionally lazy so low-level modules such as ``agent.errors`` can
be imported by provider gateways without initializing every Skill and creating a
package cycle.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from services.model_gateway import ModelGateway
    from skills.base_skill import SkillRegistry


def register_all_skills(
    registry: "SkillRegistry",
    *,
    model_gateway: "ModelGateway | None" = None,
) -> None:
    """Register all capabilities in the application composition root."""
    from skills.chat_skill import ChatSkill
    from skills.image_skill import ImageSkill
    from skills.meeting_skill import MeetingSkill
    from skills.paper_skill import PaperSkill
    from skills.search_skill import SearchSkill
    from skills.translation_skill import TranslationSkill
    from skills.travel_skill import TravelSkill

    registry.register(ChatSkill(model_gateway))
    registry.register(TravelSkill())
    registry.register(MeetingSkill())
    registry.register(SearchSkill(model_gateway))
    registry.register(ImageSkill())
    registry.register(TranslationSkill(model_gateway))
    registry.register(PaperSkill(model_gateway))
