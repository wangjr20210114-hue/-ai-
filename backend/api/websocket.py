"""WebSocket 端点：意图推断（DeepSeek）→ 自动执行 → 流式回复。

架构：
1. DeepSeek 推断意图（便宜快速，不生成回复内容）
2. 根据意图自动执行对应工具（搜索/生图/论文/会议/旅游）
3. chat 意图 → 混元流式对话（多轮记忆）
4. 工具执行结果 → DeepSeek 流式总结（翻译/论文/搜索）
"""
from __future__ import annotations

import asyncio
import json
import time
import traceback

import httpx
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from agent import register_all_skills

from agent.context import AgentContext
from agent.events import AgentEvent
from agent.orchestrator import AgentOrchestrator

from config import settings
from database.repositories.conversation_repo import (
    DEFAULT_CONVERSATION_ID,
    ensure_local_identity,
    get_conversation,
    history_lines,
)
from models.schemas import WSMessage
from services.hunyuan_service import QuotaExhaustedError, _check_quota_error
from skills.base_skill import SkillRegistry

router = APIRouter()


async def _chat_agent_handler(websocket: WebSocket, message: str, params: dict, history: list[str]) -> None:
    await _handle_chat(websocket, message, history)


def _build_orchestrator() -> AgentOrchestrator:
    registry = SkillRegistry()
    register_all_skills(registry)
    return AgentOrchestrator(
        registry=registry,
        handlers={
            "chat": _chat_agent_handler,
            "image": _handle_image,
            "search": _handle_search,
            "paper": _handle_paper,
            "travel": _handle_travel,
            "meeting": _handle_meeting,
            "translation": _handle_translation,
        },
    )


@router.websocket("/ws/{conversation_id}")
async def ws_endpoint(websocket: WebSocket, conversation_id: str) -> None:
    await ensure_local_identity()
    if conversation_id == "local-user":
        conversation_id = DEFAULT_CONVERSATION_ID
    if await get_conversation(conversation_id) is None:
        await websocket.close(code=1008, reason="conversation not found")
        return
    await websocket.accept()
    await websocket.send_text(
        WSMessage(
            type="ack",
            payload={"user_id": "local-user", "conversation_id": conversation_id},
        ).model_dump_json()
    )

    history = await history_lines(conversation_id)
    orchestrator = _build_orchestrator()
    context = AgentContext(session_id=conversation_id, history=history)

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = WSMessage.model_validate_json(raw)
            except ValidationError:
                continue

            if msg.type == "ping":
                await websocket.send_text(WSMessage(type="pong").model_dump_json())
                continue

            if msg.type != "user_activity":
                continue

            text = msg.payload.get("text", "")
            if not text:
                continue

            history.append(f"用户: {text}")

            # 通知前端：开始思考
            await websocket.send_text(
                WSMessage(type="chat_thinking", payload={}).model_dump_json()
            )

            try:
                event = AgentEvent.user_activity(
                    session_id=conversation_id,
                    text=text,
                    payload=msg.payload,
                )
                await orchestrator.handle_user_activity(websocket, event, context)

            except QuotaExhaustedError as e:
                # API 额度用尽 → 立即终止，通知前端
                error_msg = str(e)
                print(f"[QUOTA] {error_msg}")
                traceback.print_exc()
                history.append(f"AI(error): {error_msg[:100]}")
                await websocket.send_text(
                    WSMessage(type="stream_end", payload={"id": f"err-{int(time.time()*1000)}"}).model_dump_json()
                )
                await websocket.send_text(
                    WSMessage(type="error", payload={
                        "message": error_msg,
                        "error_type": "quota_exhausted",
                        "provider": getattr(e, "provider", ""),
                    }).model_dump_json()
                )
            except Exception as e:
                error_msg = f"处理失败：{type(e).__name__}: {str(e)}"
                print(f"[WS ERROR] {error_msg}")
                traceback.print_exc()
                await websocket.send_text(
                    WSMessage(type="chat_reply", payload={"content": f"抱歉，处理时出错了：{error_msg}"}).model_dump_json()
                )

    except WebSocketDisconnect:
        pass


async def _stream_sse(websocket: WebSocket, msg_id: str, system_prompt: str, user_content: str,
                      model: str = None, max_tokens: int = 1500, history: list[str] = None) -> str:
    """通用流式 LLM 调用，返回完整文本。"""
    use_model = model or settings.llm_model
    # model 为 DeepSeek 时使用对应的 key / base_url，否则用默认 provider
    if use_model == settings.deepseek_model:
        use_key = settings.deepseek_api_key
        use_base = settings.deepseek_base_url
    else:
        use_key = settings.hunyuan_api_key
        use_base = settings.hunyuan_base_url

    # 构建多轮 messages
    messages = [{"role": "system", "content": system_prompt}]
    if history:
        for h in history[-12:]:
            if h.startswith("用户: "):
                messages.append({"role": "user", "content": h[4:]})
            elif h.startswith("AI("):
                idx = h.find("): ")
                if idx > 0:
                    messages.append({"role": "assistant", "content": h[idx + 3:]})
    messages.append({"role": "user", "content": user_content})

    full_text = ""
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            async with client.stream(
                "POST",
                f"{use_base}/chat/completions",
                headers={"Authorization": f"Bearer {use_key}"},
                json={
                    "model": use_model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": 0.7,
                    "stream": True,
                },
            ) as resp:
                # 额度检测（在 raise_for_status 之前）
                provider = "DeepSeek" if use_model == settings.deepseek_model else "混元"
                if resp.status_code != 200:
                    body = await resp.aread()
                    _check_quota_error(resp.status_code, body.decode("utf-8", errors="replace"), provider)
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        t = delta.get("content", "")
                        if t:
                            full_text += t
                            await websocket.send_text(
                                WSMessage(type="stream_delta", payload={"id": msg_id, "delta": t}).model_dump_json()
                            )
                    except (json.JSONDecodeError, IndexError):
                        continue
    except QuotaExhaustedError:
        raise  # 额度错误向上传播到主处理器
    except Exception as e:
        print(f"[stream_sse] failed: {e}")
        full_text = f"抱歉，处理时出错了：{type(e).__name__}: {e}"

    if not full_text:
        full_text = "我没能理解你的意思，能再说一次吗？"

    return full_text


async def _generate_follow_ups(user_message: str, ai_content: str, history: list[str]) -> list[str]:
    """用 DeepSeek 生成 3 条追问。"""
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
    except Exception as e:
        print(f"[follow_ups] failed: {e}")
    return []


async def _handle_chat(websocket: WebSocket, user_message: str, history: list[str]) -> None:
    """混元流式对话（多轮记忆）。"""
    msg_id = f"ai-chat-{int(time.time() * 1000)}"
    await websocket.send_text(
        WSMessage(type="stream_start", payload={"id": msg_id, "intent": "chat"}).model_dump_json()
    )

    system_prompt = (
        "你是元宝主动式 Agent，一个智能助手。你可以帮用户规划旅游、创建腾讯会议、搜索论文、翻译、生图等。"
        "在普通对话中，你是一个友好、自然的聊天伙伴。回答简洁有用，用 Markdown 格式。"
    )

    full_text = await _stream_sse(websocket, msg_id, system_prompt, user_message, history=history)
    history.append(f"AI(chat): {full_text[:200]}")

    follow_ups = await _generate_follow_ups(user_message, full_text, history)
    await websocket.send_text(
        WSMessage(type="stream_end", payload={"id": msg_id, "follow_ups": follow_ups}).model_dump_json()
    )


async def _handle_image(websocket: WebSocket, user_message: str, params: dict, history: list[str]) -> None:
    """自动生图（混元生图，无需用户点击确认）。"""
    prompt = params.get("prompt", user_message)
    msg_id = f"ai-image-{int(time.time() * 1000)}"

    # 通知前端：开始生图（前端显示生成动画）
    await websocket.send_text(
        WSMessage(type="stream_start", payload={"id": msg_id, "intent": "image", "status": "generating"}).model_dump_json()
    )

    from services.hunyuan_service import hunyuan_service, ApiNotConfiguredError, QuotaExhaustedError

    try:
        image_url = await hunyuan_service.text_to_image(prompt)
        # 流式发送图片结果
        content = f"已为你生成图片 🎨\n\n![{prompt}]({image_url})"
        history.append(f"AI(image): [图片] {prompt[:50]}")

        # 逐字发送文字部分
        text_part = f"已为你生成图片 🎨\n\n"
        for char in text_part:
            await websocket.send_text(
                WSMessage(type="stream_delta", payload={"id": msg_id, "delta": char}).model_dump_json()
            )
            await asyncio.sleep(0.02)

        follow_ups = await _generate_follow_ups(user_message, content, history)
        await websocket.send_text(
            WSMessage(type="stream_end", payload={
                "id": msg_id,
                "image_url": image_url,
                "image_prompt": prompt,
                "follow_ups": follow_ups,
            }).model_dump_json()
        )
    except QuotaExhaustedError:
        raise  # 额度错误向上传播到主处理器
    except Exception as e:
        error = f"❌ 生图失败：{type(e).__name__}: {e}"
        history.append(f"AI(image): {error[:100]}")
        await websocket.send_text(
            WSMessage(type="stream_delta", payload={"id": msg_id, "delta": error}).model_dump_json()
        )
        await websocket.send_text(
            WSMessage(type="stream_end", payload={"id": msg_id}).model_dump_json()
        )


async def _handle_search(websocket: WebSocket, user_message: str, params: dict, history: list[str]) -> None:
    """搜索系统框架：意图分类 → 多源搜索 → 评分排序 → 随机选择 → AI 总结。"""
    query = params.get("query", user_message)
    msg_id = f"ai-search-{int(time.time() * 1000)}"

    await websocket.send_text(
        WSMessage(type="stream_start", payload={
            "id": msg_id, "intent": "search", "status": "searching"
        }).model_dump_json()
    )

    # 1. 搜索系统框架
    from services.search_system import search as system_search

    await websocket.send_text(
        WSMessage(type="search_status", payload={
            "id": msg_id, "status": "正在搜索..."
        }).model_dump_json()
    )

    # 从意图推断中获取搜索策略（全部由 DeepSeek 判断，不再硬编码关键词）
    search_type = params.get("search_type", "general")
    time_sensitive = params.get("time_sensitive", False)
    depth = params.get("depth", "standard")

    aggregated = await system_search(query, intent=search_type, time_sensitive=time_sensitive, depth=depth)

    results = aggregated["results"]
    images = aggregated["images"]
    image_descriptions = aggregated.get("image_descriptions", [])
    sources_used = aggregated["sources_used"]

    if not results:
        content = "抱歉，没有找到相关搜索结果。"
        await websocket.send_text(
            WSMessage(type="stream_delta", payload={"id": msg_id, "delta": content}).model_dump_json()
        )
        await websocket.send_text(WSMessage(type="stream_end", payload={"id": msg_id}).model_dump_json())
        return

    # 2. 发送"正在整理"状态 + 来源列表
    from services.search_service import build_search_prompt
    stream_gen, search_meta = await build_search_prompt(query, results, images, sources_used, image_descriptions)

    # 先发来源信息，前端在回答顶部展示
    await websocket.send_text(
        WSMessage(type="search_status", payload={
            "id": msg_id, "status": "thinking",
            "search_results": search_meta,
        }).model_dump_json()
    )

    full_text = ""
    async for chunk in stream_gen:
        full_text += chunk
        await websocket.send_text(
            WSMessage(type="stream_delta", payload={"id": msg_id, "delta": chunk}).model_dump_json()
        )

    history.append(f"AI(search): {full_text[:200]}")

    follow_ups = await _generate_follow_ups(user_message, full_text, history)
    await websocket.send_text(
        WSMessage(
            type="stream_end",
            payload={
                "id": msg_id,
                "follow_ups": follow_ups,
                "search_results": search_meta,
            },
        ).model_dump_json()
    )


async def _handle_paper(websocket: WebSocket, user_message: str, params: dict, history: list[str]) -> None:
    """论文搜索（arXiv API + DeepSeek 介绍）。"""
    topic = params.get("topic", user_message)
    msg_id = f"ai-paper-{int(time.time() * 1000)}"

    await websocket.send_text(
        WSMessage(type="stream_start", payload={"id": msg_id, "intent": "paper"}).model_dump_json()
    )

    # 1. arXiv 搜索
    papers = []
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "http://127.0.0.1:8000/api/paper/search",
                data={"topic": topic, "user_message": user_message},
            )
            data = resp.json()
            papers = data.get("papers", [])
    except Exception as e:
        print(f"[paper] search failed: {e}")

    # 2. 混元流式介绍
    if papers:
        paper_summaries = "\n".join(
            f"- {p.get('title', '')} ({p.get('year', '')}, arXiv:{p.get('arxiv_id', '')})\n  摘要：{p.get('abstract_zh', '')}"
            for p in papers
        )
        system_prompt = (
            "你是学术助手。用户想找论文，系统已搜索到以下论文。"
            "请你用自然、口语化的方式介绍这些论文，就像和朋友聊天一样。\n\n"
            "要求：1. 不要列清单 2. 重点介绍最经典的 3. 用 Markdown 格式\n"
            "【绝对禁止】不要在结尾说任何引导语。论文列表会由系统自动展示。"
        )
        full_text = await _stream_sse(
            websocket, msg_id, system_prompt,
            f"用户想找关于「{topic}」的论文。\n\n搜索结果：\n{paper_summaries}",
            model=settings.deepseek_model,
            history=None,
        )
    else:
        full_text = f"抱歉，没找到关于「{topic}」的论文。你可以换个关键词试试。"
        await websocket.send_text(
            WSMessage(type="stream_delta", payload={"id": msg_id, "delta": full_text}).model_dump_json()
        )

    history.append(f"AI(paper): {full_text[:200]}")

    follow_ups = await _generate_follow_ups(user_message, full_text, history)
    await websocket.send_text(
        WSMessage(type="stream_end", payload={"id": msg_id, "papers": papers, "follow_ups": follow_ups}).model_dump_json()
    )


async def _handle_travel(websocket: WebSocket, user_message: str, params: dict, history: list[str]) -> None:
    """旅游意图 → 建议卡片。"""
    await websocket.send_text(
        WSMessage(
            type="suggestion",
            payload={
                "intent": "travel",
                "mode": "auto",
                "content": "好呀！我来帮你规划旅游行程 😊",
                "icon": "✈️",
                "action_label": "规划行程",
                "params": {**params, "user_message": user_message},
                "data": {},
                "follow_ups": [],
            },
        ).model_dump_json()
    )


async def _handle_meeting(websocket: WebSocket, user_message: str, params: dict, history: list[str]) -> None:
    """会议意图 → 建议卡片（需要确认）。"""
    subject = params.get("subject", "")
    time_str = params.get("start_time", "")
    prompt_parts = ["检测到你想创建会议"]
    if subject:
        prompt_parts.append(f"「{subject}」")
    if time_str:
        prompt_parts.append(f"，时间 {time_str}")
    prompt_parts.append("。需要我帮你创建腾讯会议吗？")
    prompt = "".join(prompt_parts)

    await websocket.send_text(
        WSMessage(
            type="suggestion",
            payload={
                "intent": "meeting",
                "mode": "suggest",
                "content": prompt,
                "icon": "📅",
                "action_label": "创建腾讯会议",
                "params": {**params, "message": user_message},
                "data": {},
                "follow_ups": [],
            },
        ).model_dump_json()
    )


async def _handle_translation(websocket: WebSocket, user_message: str, params: dict, history: list[str]) -> None:
    """翻译意图 → DeepSeek 自动翻译。"""
    msg_id = f"ai-translate-{int(time.time() * 1000)}"
    await websocket.send_text(
        WSMessage(type="stream_start", payload={"id": msg_id, "intent": "translation"}).model_dump_json()
    )

    system_prompt = "你是专业翻译。将用户提供的文本翻译成中文。直接输出译文，不要添加任何解释。用 Markdown 格式。"
    full_text = await _stream_sse(websocket, msg_id, system_prompt, user_message,
                                  model=settings.deepseek_model, history=None)
    history.append(f"AI(translation): {full_text[:200]}")

    follow_ups = await _generate_follow_ups(user_message, full_text, history)
    await websocket.send_text(
        WSMessage(type="stream_end", payload={"id": msg_id, "follow_ups": follow_ups}).model_dump_json()
    )
