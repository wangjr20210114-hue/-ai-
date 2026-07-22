"""Semantic post-turn opportunity detection for the proactive Agent.

The detector does not answer the user and never performs a side effect.  It
selects at most one useful next service that can be delivered through the
existing persistent proactive inbox or the next empty conversation.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from typing import Any


OPPORTUNITY_TYPES = {
    "search_update",
    "writing_improvement",
    "translation_review",
    "image_iteration",
    "document_next_step",
    "task_next_step",
}


def _text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            str(item.get("text") or "") for item in content if isinstance(item, dict)
        )
    return str(content or "")


def parse_opportunity(content: Any) -> dict[str, Any] | None:
    """Validate the model result and discard low-value or unsafe proposals."""
    text = _text(content).strip()
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        text = match.group(0)
    try:
        raw = json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict) or not bool(raw.get("should_notify")):
        return None
    opportunity_type = str(raw.get("type") or "").strip()
    if opportunity_type not in OPPORTUNITY_TYPES:
        return None
    title = str(raw.get("title") or "").strip()[:80]
    body = str(raw.get("body") or "").strip()[:240]
    action_prompt = str(raw.get("action_prompt") or "").strip()[:500]
    if not title or not body or not action_prompt:
        return None
    try:
        confidence = float(raw.get("confidence") or 0)
    except (TypeError, ValueError):
        confidence = 0
    if confidence < 0.72:
        return None
    try:
        expires_in_hours = max(1, min(168, int(raw.get("expires_in_hours") or 24)))
    except (TypeError, ValueError):
        expires_in_hours = 24
    return {
        "type": opportunity_type,
        "title": title,
        "body": body,
        "action_prompt": action_prompt,
        "priority": "normal" if str(raw.get("priority") or "") != "low" else "low",
        "confidence": round(min(1.0, confidence), 3),
        "expires_in_hours": expires_in_hours,
        "reason": str(raw.get("reason") or "").strip()[:240],
    }


async def detect_opportunity(
    model: Any,
    *,
    user_message: str,
    answer: str,
    capability_plan: dict[str, Any] | None = None,
    has_pending_action: bool = False,
    timeout_seconds: float = 6.0,
) -> dict[str, Any] | None:
    """Use semantic judgment to identify one proactive service opportunity."""
    if not str(user_message or "").strip() or not str(answer or "").strip() or has_pending_action:
        return None
    system = """你是元宝的主动服务机会识别器。用户当前请求已经回答完毕；你只判断是否存在一个值得在稍后主动提供、且用户没有明确要求的下一步服务。不要回答用户。

返回严格 JSON：should_notify(boolean)、type、title、body、action_prompt、priority、confidence、expires_in_hours、reason。
type 只能是 search_update、writing_improvement、translation_review、image_iteration、document_next_step、task_next_step。

判断标准：
- 必须能显著节省用户后续操作，或预防遗漏；没有明确额外价值就 should_notify=false。
- 搜索：只有信息明显会继续变化、存在待跟进节点或回答暴露了重要未决问题时才建议追踪；不要把普通搜索改写成“继续搜索”。
- 写作：只在已有草稿存在明确受众、用途或交付节点，可主动做语气、结构、长度或格式适配时建议。
- 翻译：只在术语一致性、目标受众、本地化或双语交付确有价值时建议，不机械建议“再润色”。
- 生图：只在本轮已经生成图片且存在明确可执行的构图、尺寸或版本延展价值时建议。
- 文档：上传或阅读文档后可建议总结、提取行动项、风险或生成回复，但只选最有价值的一项。
- 任务：用户陈述了目标、截止时间或连续步骤，且下一步清晰时才建议；不能制造焦虑。
- 简单问答、闲聊、算术、脑筋急转弯、一次性事实、用户明确拒绝后续、已有待确认 Action，全部 should_notify=false。
- 最多一条；title/body 要陈述用户能理解的事实和价值，action_prompt 必须能直接作为用户下一轮发给模型的自然指令。
- 不得包含或推断姓名、联系方式、精确地址、账号、证件、健康、财务、密钥等敏感信息，不得执行副作用，不得提内部模型、扫描、机会识别或数据库。
- confidence 低于 0.72 必须 should_notify=false；有效期 1–168 小时；一般优化 priority=low，具有明确时限但无安全风险时 priority=normal。
"""
    payload = {
        "user_message": str(user_message)[:3000],
        "answer": str(answer)[:6000],
        "capability_plan": capability_plan or {},
    }
    try:
        response = await asyncio.wait_for(
            model.ainvoke([
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ]),
            timeout=max(1.0, min(12.0, float(timeout_seconds))),
        )
    except Exception:
        return None
    return parse_opportunity(getattr(response, "content", response))


def opportunity_signal(
    opportunity: dict[str, Any], *, source_id: str, now: int,
) -> dict[str, Any]:
    """Convert a validated semantic proposal into the shared signal shape."""
    identity = "|".join((
        str(opportunity.get("type") or ""),
        " ".join(str(opportunity.get("action_prompt") or "").casefold().split()),
    ))
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
    expires_at = now + int(opportunity.get("expires_in_hours") or 24) * 3600
    return {
        "type": f"opportunity_{opportunity['type']}",
        "source": "semantic_opportunity",
        "dedup_key": f"semantic_opportunity:{digest}",
        "priority": str(opportunity.get("priority") or "low"),
        "subject_ids": [str(source_id or "")],
        "title": str(opportunity.get("title") or "下一步建议"),
        "detail": str(opportunity.get("body") or ""),
        "action": str(opportunity.get("action_prompt") or ""),
        "evidence": {
            "opportunity_type": str(opportunity.get("type") or ""),
            "confidence": float(opportunity.get("confidence") or 0),
            "reason": str(opportunity.get("reason") or ""),
            "source_id": str(source_id or ""),
        },
        "occurred_at": now,
        "expires_at": expires_at,
        "cooldown_seconds": 6 * 3600,
    }


def file_opportunity_signal(payload: dict[str, Any], *, dedup_key: str, now: int) -> dict[str, Any]:
    """A successful document upload is already a trusted, explicit signal."""
    filename = str(payload.get("filename") or "这份文档").strip()[:120] or "这份文档"
    is_paper = bool(payload.get("is_paper"))
    return {
        "type": "opportunity_document_next_step",
        "source": "file_uploaded",
        "dedup_key": f"document_opportunity:{dedup_key}",
        "priority": "normal",
        "subject_ids": [str(payload.get("file_id") or payload.get("storage_key") or "")],
        "title": "文档已就绪",
        "detail": f"{filename}已保存，可以继续提炼{('研究结论与局限' if is_paper else '摘要与行动项')}。",
        "action": (
            f"请阅读“{filename}”，提炼研究问题、方法、关键结论、局限和下一步研究建议"
            if is_paper else
            f"请阅读“{filename}”，先给出简洁摘要，再提取可执行行动项、负责人和时间信息"
        ),
        "evidence": {
            "opportunity_type": "document_next_step",
            "file_id": str(payload.get("file_id") or ""),
            "storage_key": str(payload.get("storage_key") or ""),
            "filename": filename,
            "is_paper": is_paper,
        },
        "occurred_at": now,
        "expires_at": now + 7 * 24 * 3600,
    }
