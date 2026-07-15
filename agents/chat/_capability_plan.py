"""Model-driven capability planning for a user turn.

This is intentionally semantic rather than keyword based. The result only
controls which existing tools the main agent must use; it never writes a user
answer or performs a side effect.
"""

from __future__ import annotations

import json
import re
from typing import Any


DEFAULT_PLAN = {
    "needs_web_search": False,
    "needs_rich_answer": False,
    "needs_images": False,
    "needs_places": False,
    "needs_map_action": False,
    "needs_calendar_action": False,
    "needs_meeting_action": False,
    "needs_image_generation": False,
    "search_query": "",
    "image_query": "",
}

BOOLEAN_KEYS = tuple(key for key, value in DEFAULT_PLAN.items() if isinstance(value, bool))


def _text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            str(item.get("text") or "") for item in content if isinstance(item, dict)
        )
    return str(content or "")


def _decode_capability_plan(content: Any) -> dict[str, Any] | None:
    text = _text(content).strip()
    fenced = re.search(r"\{[\s\S]*\}", text)
    if fenced:
        text = fenced.group(0)
    try:
        raw = json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    plan = {key: bool(raw.get(key, False)) for key in BOOLEAN_KEYS}
    plan["search_query"] = str(raw.get("search_query") or "").strip()[:160]
    plan["image_query"] = str(raw.get("image_query") or "").strip()[:160]
    return plan


def parse_capability_plan(content: Any) -> dict[str, Any]:
    return _decode_capability_plan(content) or dict(DEFAULT_PLAN)


async def plan_capabilities(model, user_message: str) -> dict[str, Any]:
    prompt = """你是能力路由器，只判断完成本轮用户请求需要哪些能力，不回答问题。
返回严格 JSON：needs_web_search、needs_rich_answer、needs_images、needs_places、needs_map_action、needs_calendar_action、needs_meeting_action、needs_image_generation 为布尔值；search_query、image_query 为字符串。
判断原则：
- 时效信息、知识讲解、历史文化、事实核验需要 web_search；其中适合标题/时间线/表格/来源的解释需要 rich_answer，具体人物地点历史通常也需要 images。
- 旅行目的地介绍、第一次去某城市、请介绍当地有什么好玩/好吃/值得去，回答天然会包含多个可到访点，所以 needs_places 和 needs_map_action 都必须为 true；不能因为用户没说“地图”就关掉地图能力。
- 单一地点的历史、文化或原理解说不需要 map_action，除非用户同时要求周边或路线。
- 用户要求新增/修改/删除行程日程才需要 calendar_action；仅说计划去某地不等于写日程。
- 创建会议需要 meeting_action；生成新图片需要 image_generation。
- 需要搜索时，search_query 改写成适合搜索引擎的简洁事实查询，不要保留“能不能、给我讲讲”等对话措辞；否则为空字符串。
- 需要图片时，image_query 写成适合找到具体视觉素材的查询，包含主体和最有代表性的可视对象；否则为空字符串。
不要根据固定关键词机械匹配，要理解整句话的目标。只输出 JSON。"""
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": str(user_message or "")[:4000]},
    ]
    for _attempt in range(2):
        try:
            response = await model.ainvoke(messages)
            parsed = _decode_capability_plan(getattr(response, "content", ""))
            if parsed is not None:
                return parsed
        except Exception:
            continue
    return dict(DEFAULT_PLAN)
