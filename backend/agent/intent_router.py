"""意图路由器：LLM 驱动的意图分类 + 技能调度。

流程：
1. 正则快速预检（0 次 API 调用）
2. 若正则高置信命中 → 直接返回对应技能
3. 否则 → LLM 分类（1 次 API 调用，支持主动检测）
4. 路由到对应技能的 suggest() 方法
"""
from __future__ import annotations

import json
from typing import Any

from agent import register_all_skills
from skills.base_skill import SkillRegistry, SkillResult

# 全局注册表
_registry = SkillRegistry()
_skills_registered = False


def _ensure_registered() -> None:
    global _skills_registered
    if not _skills_registered:
        register_all_skills(_registry)
        _skills_registered = True


async def route_message(
    message: str,
    session_id: str,
    history: list[str] | None = None,
) -> SkillResult:
    """分类用户意图并路由到对应技能。

    Returns:
        SkillResult: 包含 intent / mode / content / params 等
    """
    _ensure_registered()

    # 1. 正则快速预检
    keyword_match = _registry.keyword_check(message)

    # 2. LLM 分类（支持主动检测和参数提取）
    llm_result = await _llm_classify(message, history or [])

    intent = llm_result.get("intent", "chat")
    params = llm_result.get("params", {})
    suggestion_text = llm_result.get("suggestion", "")

    # 如果 LLM 返回 chat 但正则匹配了，用正则结果
    if intent == "chat" and keyword_match:
        intent = keyword_match
        params = {}
        suggestion_text = ""

    # 3. 路由到技能
    skill = _registry.get(intent)
    if skill:
        result = await skill.suggest(message, params)
        # 如果 LLM 生成了更好的建议文案，覆盖技能默认文案
        if suggestion_text and not params:
            result.content = suggestion_text
        return result

    # 4. 兜底：通用对话
    if suggestion_text:
        return SkillResult(
            intent="chat",
            mode="immediate",
            content=suggestion_text,
        )

    # 列出所有可用能力
    skill_list = "\n".join(
        f"- {s.icon} {s.description}" for s in _registry.all_skills()
    )
    return SkillResult(
        intent="chat",
        mode="immediate",
        content=f"我目前支持以下能力：\n\n{skill_list}\n\n你想做什么呢？",
    )


async def _llm_classify(message: str, history: list[str]) -> dict[str, Any]:
    """调用 LLM 进行意图分类。

    Returns:
        {"intent": "travel", "params": {...}, "suggestion": "..."}
    """
    _ensure_registered()

    try:
        from prompts.templates import INTENT_CLASSIFICATION_PROMPT
        from services.hunyuan_service import hunyuan_service, ApiNotConfiguredError
        from scenarios.scenario_type import ScenarioType

        skill_desc = _registry.build_llm_description()
        system_prompt = INTENT_CLASSIFICATION_PROMPT.replace("{{SKILLS}}", skill_desc)

        # 构造对话历史
        history_str = ""
        if history:
            history_str = "\n".join(history[-6:])

        user_content = f"用户消息：{message}"
        if history_str:
            user_content += f"\n\n对话历史：\n{history_str}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        result, _ = await hunyuan_service.chat_json(
            messages, "intent_router", ScenarioType.CHAT, max_tokens=300
        )
        return result

    except Exception as e:
        # LLM 不可用时，回退到正则
        print(f"[intent_router] LLM classify failed: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return {"intent": "chat", "params": {}, "suggestion": ""}
