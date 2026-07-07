"""WebSocket 端点：意图路由器 + 流式输出 + 追问推荐。"""
from __future__ import annotations

import json
import time
import traceback

import httpx
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from config import settings
from models.schemas import WSMessage

router = APIRouter()


async def _generate_follow_ups(user_message: str, ai_content: str, history: list[str]) -> list[str]:
    """用 LLM 生成 3 条追问建议。"""
    if not settings.llm_ready or not ai_content:
        return []
    try:
        messages = [
            {
                "role": "system",
                "content": (
                    "根据用户的对话上下文，推测用户接下来可能想问的 3 个问题。"
                    "要求：1. 简短（10字以内）2. 自然口语 3. 与当前话题相关 4. 不要重复已问过的\n"
                    '输出格式：JSON 数组 ["问题1","问题2","问题3"]'
                ),
            },
            {
                "role": "user",
                "content": f"用户问：{user_message}\n\nAI回答：{ai_content[:500]}",
            },
        ]
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{settings.llm_base_url}/chat/completions",
                headers={"Authorization": f"Bearer {settings.llm_api_key}"},
                json={
                    "model": settings.llm_model,
                    "messages": messages,
                    "max_tokens": 200,
                    "temperature": 0.8,
                },
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"].strip()
            content = content.strip("`").strip()
            if content.startswith("json"):
                content = content[4:].strip()
            result = json.loads(content)
            if isinstance(result, list):
                return [str(q) for q in result[:3]]
    except Exception as e:
        print(f"[follow_ups] failed: {e}")
    return []


@router.websocket("/ws/{session_id}")
async def ws_endpoint(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()
    await websocket.send_text(
        WSMessage(type="ack", payload={"session_id": session_id}).model_dump_json()
    )

    history: list[str] = []

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

            if msg.type == "user_activity":
                text = msg.payload.get("text", "")
                if not text:
                    continue

                history.append(f"用户: {text}")

                await websocket.send_text(
                    WSMessage(type="chat_thinking", payload={}).model_dump_json()
                )

                try:
                    from agent.intent_router import route_message

                    result = await route_message(text, session_id, history)
                    history.append(f"AI({result.intent}): {result.content[:100]}")

                    # === paper 意图 ===
                    if result.intent == "paper":
                        await _handle_paper_intent(websocket, result, text, session_id, history)
                        continue

                    # === immediate / chat → 流式输出 ===
                    if result.mode == "immediate":
                        msg_id = f"ai-stream-{int(time.time() * 1000)}"
                        await websocket.send_text(
                            WSMessage(type="stream_start", payload={"id": msg_id, "intent": result.intent}).model_dump_json()
                        )
                        await _stream_text(websocket, msg_id, result.content)

                        # 生成追问
                        follow_ups = await _generate_follow_ups(text, result.content, history)

                        await websocket.send_text(
                            WSMessage(type="stream_end", payload={"id": msg_id, "follow_ups": follow_ups}).model_dump_json()
                        )
                        continue

                    # === suggestion 模式 ===
                    # 先生成追问
                    follow_ups = await _generate_follow_ups(text, result.content, history)
                    await websocket.send_text(
                        WSMessage(
                            type="suggestion",
                            payload={
                                "intent": result.intent,
                                "mode": result.mode,
                                "content": result.content,
                                "icon": result.icon,
                                "action_label": result.action_label,
                                "params": result.params,
                                "data": result.data,
                                "follow_ups": follow_ups,
                            },
                        ).model_dump_json()
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
    except Exception as e:
        print(f"[WS FATAL] {type(e).__name__}: {e}")
        traceback.print_exc()


async def _stream_text(websocket: WebSocket, msg_id: str, full_text: str) -> None:
    """打字机效果逐字发送。"""
    import re
    import asyncio
    tokens = re.findall(r'[\u4e00-\u9fff]|[a-zA-Z]+|\s+|\S', full_text)
    for token in tokens:
        await websocket.send_text(
            WSMessage(type="stream_delta", payload={"id": msg_id, "delta": token}).model_dump_json()
        )
        await asyncio.sleep(0.02)


async def _handle_paper_intent(websocket, result, user_message, session_id, history) -> None:
    """处理论文意图：搜索 + 流式介绍 + 论文列表 + 追问。"""
    topic = result.params.get("topic", user_message)

    # 1. 搜索（传入用户原始消息，保留"2篇""近5年"等约束）
    papers = []
    search_error = ""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post("http://127.0.0.1:8000/api/paper/search", data={
                "topic": topic,
                "user_message": user_message,
            })
            data = resp.json()
            if data.get("error"):
                search_error = data["error"]
            else:
                papers = data.get("papers", [])
    except Exception as e:
        search_error = f"搜索失败: {e}"

    msg_id = f"ai-paper-{int(time.time() * 1000)}"
    await websocket.send_text(
        WSMessage(type="stream_start", payload={"id": msg_id, "intent": "paper"}).model_dump_json()
    )

    if papers:
        paper_summaries = "\n".join(
            f"- {p.get('title', '')} ({p.get('year', '')}, arXiv:{p.get('arxiv_id', '')})\n  摘要：{p.get('abstract_zh', '')}"
            for p in papers
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "你是学术助手。用户想找论文，系统已搜索到以下论文。"
                    "请你用自然、口语化的方式介绍这些论文，就像和朋友聊天一样。\n\n"
                    "要求：\n"
                    "1. 不要列清单，用自然段落介绍\n"
                    "2. 重点介绍最经典/最重要的那篇\n"
                    "3. 简要提到其他相关论文\n"
                    "4. 用 Markdown 格式\n\n"
                    "【绝对禁止】：不要在结尾说『需要我帮你进一步整理』『你想了解更多吗』等引导语。"
                    "不要说『你可以选择』『你看看哪篇感兴趣』等。论文列表会由系统自动展示，你只需介绍即可。"
                ),
            },
            {"role": "user", "content": f"用户想找关于「{topic}」的论文。\n\n搜索结果：\n{paper_summaries}"},
        ]

        try:
            full_text = ""
            async with httpx.AsyncClient(timeout=60.0) as client:
                async with client.stream(
                    "POST",
                    f"{settings.llm_base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {settings.llm_api_key}"},
                    json={
                        "model": settings.llm_model,
                        "messages": messages,
                        "max_tokens": 800,
                        "temperature": 0.7,
                        "stream": True,
                    },
                ) as resp:
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

            history.append(f"AI(paper): {full_text[:100]}")

            # 生成追问
            follow_ups = await _generate_follow_ups(user_message, full_text, history)

            await websocket.send_text(
                WSMessage(type="stream_end", payload={"id": msg_id, "papers": papers, "follow_ups": follow_ups}).model_dump_json()
            )
        except Exception as e:
            print(f"[paper_intro] LLM stream failed: {e}")
            await websocket.send_text(
                WSMessage(type="stream_end", payload={"id": msg_id, "papers": papers, "fallback": f"我帮你找到了 {len(papers)} 篇关于「{topic}」的论文。"}).model_dump_json()
            )
    else:
        fallback = f"抱歉，没找到关于「{topic}」的论文。你可以换个关键词试试。"
        await _stream_text(websocket, msg_id, fallback)
        await websocket.send_text(
            WSMessage(type="stream_end", payload={"id": msg_id, "papers": []}).model_dump_json()
        )
