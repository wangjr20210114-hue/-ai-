"""Multi-source web search skill."""
from __future__ import annotations

from typing import Any, AsyncIterator

from agent.cancellation import CancellationToken
from agent.contracts import FailurePolicy, PermissionLevel, RiskLevel, SkillParameter, SkillSchema
from services.model_gateway import CallContext, ModelGateway
from services.search_service import prepare_search_prompt
from skills.base_skill import BaseSkill, SkillResult, SkillStreamEvent


class SearchSkill(BaseSkill):
    def __init__(self, gateway: ModelGateway | None = None) -> None:
        self.gateway = gateway

    @property
    def name(self) -> str:
        return "search"

    @property
    def description(self) -> str:
        return "多源搜索互联网信息（网页、微信公众号、知乎、百科、图片），并基于可追踪来源生成答案"

    @property
    def trigger_keywords(self) -> list[str]:
        return ["搜索", "搜一下", "查询", "查一下", "最新", "新闻", "今天", "现在", "最近", "公众号", "微信文章", "知乎", "百科", "帮我找", "有没有"]

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
    def streaming(self) -> bool:
        return True

    @property
    def failure_policy(self) -> FailurePolicy:
        return FailurePolicy(max_retries=1, retry_backoff_seconds=0.3, user_visible=True)

    @property
    def planner_steps(self) -> list[str]:
        return ["classify_search_need", "search_sources", "rank_results", "summarize_with_sources", "persist_response"]

    async def suggest(self, message: str, params: dict[str, Any]) -> SkillResult:
        query = str(params.get("query") or message)
        return SkillResult(
            intent=self.name,
            mode=self.mode,
            content="",
            icon=self.icon,
            action_label=self.action_label,
            params={**params, "query": query, "message": message},
            data={"query": query},
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
        query = str(params.get("query") or message).strip()
        if not query:
            raise ValueError("搜索词不能为空")
        yield SkillStreamEvent(
            event_type="search_status",
            data={"status": "searching", "query": query},
        )

        from services.search_system import search as system_search

        aggregated = await system_search(
            query,
            intent=str(params.get("search_type") or "general"),
            time_sensitive=bool(params.get("time_sensitive", False)),
            depth=str(params.get("depth") or "standard"),
        )
        results = list(aggregated.get("results") or [])
        images = list(aggregated.get("images") or [])
        image_descriptions = list(aggregated.get("image_descriptions") or [])
        sources_used = list(aggregated.get("sources_used") or [])

        if not results:
            content = "抱歉，没有找到可验证的相关搜索结果。"
            follow_ups = await self._generate_follow_ups(query, content)
            yield SkillStreamEvent(delta=content)
            yield SkillStreamEvent(
                done=True,
                content=content,
                data={
                    "query": query,
                    "search_results": {
                        "query": query,
                        "results": [],
                        "images": [],
                        "sources_used": sources_used,
                        "total": 0,
                    },
                    "follow_ups": follow_ups,
                },
            )
            return

        if self.gateway is None:
            raise RuntimeError("SearchSkill requires ModelGateway in execution runtime")
        request, search_meta = prepare_search_prompt(
            query,
            results,
            images,
            sources_used,
            image_descriptions,
        )
        yield SkillStreamEvent(
            event_type="search_status",
            data={"status": "thinking", "search_results": search_meta},
        )
        full_text = ""
        async for chunk in self.gateway.stream_text(
            request,
            CallContext(run_id=run_id, conversation_id=session_id, skill_name=self.name),
            cancellation,
        ):
            if chunk.delta:
                full_text += chunk.delta
                yield SkillStreamEvent(delta=chunk.delta)
            if chunk.done:
                follow_ups = await self._generate_follow_ups(query, full_text)
                yield SkillStreamEvent(
                    done=True,
                    content=full_text,
                    data={
                        "query": query,
                        "search_results": search_meta,
                        "provider": chunk.provider,
                        "model": chunk.model,
                        "follow_ups": follow_ups,
                    },
                    usage=chunk.usage.to_dict(),
                    provider_request_id=chunk.provider_request_id,
                )

    async def _generate_follow_ups(self, query: str, ai_content: str) -> list[str]:
        """Generate 3 follow-up questions."""
        try:
            import json as _json
            import httpx
            from config import settings
            messages = [
                {"role": "system", "content": "根据对话上下文，推测用户接下来可能想问的 3 个问题。简短（10字以内），自然口语。输出 JSON 数组 [\"问题1\",\"问题2\",\"问题3\"]"},
                {"role": "user", "content": f"用户搜索：{query}\n\nAI回答：{ai_content[:500]}"},
            ]
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{settings.deepseek_base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {settings.deepseek_api_key}"},
                    json={"model": settings.deepseek_model, "messages": messages, "max_tokens": 200, "temperature": 0.8},
                )
                resp.raise_for_status()
                content = resp.json()["choices"][0]["message"]["content"].strip().strip("`").strip()
                if content.startswith("json"):
                    content = content[4:].strip()
                result = _json.loads(content)
                if isinstance(result, list):
                    return [str(q) for q in result[:3]]
        except Exception:
            pass
        return []
