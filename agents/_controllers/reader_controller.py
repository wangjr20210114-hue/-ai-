"""Controller for focused Makers PDF and paper reader operations."""

import asyncio
import time

from ..chat._llm import get_model
from ..chat._protocol import StreamDeltaNormalizer, public_error
from .._infrastructure.makers.identity import require_user
from .._infrastructure.http import error
from .._application.intelligence.service import load_intelligence_state
from .._application.skills.access import resolve_skill_access
from .._application.i18n import language_instruction, normalize_language, text as copy_text


PROMPTS = frozenset({
    "translate", "summarize", "explain", "formula", "analyze",
    "full-translate", "terms", "qa",
})


def _text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(str(item.get("text") or "") for item in content if isinstance(item, dict))
    return str(content or "")


async def handler(ctx):
    body = ctx.request.body or {}
    response_language = normalize_language(body.get("response_language"))
    identity = require_user(ctx)
    intelligence = await load_intelligence_state(
        ctx.store.langgraph_store,
        str(identity["user_id"]),
    )
    access = resolve_skill_access(identity, intelligence.get("skill_preferences"))
    if not access.allows_capability("paper_assistant"):
        if access.reason_for_capability("paper_assistant") == "login_required":
            return error(copy_text("reader.login_required", response_language), 403, code="LOGIN_REQUIRED")
        return error(copy_text("reader.skill_disabled", response_language), 403, code="SKILL_DISABLED")
    action = str(body.get("action") or "")
    text = str(body.get("text") or "").strip()
    question = str(body.get("question") or "").strip()
    if action not in PROMPTS:
        return error(copy_text("reader.unsupported", response_language))
    if not text:
        return error(copy_text("reader.text_required", response_language))
    limit = 120000 if action in {"analyze", "full-translate", "terms", "qa"} else 12000
    text = text[:limit]
    user = copy_text(
        "model.reader.document", response_language, document=text,
    )
    if action == "qa":
        if not question:
            return error(copy_text("reader.question_required", response_language))
        user += "\n\n" + copy_text(
            "model.reader.question", response_language,
            question=question[:2000],
        )
    messages = [
        {
            "role": "system",
            "content": copy_text(
                "model.reader.system", response_language,
                task=copy_text(f"model.reader.{action}", response_language),
                language_instruction=language_instruction(response_language),
            ),
        },
        {"role": "user", "content": user},
    ]
    reasoning_action = action in {"analyze", "qa"}
    reader_model = get_model(
        ctx.env,
        thinking_mode="enabled" if reasoning_action else "disabled",
        fallback_profile="reasoning" if reasoning_action else "fast",
    )

    async def gen():
        queue: asyncio.Queue = asyncio.Queue()
        done = object()

        async def produce():
            normalizer = StreamDeltaNormalizer()
            try:
                async for chunk in reader_model.astream(messages):
                    delta = normalizer.push(_text(getattr(chunk, "content", "")))
                    if delta:
                        await queue.put(ctx.utils.sse({
                            "type": "paper_delta",
                            "content": delta,
                        }))
                await queue.put(ctx.utils.sse({"type": "paper_done"}))
            except Exception as exc:
                await queue.put(ctx.utils.sse({
                    "type": "error_message",
                    "content": public_error(exc, response_language),
                }))
            finally:
                await queue.put(done)

        producer = asyncio.create_task(produce())
        try:
            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=5)
                except asyncio.TimeoutError:
                    yield ctx.utils.sse({
                        "type": "ping",
                        "ts": int(time.time() * 1000),
                    })
                    continue
                if item is done:
                    break
                yield item
        finally:
            if not producer.done():
                producer.cancel()
        yield b"data: [DONE]\n\n"

    return ctx.utils.stream_sse(gen())
