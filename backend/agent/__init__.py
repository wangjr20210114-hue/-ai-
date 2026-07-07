"""Agent 包：注册所有技能到全局注册表。"""
from __future__ import annotations

from skills.base_skill import SkillRegistry
from skills.travel_skill import TravelSkill
from skills.meeting_skill import MeetingSkill
from skills.news_skill import NewsSkill
from skills.image_skill import ImageSkill
from skills.translation_skill import TranslationSkill
from skills.paper_skill import PaperSkill


def register_all_skills(registry: SkillRegistry) -> None:
    """注册所有技能到注册表。新增能力只需在这里注册。"""
    registry.register(TravelSkill())
    registry.register(MeetingSkill())
    registry.register(NewsSkill())
    registry.register(ImageSkill())
    registry.register(TranslationSkill())
    registry.register(PaperSkill())
