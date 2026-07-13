"""General conversational skill backed by the unified model gateway."""
from __future__ import annotations

import json
from typing import Any, AsyncIterator

import httpx

import asyncio

from agent.cancellation import CancellationToken
from agent.contracts import FailurePolicy, PermissionLevel, RiskLevel, SkillSchema
from config import settings
from services.model_gateway import CallContext, ModelGateway, ModelRequest
from skills.base_skill import BaseSkill, SkillResult, SkillStreamEvent

import re


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
                    "不要在回答中提及搜索、参考信息、来源等内部过程。"
                ),
            },
            *_history_messages(history, message),
            {"role": "user", "content": message},
        ]

        # If web search is enabled, fetch search results and prepend context
        search_data: dict[str, Any] = {}
        if web_search_enabled and self._should_search(message):
            search_data = await self._web_search(message)
            result_count = len(search_data.get("results", []))
            media_count = len(search_data.get("media", []))

            from urllib.parse import urlparse as _urlparse
            searched_sources = []
            for r in search_data.get("results", [])[:6]:
                source = str(r.get("source", ""))
                url = str(r.get("url", ""))
                try:
                    domain = _urlparse(url).netloc.replace("www.", "")[:25] if url.startswith("http") else ""
                except Exception:
                    domain = ""
                label = f"{source}:{domain}" if domain else source
                if label and label not in searched_sources:
                    searched_sources.append(label)
            if searched_sources:
                yield SkillStreamEvent(
                    event_type="search_status",
                    data={
                        "status": "analyzing",
                        "statusText": f"已搜索 {', '.join(searched_sources[:5])}",
                    },
                )

            # Phase 2: results summary
            if result_count > 0:
                source_titles = []
                for r in search_data.get("results", [])[:5]:
                    title = re.sub(r'\[\[[^\]]*\]\]', '', str(r.get("title", ""))).strip()[:25]
                    if title:
                        source_titles.append(title)
                yield SkillStreamEvent(
                    event_type="search_status",
                    data={
                        "status": "analyzing",
                        "statusText": f"找到 {result_count} 条信息" + (f"，{media_count} 张图片" if media_count else "") + "，正在整理…",
                        "sources": source_titles,
                    },
                )
            # Inject search context and media info if we have results
            context_text = search_data.get("context", "")
            media_list = search_data.get("media", [])
            has_real_content = any(
                r.get("snippet", "").strip()
                for r in search_data.get("results", [])[:6]
            )
            if search_data.get("results"):
                raw_results = search_data.get("results", [])
                media_list = search_data.get("media", [])

                # Score all candidates for relevance to the query
                scored = await self._score_candidates(message, raw_results, media_list)

                parts: list[str] = []
                context_text = search_data.get("context", "")
                relevant_media = scored.get("media", [])
                relevant_links = scored.get("links", [])

                if context_text:
                    parts.append(f"## 搜索结果\n{context_text}")

                if relevant_links:
                    links = []
                    for item in relevant_links:
                        links.append(
                            f"- [{item['source']}] {item['title'][:40]}（{item['score']}/10）\n"
                            f"  {item['url']}"
                        )
                    parts.append(
                        f"## 推荐阅读\n"
                        f"这些链接与用户问题高度相关，请在回答中自然地引用，让用户点击深入了解。\n"
                        f"{chr(10).join(links)}"
                    )

                if relevant_media:
                    img_lines = []
                    for m in relevant_media:
                        img_lines.append(
                            f"- {m['id']}: {m['caption']}（{m['score']}/10）"
                        )
                    parts.append(
                        f"## 可用图片\n"
                        f"评分已标注。只在图片与段落直接相关时单独输出 "
                        f"[[image:media-id]]；不要输出或猜测图片 URL。\n"
                        f"{chr(10).join(img_lines)}"
                    )

                if parts:
                    messages.insert(1, {
                        "role": "system",
                        "content": "\n\n".join(parts).strip(),
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
                # Fire-and-forget: extract memory proposals from this conversation
                asyncio.create_task(
                    self._extract_and_upsert_memories(
                        message, full_text, session_id
                    )
                )

    def _should_search(self, message: str) -> bool:
        if len(message) < 5:
            return False
        skip_keywords = ["你好", "你是谁", "谢谢", "再见", "帮我画", "生成图片"]
        return not any(kw in message for kw in skip_keywords)

    async def _score_candidates(
        self, query: str, results: list[dict[str, Any]], media_list: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Score all multimodal candidates (links, images) for relevance to query via DeepSeek."""
        try:
            import json as _json, httpx
            candidates: list[dict] = []
            for r in results:
                src = str(r.get("source", ""))
                url = str(r.get("url", "") or r.get("article_url", "")).strip()
                if src in ("wechat", "zhihu", "baike"):
                    candidates.append({"type": "link", "id": f"l{len(candidates)}",
                        "source": src, "title": str(r.get("title", ""))[:50],
                        "snippet": str(r.get("snippet", ""))[:100],
                        "url": url or f"（{src}来源，无直接链接）"})
            for m in media_list:
                candidates.append({"type": "image", "id": m.get("id", ""),
                    "caption": str(m.get("caption", ""))[:50], "url": str(m.get("url", ""))})
            if not candidates:
                return {"context": "", "links": [], "media": []}

            ct = "\n".join(f"{c['id']} [{c['type']}] {c.get('title') or c.get('caption','')}: {c.get('snippet','')}"
                          for c in candidates)
            prompt = (f"用户查询：{query[:80]}\n\n为候选项评相关度1-10分并给理由：\n\n{ct}\n\n"
                      f'返回JSON数组：{{"id":"x","score":1-10,"reason":"理由"}}')
            async with httpx.AsyncClient(timeout=15) as cl:
                r = await cl.post(f"{settings.deepseek_base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {settings.deepseek_api_key}"},
                    json={"model": settings.deepseek_model, "messages": [{"role":"user","content":prompt}],
                          "max_tokens": 500, "temperature": 0.3})
                r.raise_for_status()
                raw = r.json()["choices"][0]["message"]["content"].strip()
                # Strip ```json ... ``` markdown code blocks
                raw = raw.strip("`")
                if raw.startswith("json\n"):
                    raw = raw[5:]
                elif raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.strip()
                scores = _json.loads(raw)
            if not isinstance(scores, list):
                return {
                    "context": "",
                    "links": [],
                    "media": [
                        {
                            "id": str(item.get("id", "")),
                            "caption": str(item.get("caption") or item.get("alt") or "相关图片"),
                            "score": 5,
                        }
                        for item in media_list
                        if item.get("id")
                    ],
                }

            sm = {s["id"]: (int(s["score"]), str(s.get("reason", ""))) for s in scores if isinstance(s, dict)}

            links = []
            for c in candidates:
                if c["type"] != "link": continue
                sc = sm.get(c["id"], (4, ""))
                if sc[0] >= 4:
                    lb = {"wechat": "公众号", "zhihu": "知乎", "baike": "百科"}.get(c["source"], c["source"])
                    links.append({"source": lb, "title": c["title"], "url": c["url"], "score": sc[0], "reason": sc[1]})
            links.sort(key=lambda x: -x["score"])

            imgs = []
            for c in candidates:
                if c["type"] != "image": continue
                sc = sm.get(c["id"], (5, ""))
                if sc[0] >= 5:
                    imgs.append({"id": c["id"], "caption": c["caption"], "score": sc[0], "reason": sc[1]})
            imgs.sort(key=lambda x: -x["score"])

            return {"context": "", "links": links, "media": imgs}
        except Exception:
            return {
                "context": "",
                "links": [],
                "media": [
                    {
                        "id": str(item.get("id", "")),
                        "caption": str(item.get("caption") or item.get("alt") or "相关图片"),
                        "score": 5,
                    }
                    for item in media_list
                    if item.get("id")
                ],
            }

    async def _extract_and_upsert_memories(
        self,
        user_message: str,
        ai_response: str,
        session_id: str,
    ) -> None:
        """Fire-and-forget: extract user facts from conversation and upsert directly."""
        try:
            import json as _json
            import httpx

            total_chars = len(user_message) + len(ai_response)
            if total_chars < 30:
                return

            prompt = (
                "从以下对话中提取关于用户的长期事实和偏好。\n\n"
                "返回 JSON 数组（最多 2 条），每条格式：\n"
                '{"key": "简短标签（如「喜欢猫」「住在北京」）",'
                ' "value": "具体内容", "confidence": 0.3-1.0}\n\n'
                "confidence 规则：明确陈述=0.9+，暗示=0.5-0.7，不确定=跳过\n"
                "不要提取问候语、临时信息。如果本次对话改变了旧事实，confidence 应该更高。\n"
            )
            user_content = f"用户：{user_message}\n\nAI回复（摘要）：{ai_response[:1000]}"

            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    f"{settings.deepseek_base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {settings.deepseek_api_key}"},
                    json={
                        "model": settings.deepseek_model,
                        "messages": [
                            {"role": "system", "content": prompt},
                            {"role": "user", "content": user_content},
                        ],
                        "max_tokens": 300,
                        "temperature": 0.3,
                    },
                )
                resp.raise_for_status()
                content = resp.json()["choices"][0]["message"]["content"].strip().strip("`").strip()
                if content.startswith("json"):
                    content = content[4:].strip()
                items = _json.loads(content)
                if not isinstance(items, list):
                    return

            from database.repositories import memory_repo

            for item in items[:2]:
                key = str(item.get("key", "")).strip()
                value = item.get("value", "")
                if not key or not value:
                    continue
                confidence = min(1.0, max(0.3, float(item.get("confidence") or 0.5)))
                try:
                    await memory_repo.upsert_memory(
                        key=key,
                        value=value,
                        confidence=confidence,
                        source_message_id=session_id or "",
                    )
                except Exception:
                    pass  # Non-critical
        except Exception:
            pass  # Best-effort, never block

    async def _web_search(self, query: str) -> dict[str, Any]:
        """Fetch web search results and build context for the LLM."""
        try:
            from services.search_system import search as system_search
            aggregated = await system_search(query, intent="general", time_sensitive=False, depth="basic")
            results = list(aggregated.get("results") or [])
            if not results:
                return {}
            # Build context text from top results — clean bracket artifacts from snippets
            context_parts = []
            for r in results[:6]:
                title = r.get("title", "")
                snippet = r.get("snippet", "")
                source = r.get("source", "")
                # Remove [[xxx] yyy] patterns that leak from search providers
                snippet = re.sub(r'\[\[[^\]]*\]([^\]]*)\]', r'\1', snippet).strip()
                context_parts.append(f"[{source}] {title}: {snippet}")
            # Build media list from search results
            media_list = []
            raw_media = list(aggregated.get("media") or [])
            image_descs = list(aggregated.get("image_descriptions") or [])
            # Build a url→description map for visual filtering
            desc_by_url = {d.get("url", ""): d.get("description", "") for d in image_descs if d.get("url")}
            for m in raw_media:
                url = m.get("url", "")
                caption = m.get("caption") or m.get("alt", "")
                vision_desc = desc_by_url.get(url, "")
                if vision_desc:
                    caption = vision_desc
                # Visual model already filtered irrelevant images in describe_images()
                media_list.append({
                    "id": m.get("id", ""),
                    "kind": "image",
                    "url": url,
                    "caption": caption,
                    "alt": caption,
                    "source_url": m.get("source_url", ""),
                    "source_id": m.get("source_id", ""),
                    "source_title": m.get("source_title", ""),
                    "generated": False,
                })
            # Also extract images from results as fallback
            if not media_list:
                images = list(aggregated.get("images") or [])[:3]
                for i, img_url in enumerate(images):
                    media_list.append({
                        "id": f"media-{i+1}",
                        "kind": "image",
                        "url": img_url,
                        "caption": "",
                        "alt": "搜索图片",
                        "source_url": "",
                        "source_id": "",
                        "generated": False,
                    })
            # Tag results with stable IDs for frontend card resolution
            for i, r in enumerate(results[:8]):
                if not r.get("id"):
                    r["id"] = f"source-{i+1}"
            return {
                "results": results,
                "context": "\n".join(context_parts),
                "media": media_list,
                "search_meta": {
                    "query": query,
                    "results": results[:8],
                    "media": media_list,
                    "images": [m["url"] for m in media_list],
                    "sources_used": list(aggregated.get("sources_used") or []),
                    "total": len(results),
                },
            }
        except Exception:
            return {}

    async def _generate_follow_ups(self, user_message: str, ai_content: str, history: list[str]) -> list[str]:
        """Generate 3 follow-up questions using DeepSeek."""
        if settings.mock_mode:
            return []
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
