"""Focused AI operations for the Makers PDF/paper reader."""

import asyncio
import time

from ..chat._llm import get_model
from ..chat._protocol import StreamDeltaNormalizer, public_error
from .._shared.auth import require_user
from .._shared.entitlements import require_skill_access
from .._shared.http import error


PROMPTS = {
    "translate": "把以下学术文本准确翻译成中文。保留公式、术语和引用编号，不添加原文没有的内容。",
    "summarize": "用中文简洁总结以下学术文本的核心论点、方法和结论。",
    "explain": "用中文解释以下术语或文本，先给直观解释，再说明它在论文语境中的含义。",
    "formula": "解释以下公式或数学文本中各符号、关系、用途和直观含义；信息不足时明确说明。",
    "analyze": "阅读以下论文文本，按研究问题、方法、数据/实验、主要结论、创新点、局限性和可复现线索给出结构化中文助读。引用页码标记若原文包含页码。",
    "full-translate": "把以下论文文本翻译成中文，保持标题和段落结构，保留公式与引用。文本可能是分块内容，不要省略。",
    "terms": "提取以下论文最重要的术语，给出英文、中文译名和一句语境解释。",
    "qa": "仅依据给出的论文文本回答问题。结论必须可由文本支持；找不到时明确说论文片段未提供，并指出还需要哪部分。",
}


def _text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(str(item.get("text") or "") for item in content if isinstance(item, dict))
    return str(content or "")


async def handler(ctx):
    identity = require_user(ctx)
    try:
        require_skill_access(identity, "paper-reading")
    except PermissionError as exc:
        return error(str(exc), 403, code="SKILL_ACCESS_DENIED")
    body = ctx.request.body or {}
    action = str(body.get("action") or "")
    text = str(body.get("text") or "").strip()
    question = str(body.get("question") or "").strip()
    response_language = str(body.get("response_language") or "zh-CN")
    if action not in PROMPTS:
        return error("不支持的助读操作")
    if not text:
        return error("缺少可分析的论文文本")
    limit = 120000 if action in {"analyze", "full-translate", "terms", "qa"} else 12000
    text = text[:limit]
    user = f"论文文本：\n{text}"
    if action == "qa":
        if not question:
            return error("问题不能为空")
        user += f"\n\n问题：{question[:2000]}"
    language_hint = {
        "zh-CN": "请使用简体中文。",
        "zh-TW": "請使用繁體中文。",
        "en": "Respond in clear English.",
        "cat-cute": "请使用简体中文，保持准确，语气像可爱的橘猫，适度加“喵”。",
        "cat-cold": "请使用简体中文，保持准确，语气像冷静克制的橘猫，偶尔简短加“喵”。",
    }.get(response_language, "请使用简体中文。")
    messages = [
        {
            "role": "system",
            "content": (
                f"{PROMPTS[action]}\n{language_hint}\n"
                "输出 GitHub Flavored Markdown。直接输出结果，不要描述内部过程。"
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
                    "content": public_error(exc),
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
