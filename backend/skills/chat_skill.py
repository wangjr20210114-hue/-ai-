"""General conversational skill backed by the unified model gateway."""
from __future__ import annotations

import json
from typing import Any, AsyncIterator

import httpx

from agent.cancellation import CancellationToken
from agent.contracts import FailurePolicy, PermissionLevel, RiskLevel, SkillSchema
from config import settings
from services.model_gateway import CallContext, ModelGateway, ModelRequest
from skills.base_skill import BaseSkill, SkillResult, SkillStreamEvent


def _history_messages(history: list[str], current_message: str) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    # Only use the last few turns of history to avoid context bleed
    for line in history[-12:]:
        line = line.strip()
        if not line:
            continue
        if line.startswith("用户: "):
            content = line[4:]
            # Skip the current user message — it's appended separately below
            if content == current_message:
                continue
            messages.append({"role": "user", "content": content})
        elif line.startswith("AI("):
            separator = line.find("): ")
            if separator > 0:
                messages.append({"role": "assistant", "content": line[separator + 3:]})
        elif line.startswith("AI: "):
            messages.append({"role": "assistant", "content": line[4:]})
    return messages


class ChatSkill(BaseSkill):
    def __init__(self, gateway: ModelGateway | None = None) -> None:
        self.gateway = gateway

    @property
    def name(self) -> str:
        return "chat"

    @property
    def description(self) -> str:
        return "处理不属于其他专用能力的普通对话、解释、建议与问答"

    @property
    def trigger_keywords(self) -> list[str]:
        return []

    @property
    def schema(self) -> SkillSchema:
        return SkillSchema(
            intent=self.name,
            description=self.description,
            examples=["你好", "解释一下这个概念", "给我一些建议"],
            output_modes=["stream", "markdown"],
        )

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
        return FailurePolicy(max_retries=1, retry_backoff_seconds=0.5, user_visible=True)

    @property
    def planner_steps(self) -> list[str]:
        return ["load_context", "generate_response", "persist_response"]

    async def suggest(self, message: str, params: dict[str, Any]) -> SkillResult:
        del message, params
        return SkillResult(intent=self.name, mode="auto", content="正在回答。")

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
        if self.gateway is None:
            raise RuntimeError("ChatSkill requires ModelGateway in execution runtime")

        # Check if web search is enabled (default: on)
        web_search_enabled = params.get("web_search", True)

        messages: list[dict[str, str]] = [
            {
                "role": "system",
                "content": (
                    "你是元宝主动式 Agent，一个智能助手。"
                    "用 Markdown 格式回复。"
                    "如果回答中涉及图片，可以将图片插入到合适的位置，使内容图文并茂。"
                    "如果用户的问题涉及旅游、会议等你能提供的服务，在回答中自然地引导用户使用。"
                ),
            },
            *_history_messages(history, message),
            {"role": "user", "content": message},
        ]

        # If web search is enabled, fetch search results and prepend context
        search_data: dict[str, Any] = {}
        if web_search_enabled and self._should_search(message):
            search_data = await self._web_search(message)
            if search_data.get("results"):
                messages.insert(1, {
                    "role": "system",
                    "content": f"以下是关于用户问题的网络搜索结果，可以参考这些信息回答：\n\n{search_data['context']}",
                })

        full_text = ""
        async for chunk in self.gateway.stream_text(
            ModelRequest(
                messages=messages,
                provider=settings.llm_provider,
                model=settings.llm_model,
                max_tokens=1800,
                temperature=0.7,
                operation="chat",
            ),
            CallContext(run_id=run_id, conversation_id=session_id, skill_name=self.name),
            cancellation,
        ):
            if chunk.delta:
                full_text += chunk.delta
                yield SkillStreamEvent(delta=chunk.delta)
            if chunk.done:
                # Generate follow-up questions
                follow_ups = await self._generate_follow_ups(message, full_text, history)
                data = {
                    "provider": chunk.provider,
                    "model": chunk.model,
                    "follow_ups": follow_ups,
                }
                if search_data.get("results"):
                    data["search_results"] = search_data["search_meta"]
                yield SkillStreamEvent(
                    done=True,
                    content=full_text,
                    data=data,
                    usage=chunk.usage.to_dict(),
                    provider_request_id=chunk.provider_request_id,
                )

    def _should_search(self, message: str) -> bool:
        """Determine if the message would benefit from web search."""
        # Don't search for very short/greeting messages
        if len(message) < 5:
            return False
        skip_keywords = ["你好", "你是谁", "谢谢", "再见", "帮我画", "生成图片"]
        return not any(kw in message for kw in skip_keywords)

    async def _web_search(self, query: str) -> dict[str, Any]:
        """Fetch web search results and build context for the LLM."""
        try:
            from services.search_system import search as system_search
            aggregated = await system_search(query, intent="general", time_sensitive=False, depth="basic")
            results = list(aggregated.get("results") or [])
            if not results:
                return {}
            # Build context text from top results
            context_parts = []
            for r in results[:5]:
                title = r.get("title", "")
                snippet = r.get("snippet", "")
                source = r.get("source", "")
                context_parts.append(f"[{source}] {title}: {snippet}")
            return {
                "results": results,
                "context": "\n".join(context_parts),
                "search_meta": {
                    "query": query,
                    "results": results[:8],
                    "images": list(aggregated.get("images") or [])[:3],
                    "sources_used": list(aggregated.get("sources_used") or []),
                    "total": len(results),
                },
            }
        except Exception as e:
            return {}

    async def _generate_follow_ups(self, user_message: str, ai_content: str, history: list[str]) -> list[str]:
        """Generate 3 follow-up questions using DeepSeek."""
        try:
            messages = [
                {"role": "system", "content": "根据对话上下文，推测用户接下来可能想问的 3 个问题。简短（10字以内），自然口语。输出 JSON 数组 [\"问题1\",\"问题2\",\"问题3\"]"},
                {"role": "user", "content": f"用户问：{user_message}\n\nAI回答：{ai_content[:500]}"},
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
                result = json.loads(content)
                if isinstance(result, list):
                    return [str(q) for q in result[:3]]
        except Exception:
            pass
        return []
