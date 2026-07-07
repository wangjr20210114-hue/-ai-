"""技能基类、结果模型、注册表。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SkillResult:
    """技能执行结果 — 统一格式，前端据此渲染不同卡片。

    Attributes:
        intent:       技能标识（travel / meeting / news / image / translation / paper）
        mode:         执行模式
                      - "auto"：前端自动展开（如旅游助手直接弹出问答）
                      - "suggest"：显示建议卡片 + 确认按钮（如创建会议前需确认）
                      - "immediate"：直接返回结果文本（如翻译结果）
        content:      Markdown 文本（建议话术或直接结果）
        icon:         前端图标 emoji
        action_label: 确认按钮文案（suggest 模式）
        params:       LLM 提取的参数（传递给前端 / REST API）
        data:         技能额外数据（前端渲染用）
    """
    intent: str
    mode: str = "suggest"
    content: str = ""
    icon: str = "✨"
    action_label: str = "执行"
    params: dict[str, Any] = field(default_factory=dict)
    data: dict[str, Any] = field(default_factory=dict)


class BaseSkill(ABC):
    """所有技能的基类。子类需实现 name / description / trigger_keywords / suggest。"""

    @property
    @abstractmethod
    def name(self) -> str:
        """技能标识（如 'travel', 'meeting'）。"""

    @property
    @abstractmethod
    def description(self) -> str:
        """技能描述（用于 LLM 意图分类提示词）。"""

    @property
    @abstractmethod
    def trigger_keywords(self) -> list[str]:
        """触发关键词（用于快速正则预检，节省 LLM 调用）。"""

    @property
    def icon(self) -> str:
        """前端图标 emoji。"""
        return "✨"

    @property
    def action_label(self) -> str:
        """确认按钮文案。"""
        return "执行"

    @property
    def mode(self) -> str:
        """执行模式：'auto' / 'suggest' / 'immediate'。"""
        return "suggest"

    @abstractmethod
    async def suggest(self, message: str, params: dict[str, Any]) -> SkillResult:
        """生成建议或直接执行，返回 SkillResult。"""

    async def handle(self, message: str, params: dict[str, Any], session_id: str) -> SkillResult:
        """REST API 调用时的执行入口（默认同 suggest）。"""
        return await self.suggest(message, params)


class SkillRegistry:
    """技能注册表 — 管理所有已注册技能，提供查询和关键词预检。"""

    def __init__(self) -> None:
        self._skills: dict[str, BaseSkill] = {}

    def register(self, skill: BaseSkill) -> None:
        self._skills[skill.name] = skill

    def get(self, name: str) -> BaseSkill | None:
        return self._skills.get(name)

    def all_skills(self) -> list[BaseSkill]:
        return list(self._skills.values())

    def keyword_check(self, text: str) -> str | None:
        """快速关键词预检，返回第一个匹配的技能名。"""
        for skill in self._skills.values():
            for kw in skill.trigger_keywords:
                if kw in text:
                    return skill.name
        return None

    def build_llm_description(self) -> str:
        """生成 LLM 意图分类提示词中的技能列表。"""
        lines = []
        for skill in self._skills.values():
            lines.append(f"- **{skill.name}**: {skill.description}")
        return "\n".join(lines)


# 全局单例
skill_registry = SkillRegistry()
