"""Web search skill."""
from __future__ import annotations

from typing import Any

from agent.contracts import FailurePolicy, PermissionLevel, RiskLevel, SkillParameter, SkillSchema
from skills.base_skill import BaseSkill, SkillResult


class SearchSkill(BaseSkill):
    @property
    def name(self) -> str:
        return "search"

    @property
    def description(self) -> str:
        return "多源搜索互联网信息（网页、微信公众号、知乎、百科、图片）。用户想搜索、查询、了解信息、找公众号文章、看知乎讨论时触发"

    @property
    def trigger_keywords(self) -> list[str]:
        return ["搜索", "搜一下", "查询", "查一下", "最新", "新闻", "今天", "现在", "最近", "公众号", "微信文章", "知乎", "百科", "是什么", "怎么回事", "帮我找", "有没有"]

    @property
    def schema(self) -> SkillSchema:
        return SkillSchema(
            intent=self.name,
            description=self.description,
            parameters=[
                SkillParameter("query", "string", "搜索查询词", True),
                SkillParameter("search_type", "string", "fact/recommend/discussion/news/general", False, "general", ["fact", "recommend", "discussion", "news", "general"]),
                SkillParameter("time_sensitive", "boolean", "是否需要最新信息", False, False),
                SkillParameter("depth", "string", "搜索深度", False, "standard", ["basic", "standard", "deep"]),
            ],
            examples=["搜一下最新 AI 新闻", "知乎上怎么评价某产品"],
            output_modes=["stream", "sources", "cards"],
        )

    @property
    def icon(self) -> str:
        return "🔍"

    @property
    def action_label(self) -> str:
        return "搜索"

    @property
    def mode(self) -> str:
        return "auto"

    @property
    def permission_level(self) -> PermissionLevel:
        return PermissionLevel.AUTO

    @property
    def risk_level(self) -> RiskLevel:
        return RiskLevel.LOW

    @property
    def failure_policy(self) -> FailurePolicy:
        return FailurePolicy(max_retries=1, retry_backoff_seconds=0.3, user_visible=True)

    @property
    def planner_steps(self) -> list[str]:
        return ["classify_search_need", "search_sources", "rank_results", "summarize_with_sources"]

    async def suggest(self, message: str, params: dict[str, Any]) -> SkillResult:
        query = params.get("query", message)
        return SkillResult(
            intent=self.name,
            mode=self.mode,
            content="",
            icon=self.icon,
            action_label=self.action_label,
            params={**params, "query": query, "message": message},
            data={"query": query},
        )