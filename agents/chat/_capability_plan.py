"""Model-driven capability planning for a user turn.

This is intentionally semantic rather than keyword based. The result only
controls which existing tools the main agent must use; it never writes a user
answer or performs a side effect.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
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
    "needs_papers": False,
    "search_query": "",
    "image_query": "",
    "paper_author": "",
    "paper_year": 0,
    "paper_limit": 0,
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
    plan["paper_author"] = str(raw.get("paper_author") or "").strip()[:120]
    try:
        plan["paper_year"] = int(raw.get("paper_year") or 0)
        plan["paper_limit"] = max(0, min(10, int(raw.get("paper_limit") or 0)))
    except (TypeError, ValueError):
        plan["paper_year"] = 0
        plan["paper_limit"] = 0
    return plan


def parse_capability_plan(content: Any) -> dict[str, Any]:
    return _decode_capability_plan(content) or dict(DEFAULT_PLAN)


async def plan_capabilities(model, user_message: str) -> dict[str, Any]:
    today = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
    prompt = f"""你是能力路由器，只判断完成本轮用户请求需要哪些能力，不回答问题。当前北京时间日期是运行时得到的 {today}；“今天、今日、今年、最近 N 年”等相对时间必须据此解析并写入搜索查询，绝不能沿用训练数据、示例或旧会话里的日期。
返回严格 JSON：needs_web_search、needs_rich_answer、needs_images、needs_places、needs_map_action、needs_calendar_action、needs_meeting_action、needs_image_generation、needs_papers 为布尔值；search_query、image_query、paper_author 为字符串；paper_year、paper_limit 为整数。
判断原则：
- 这些字段只是给主模型的能力建议，绝不是工具开关；主模型始终可以自主决定是否搜索、使用多少素材以及怎样组织回答。
- 判断外部网页、图片等素材是否可能增进回答。稳定知识也可以搜索核实或补充视觉资料，但不能因为搜索结果存在，就要求主模型围绕网页逐条复述。
- rich_answer/images 表示富媒体素材可能有帮助，不规定最终版式；模型可以采用、穿插、重排或完全舍弃素材。
- 旅行目的地介绍、第一次去某城市、请介绍当地有什么好玩/好吃/值得去，回答天然会包含多个可到访点，所以 needs_places 和 needs_map_action 都必须为 true；不能因为用户没说“地图”就关掉地图能力。
- 单一地点的历史、文化或原理解说不需要 map_action，除非用户同时要求周边或路线。
- 用户要求新增/修改/删除行程日程才需要 calendar_action；仅说计划去某地不等于写日程。
- 创建会议需要 meeting_action；生成新图片需要 image_generation。若图片主体是现实中的具体人物、地点、产品、动物品种或其他需要外观准确的对象，同时设置 web_search 和 images，并用 image_query 描述该真实主体；纯幻想、抽象画面或用户已给参考图则不搜索。
- 搜索论文、文献、arXiv 或某研究方向的学术成果需要 papers；search_query 写论文主题。用户指定作者时 paper_author 使用其常见英文学术署名（如能确定），指定年份和数量时分别填写 paper_year、paper_limit；没有则为 0 或空字符串。
- 需要搜索时，search_query 改写成适合搜索引擎的简洁事实查询，不要保留“能不能、给我讲讲”等对话措辞；否则为空字符串。
- 用户明确询问“今天/今日”的新闻或进展时，search_query 必须包含上面的当前完整日期，并强调只要发布日期可核验为该日的内容；不能用“过去一周”或其他日期代替。
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
