"""新闻搜索技能（占位实现，后续接入腾讯新闻/公众号搜索 API）。"""
from __future__ import annotations

from typing import Any

from skills.base_skill import BaseSkill, SkillResult


class NewsSkill(BaseSkill):
    """搜索新闻/公众号文章。"""

    @property
    def name(self) -> str:
        return "news"

    @property
    def description(self) -> str:
        return "搜索新闻和公众号文章。用户想了解最新资讯、新闻、热点事件"

    @property
    def trigger_keywords(self) -> list[str]:
        return ["新闻", "资讯", "热搜", "热点"]

    @property
    def icon(self) -> str:
        return "📰"

    @property
    def action_label(self) -> str:
        return "搜索新闻"

    @property
    def mode(self) -> str:
        return "suggest"

    async def suggest(self, message: str, params: dict[str, Any]) -> SkillResult:
        query = params.get("query", message)
        return SkillResult(
            intent=self.name,
            mode=self.mode,
            content=f"需要我帮你搜索关于「{query}」的最新新闻吗？",
            icon=self.icon,
            action_label=self.action_label,
            params={**params, "query": query},
            data={"todo": "接入腾讯新闻/公众号搜索 API"},
        )
