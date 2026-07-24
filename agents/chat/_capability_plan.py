"""Model-driven capability planning for a user turn.

This is intentionally semantic rather than keyword based. The result only
controls which existing tools the main agent must use; it never writes a user
answer or performs a side effect.
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable


DEFAULT_PLAN = {
    "needs_clarification": False,
    "needs_web_search": False,
    "strict_today_only": False,
    "needs_rich_answer": False,
    "needs_images": False,
    "needs_places": False,
    "needs_route": False,
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


def required_tools_for_plan(plan: dict[str, Any]) -> tuple[str, ...]:
    """Turn the semantic plan into the shortest required capability chain.

    The routing decision remains model-driven.  This function only maps the
    planner's semantic booleans to existing Makers-native tools so the main
    model cannot claim that a map, calendar change, meeting, or generated image
    is ready without actually producing the corresponding UI action.
    """
    # Missing critical information is a terminal planning state for this turn.
    # Ask once with a structured card before spending search/provider budget or
    # attempting a side effect with guessed inputs.
    if bool(plan.get("needs_clarification")):
        return ("ask_user_clarification",)

    required: list[str] = []
    if bool(plan.get("needs_web_search")) or bool(plan.get("needs_papers")):
        required.append("rich_search")

    # The composite map tool verifies every model-selected place and prepares
    # the terminal map Action in one call.  For a single non-map location (most
    # commonly a calendar destination), retain the focused place lookup.
    if bool(plan.get("needs_route")):
        required.append("plan_route_between_places")
    elif bool(plan.get("needs_map_action")):
        required.append("recommend_places_on_map")
    elif bool(plan.get("needs_places")):
        required.append("search_places")

    if bool(plan.get("needs_calendar_action")):
        required.append("propose_calendar_changes")
    if bool(plan.get("needs_meeting_action")):
        required.append("propose_meeting")
    if bool(plan.get("needs_image_generation")):
        required.append("propose_image")
    return tuple(dict.fromkeys(required))


def required_tool_for_plan(plan: dict[str, Any]) -> str:
    """Backward-compatible first item of the semantic capability chain."""
    required = required_tools_for_plan(plan)
    return required[0] if required else ""


def media_enabled_for_plan(
    plan: dict[str, Any], image_limit: int, planner_timed_out: bool = False,
) -> bool:
    """Make reviewed media available for semantic web-search turns.

    The planner still decides whether external facts are needed and produces the
    merged query. Once it chooses web search, the same result may also provide
    reviewed image candidates unless the user set the image limit to zero. A
    distinct visual query still follows the planner; otherwise the fact response
    is reused and no second SearchPro request is added.
    """
    return int(image_limit) > 0 and bool(
        planner_timed_out or plan.get("needs_web_search") or plan.get("needs_images")
    )


def next_required_tool(
    required_tools: Iterable[str],
    used_tool_names: Iterable[str],
    allowed_tool_names: set[str],
) -> str:
    """Return the next available planner-required tool not used this turn."""
    used = set(used_tool_names)
    for name in required_tools:
        clean_name = str(name or "").strip()
        if clean_name and clean_name in allowed_tool_names and clean_name not in used:
            return clean_name
    return ""


async def plan_capabilities(model, user_message: str, memory_context: str = "") -> dict[str, Any]:
    today = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
    prompt = f"""你是能力路由器，只判断完成本轮用户请求需要哪些能力，不回答问题。当前北京时间日期是运行时得到的 {today}；“今天、今日、今年、最近 N 年”等相对时间必须据此解析并写入搜索查询，绝不能沿用训练数据、示例或旧会话里的日期。
返回严格 JSON：needs_clarification、needs_web_search、strict_today_only、needs_rich_answer、needs_images、needs_places、needs_route、needs_map_action、needs_calendar_action、needs_meeting_action、needs_image_generation、needs_papers 为布尔值；search_query、image_query、paper_author 为字符串；paper_year、paper_limit 为整数。
判断原则：
- 这些字段只是给主模型的能力建议，绝不是工具开关；主模型始终可以自主决定是否搜索、使用多少素材以及怎样组织回答。
- 只有缺失信息会阻断所有安全且有用的回答，或无法唯一确定将要执行的真实副作用对象时，needs_clarification=true，而且本轮其他能力全部设为 false。“不同偏好会改变结果”“知道后会更好”或用户尚未决定，都不足以触发澄清；只要能够基于不同合理假设给出至少两套不误导的方案，needs_clarification 必须为 false，并让主模型直接给出 2–3 套带假设与取舍的方案。这个判断必须泛化到任何主题和偏好，不能按某个任务类别套用固定问题。普通事实问答、存在低风险默认值时也不要澄清。澄清字段只能来自用户本轮明确目标、当前对话里尚未解决的条件、与本任务直接相关的安全长期记忆或当前可核验状态；不得套用某类任务常见的画像问卷，也不得因为“可能有帮助”就追加问题。已有上下文、可靠记忆、核实结果或其他必要字段能够推导的内容不要再问；记忆与本轮表达冲突或仍不确定时，以本轮表达为准。澄清卡只收齐继续执行所不可缺少的最少字段：有限候选优先单选/多选，能用是/否表达就用判断，只缺日期用 date、日期已知只缺时刻用 time、两者都缺才用 datetime，只有答案无法枚举时才用短文本；不要在长回答末尾再追问。
- 先语义判断是否需要外部事实。简单计算、脑筋急转弯、闲聊或模型可直接可靠回答的请求不搜索；时效事实、用户明确要求查证、需要来源或现实世界信息时搜索。
- 独立判断图片是否能明显加快理解。现实事件的新闻/近期进展综述，如果现场、人物、产品或实物图片能帮助用户区分各条进展，通常设置 needs_images=true；只有用户明确要极简文字、主题高度抽象或确实没有有意义视觉对象时才设为 false。地点、产品、动植物、历史实物等同理。不能机械地按“用户有没有说图片”判断。
- search_query 必须把完成目标所需的事实约束合并成一次高质量查询；不要拆成多个近义查询，也不要预留“第二次再搜”。近期进展综述要在同一查询中要求多个独立事件、可核验日期和可靠来源，避免只命中一条宽泛报道。image_query 只表达最能代表这些事实的视觉对象，可与事实搜索并发。
- rich_answer/images 表示富媒体素材可能有帮助，不规定最终版式；模型可以采用、穿插、重排或完全舍弃素材。
- 旅行目的地介绍、第一次去某城市、请介绍当地有什么好玩/好吃/值得去，回答天然会包含多个可到访点，所以 needs_places 和 needs_map_action 都必须为 true；不能因为用户没说“地图”就关掉地图能力。
- 单一地点的历史、文化或原理解说不需要 map_action，除非用户同时要求周边或路线。
- 用户询问两个地点之间“多远、多久、怎么走、打车多少钱”或明确要求道路路线时，needs_route=true。真实距离由地点与路线服务核验，不要为了距离本身设置 needs_web_search，也不要用网页结果估算；只有用户还要求沿途新闻、实时政策等额外事实时才同时设置 web_search。needs_route 已包含两个端点的地点核验，不必为了同一端点再额外设置 needs_places 或 map_action。
- 用户要求新增/修改/删除行程日程才需要 calendar_action；仅说计划去某地不等于写日程。
- 创建会议需要 meeting_action；生成新图片需要 image_generation。若图片主体是现实中的具体人物、地点、产品、动物品种或其他需要外观准确的对象，同时设置 web_search 和 images，并用 image_query 描述该真实主体；纯幻想、抽象画面或用户已给参考图则不搜索。
- 搜索论文、文献、arXiv 或某研究方向的学术成果需要 papers；search_query 写论文主题。用户指定作者时 paper_author 使用其常见英文学术署名（如能确定），指定年份和数量时分别填写 paper_year、paper_limit；没有则为 0 或空字符串。
- 需要搜索时，search_query 改写成适合搜索引擎的简洁事实查询，不要保留“能不能、给我讲讲”等对话措辞；否则为空字符串。
- 只有用户明确要求“今天/今日发生或发布的新闻、公告、进展”时，strict_today_only=true，search_query 必须包含上面的当前完整日期，并强调只要发布日期可核验为该日的内容；不能用“过去一周”或其他日期代替。
- “截至今天/截至目前的最新能力、现状、价格或对比”表示查询截止时间，不表示资料必须在今天发布；这类请求 strict_today_only=false，应检索截至当前日期可核验的最新官方资料并保留各自真实发布日期。
- 需要图片时，image_query 写成适合找到具体视觉素材的查询，包含主体和最有代表性的可视对象；否则为空字符串。
不要根据固定关键词机械匹配，要理解整句话的目标。只输出 JSON。"""
    safe_memory = str(memory_context or "").strip()[:4000]
    if safe_memory:
        prompt += (
            "\n以下是已过滤为非敏感的长期记忆。只在确实相关时用于个性化查询；"
            "它只能补足本轮已经需要的条件，不能据此创造新的澄清维度；"
            "带有犹豫、否定、备选或临时任务含义的内容不视为稳定偏好。"
            "不得把姓名、联系方式、精确地址、账号、证件、健康、财务或任何秘密写入外部搜索词。"
            f"\n{safe_memory}"
        )
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


async def plan_capabilities_bounded(
    model,
    user_message: str,
    memory_context: str = "",
    timeout_seconds: float = 6.0,
) -> tuple[dict[str, Any], bool]:
    """Run the semantic planner without letting it block the whole turn.

    A timeout does not replace semantic routing with keyword rules. The main
    chat model still receives the complete tool set and decides which tools to
    use; only the optional pre-plan and its forced-tool hints are omitted.
    """
    try:
        plan = await asyncio.wait_for(
            plan_capabilities(model, user_message, memory_context),
            timeout=max(0.01, float(timeout_seconds)),
        )
        return plan, False
    except asyncio.TimeoutError:
        return dict(DEFAULT_PLAN), True
