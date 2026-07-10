"""意图推断层（DeepSeek）+ 自动执行路由器。

核心原则：
1. 意图推断用 DeepSeek（便宜快速），不生成回复内容
2. 回复内容由混元根据完整对话历史自由生成
3. 意图推断只决定"调用什么工具"，不影响大模型回复
"""
from __future__ import annotations

import json
from typing import Any

import httpx

from agent import register_all_skills
from config import settings
from services.hunyuan_service import _check_quota_error, QuotaExhaustedError
from skills.base_skill import SkillRegistry

_registry = SkillRegistry()
_skills_registered = False


def _ensure_registered() -> None:
    global _skills_registered
    if not _skills_registered:
        register_all_skills(_registry)
        _skills_registered = True


async def classify_intent(
    message: str,
    history: list[str] | None = None,
) -> dict[str, Any]:
    """用 DeepSeek 推断用户意图。

    Returns:
        {"intent": "travel|meeting|search|image|translation|paper|chat", "params": {...}}
    """
    _ensure_registered()

    from prompts.templates import INTENT_CLASSIFICATION_PROMPT

    skill_desc = _registry.build_llm_description()
    system_prompt = INTENT_CLASSIFICATION_PROMPT.replace("{{SKILLS}}", skill_desc)

    # 构造对话历史
    history_str = ""
    if history:
        history_str = "\n".join(history[-8:])

    user_content = f"用户消息：{message}"
    if history_str:
        user_content += f"\n\n对话历史：\n{history_str}"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    # 用 DeepSeek 推断（便宜快速）
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{settings.deepseek_base_url}/chat/completions",
                headers={"Authorization": f"Bearer {settings.deepseek_api_key}"},
                json={
                    "model": settings.deepseek_model,
                    "messages": messages,
                    "max_tokens": 200,
                    "temperature": 0.1,  # 低温度，精确推断
                },
            )
            _check_quota_error(resp.status_code, resp.text, "DeepSeek")
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"].strip()
            content = content.strip("`").strip()
            if content.startswith("json"):
                content = content[4:].strip()
            result = json.loads(content)
            return result
    except QuotaExhaustedError:
        raise
    except Exception as e:
        print(f"[intent_router] DeepSeek classify failed: {e}")
        # 回退到正则
        keyword_match = _registry.keyword_check(message)
        if keyword_match:
            return {"intent": keyword_match, "params": {}}
        return {"intent": "chat", "params": {}}
