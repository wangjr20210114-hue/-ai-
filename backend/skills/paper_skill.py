"""Academic paper search and introduction skill."""
from __future__ import annotations

import re
from typing import Any, AsyncIterator

from agent.cancellation import CancellationToken
from agent.contracts import FailurePolicy, PermissionLevel, RiskLevel, SkillParameter, SkillSchema
from config import settings
from services.model_gateway import CallContext, ModelGateway, ModelRequest
from services.paper_search_service import PaperSearchService
from skills.base_skill import BaseSkill, SkillResult, SkillStreamEvent


class PaperSkill(BaseSkill):
    def __init__(self, gateway: ModelGateway | None = None) -> None:
        self.gateway = gateway
        self.search_service = PaperSearchService(gateway)

    @property
    def name(self) -> str:
        return "paper"

    @property
    def description(self) -> str:
        return "科研论文搜索与助读，支持按主题、标题、作者或年份搜索 arXiv 论文并生成来源可追踪的介绍"

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
    def streaming(self) -> bool:
        return True

    @property
    def failure_policy(self) -> FailurePolicy:
        return FailurePolicy(max_retries=1, retry_backoff_seconds=0.3, user_visible=True)

    @property
    def planner_steps(self) -> list[str]:
        return ["parse_academic_query", "search_arxiv", "translate_abstracts", "summarize_papers", "persist_response"]

    @staticmethod
    def _topic(message: str, params: dict[str, Any]) -> str:
        topic = str(params.get("topic") or "").strip()
        if topic:
            return topic
        return re.sub(
            r"(帮我|我想|我想看|我想读|帮我找|搜索|查一下|看看|读一下|这篇|一些|相关|的|关于|请问)",
            "",
            message,
        ).strip() or message

    async def suggest(self, message: str, params: dict[str, Any]) -> SkillResult:
        topic = self._topic(message, params)
        return SkillResult(
            intent=self.name,
            mode=self.mode,
            content=f"正在搜索关于「{topic}」的论文。",
            icon=self.icon,
            action_label=self.action_label,
            params={**params, "topic": topic, "message": message},
            data={"topic": topic},
        )

    async def stream(
        self,
        message: str,
        params: dict[str, Any],
        session_id: str,
        history: list[str],
        *,
        run_id: str,
        cancellation: CancellationToken | None = None,
    ) -> AsyncIterator[SkillStreamEvent]:
        del history
        topic = self._topic(message, params)
        yield SkillStreamEvent(
            event_type="paper_status",
            data={"status": "searching", "topic": topic},
        )
        search_result = await self.search_service.search(
            topic=topic,
            user_message=message,
            max_results=params.get("max_results"),
            year_from=params.get("year_from"),
            run_id=run_id,
            conversation_id=session_id,
        )
        papers = list(search_result.get("papers") or [])
        if not papers:
            content = f"没有找到关于「{topic}」的 arXiv 论文。可以尝试更具体的英文关键词、作者名或研究方向。"
            yield SkillStreamEvent(delta=content)
            yield SkillStreamEvent(done=True, content=content, data={**search_result, "papers": []})
            return
        if self.gateway is None:
            raise RuntimeError("PaperSkill requires ModelGateway in execution runtime")

        summaries = "\n\n".join(
            f"- {paper.get('title', '')} ({paper.get('year', '')}, arXiv:{paper.get('arxiv_id', '')})\n"
            f"  作者：{paper.get('authors', '')}\n"
            f"  摘要：{paper.get('abstract_zh', '')}\n"
            f"  核心贡献：{paper.get('key_contribution', '')}"
            for paper in papers
        )
        yield SkillStreamEvent(
            event_type="paper_status",
            data={"status": "summarizing", "papers": papers},
        )
        full_text = ""
        async for chunk in self.gateway.stream_text(
            ModelRequest(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "你是严谨的学术助手。基于系统提供的真实论文信息，介绍最值得阅读的论文、"
                            "它们之间的关系和适合的阅读顺序。不要编造引用量或实验结果；使用 Markdown；"
                            "不要重复完整论文列表，列表由界面单独展示。"
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"用户主题：{topic}\n\n论文结果：\n{summaries}",
                    },
                ],
                provider="deepseek",
                model=settings.deepseek_model,
                max_tokens=1800,
                temperature=0.4,
                operation="paper_search_summary",
            ),
            CallContext(run_id=run_id, conversation_id=session_id, skill_name=self.name),
            cancellation,
        ):
            if chunk.delta:
                full_text += chunk.delta
                yield SkillStreamEvent(delta=chunk.delta)
            if chunk.done:
                yield SkillStreamEvent(
                    done=True,
                    content=full_text,
                    data={
                        **search_result,
                        "papers": papers,
                        "provider": chunk.provider,
                        "model": chunk.model,
                    },
                    usage=chunk.usage.to_dict(),
                    provider_request_id=chunk.provider_request_id,
                )
