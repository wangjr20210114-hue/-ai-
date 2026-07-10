"""Academic paper assistant skill."""
from __future__ import annotations

import re
from typing import Any

from agent.contracts import FailurePolicy, PermissionLevel, RiskLevel, SkillParameter, SkillSchema
from skills.base_skill import BaseSkill, SkillResult


class PaperSkill(BaseSkill):
    @property
    def name(self) -> str:
        return "paper"

    @property
    def description(self) -> str:
        return "科研论文搜索与助读。支持推荐论文、自动下载、选词翻译、段落总结、全文分析、术语提取、论文问答"

    @property
    def trigger_keywords(self) -> list[str]:
        return ["论文", "文献", "arXiv", "arxiv", "学术", "paper", "读懂", "论文阅读", "找论文", "最新研究"]

    @property
    def schema(self) -> SkillSchema:
        return SkillSchema(
            intent=self.name,
            description=self.description,
            parameters=[
                SkillParameter("topic", "string", "论文主题、标题、作者或研究方向", True),
                SkillParameter("max_results", "integer", "返回论文数量", False, 5),
                SkillParameter("year_from", "integer", "起始年份", False),
            ],
            examples=["找 Transformer 经典论文", "帮我读 attention is all you need"],
            output_modes=["stream", "paper_list", "reader"],
        )

    @property
    def icon(self) -> str:
        return "📄"

    @property
    def action_label(self) -> str:
        return "搜索论文"

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
    def failure_policy(self) -> FailurePolicy:
        return FailurePolicy(max_retries=1, retry_backoff_seconds=0.3, user_visible=True)

    @property
    def planner_steps(self) -> list[str]:
        return ["parse_academic_query", "search_arxiv", "summarize_papers", "render_reader_actions"]

    async def suggest(self, message: str, params: dict[str, Any]) -> SkillResult:
        topic = params.get("topic", "")
        if not topic:
            topic = re.sub(r'(帮我|我想|我想看|我想读|帮我找|搜索|查一下|看看|读一下|这篇|一些|相关|的|关于|请问)', '', message).strip() or message
        return SkillResult(
            intent=self.name,
            mode=self.mode,
            content=f"我来帮你找关于「{topic}」的论文 📄\n\n正在搜索相关论文...",
            icon=self.icon,
            action_label=self.action_label,
            params={**params, "topic": topic, "message": message},
            data={"topic": topic},
        )