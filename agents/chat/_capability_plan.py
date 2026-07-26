"""Model-driven capability planning for a user turn.

This is intentionally semantic rather than keyword based. The result only
controls which existing tools the main agent must use; it never writes a user
answer or performs a side effect.
"""

from __future__ import annotations

import asyncio
import difflib
import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field


DEFAULT_PLAN = {
    "needs_clarification": False,
    "needs_web_search": False,
    "strict_today_only": False,
    "needs_images": False,
    "needs_places": False,
    "needs_current_location": False,
    "needs_nearby_places": False,
    "needs_route": False,
    "needs_map_action": False,
    "needs_calendar_action": False,
    "needs_calendar_context": False,
    "needs_meeting_action": False,
    "needs_workflow_action": False,
    "needs_image_generation": False,
    "needs_papers": False,
    "needs_deep_reasoning": False,
    "needs_followups": False,
    "needs_memory_extraction": False,
    "needs_opportunity_review": False,
    "use_memory_context": False,
    "search_query": "",
    "image_query": "",
    "nearby_query": "",
    "paper_author": "",
    "paper_year": 0,
    "paper_limit": 0,
    "blocked_skill": "",
    "route_stops": [],
    "route_city": "全国",
    "route_mode": "default",
    "route_strategy": "default",
    "route_uses_current_location": False,
    "place_resolution_target": "none",
}

BOOLEAN_KEYS = tuple(key for key, value in DEFAULT_PLAN.items() if isinstance(value, bool))
KNOWN_SKILLS = {
    "web-search",
    "vision",
    "image-studio",
    "maps",
    "calendar",
    "proactive-agent",
    "paper-reading",
    "tencent-meeting",
}

class PlannedRouteStop(BaseModel):
    """One user-specified stop preserved verbatim and in user order."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(
        default="",
        description=(
            "The standalone place name or dialogue reference for this stop. "
            "The first item is always the origin and the last item the destination."
        ),
    )
    near_query: str = Field(
        default="",
        description=(
            "The separate anchor place only when query is a category or brand "
            "described as near another place; otherwise empty."
        ),
    )


class CapabilityPlan(BaseModel):
    """Validated semantic plan returned by LangChain structured output."""

    model_config = ConfigDict(extra="forbid")

    needs_clarification: bool = False
    needs_web_search: bool = False
    strict_today_only: bool = False
    needs_images: bool = False
    needs_places: bool = False
    needs_current_location: bool = Field(
        default=False,
        description=(
            "True when the user directly asks where they currently are or asks "
            "the assistant to identify the fresh browser location."
        ),
    )
    needs_nearby_places: bool = False
    needs_route: bool = False
    needs_map_action: bool = False
    needs_calendar_action: bool = False
    needs_calendar_context: bool = Field(
        default=False,
        description=(
            "True when answering requires reading the user's current schedules, "
            "including calendar create, update, delete, conflict, or agenda questions."
        ),
    )
    needs_meeting_action: bool = False
    needs_workflow_action: bool = False
    needs_image_generation: bool = False
    needs_papers: bool = False
    needs_deep_reasoning: bool = Field(
        default=False,
        description=(
            "True only for genuinely multi-step open-ended reasoning. Fixed JSON, "
            "tool arguments, routing, acknowledgements, and ordinary chat use Flash."
        ),
    )
    needs_followups: bool = Field(
        default=False,
        description="True only when suggested next questions add concrete user value.",
    )
    needs_memory_extraction: bool = Field(
        default=False,
        description=(
            "True only when the user explicitly states a durable non-sensitive "
            "preference or fact that may help future turns."
        ),
    )
    needs_opportunity_review: bool = Field(
        default=False,
        description=(
            "True only when the completed turn may justify a useful proactive "
            "next-step notification and proactive-agent is enabled."
        ),
    )
    use_memory_context: bool = Field(
        default=False,
        description=(
            "True only when confirmed long-term memory is directly relevant to "
            "the current request."
        ),
    )
    search_query: str = ""
    image_query: str = ""
    nearby_query: str = Field(
        default="",
        description=(
            "For a nearby-place request, the short provider category to find, "
            "such as 餐厅、景点、咖啡馆、酒店. Empty otherwise."
        ),
    )
    paper_author: str = ""
    paper_year: int = 0
    paper_limit: int = 0
    blocked_skill: str = Field(default="", description="Exact disabled Skill id or empty")
    route_stops: list[PlannedRouteStop] = Field(
        default_factory=list,
        description=(
            "For a route request, every explicitly requested stop in exact order. "
            "Never omit the origin, intermediate stops, or destination. Empty otherwise."
        ),
    )
    route_city: str = Field(
        default="全国",
        description="Explicit city shared by the route stops, or 全国 when not established",
    )
    route_mode: str = Field(
        default="default",
        description=(
            "Explicit travel mode: driving, transit, walking, or bicycling. "
            "Use default when the user did not specify one."
        ),
    )
    route_strategy: str = Field(
        default="default",
        description=(
            "Explicit route preference: time_then_cost, least_time, or least_cost. "
            "Use default when the user did not state a preference."
        ),
    )
    route_uses_current_location: bool = Field(
        default=False,
        description=(
            "True only when a fresh, user-authorized browser location is available "
            "and should be used as the implicit origin."
        ),
    )
    place_resolution_target: str = Field(
        default="none",
        description=(
            "Set to calendar when an unverified real-world place belongs to a "
            "calendar create/update request, even if the place is misspelled, "
            "ambiguous, or lacks a city. Otherwise none."
        ),
    )


def _text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            str(item.get("text") or "") for item in content if isinstance(item, dict)
        )
    return str(content or "")


def _decode_capability_plan(content: Any) -> dict[str, Any] | None:
    if isinstance(content, BaseModel):
        raw = content.model_dump()
    elif isinstance(content, dict):
        raw = content
    else:
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
    plan["nearby_query"] = str(raw.get("nearby_query") or "").strip()[:80]
    plan["paper_author"] = str(raw.get("paper_author") or "").strip()[:120]
    blocked_skill = str(raw.get("blocked_skill") or "").strip()
    plan["blocked_skill"] = blocked_skill if blocked_skill in KNOWN_SKILLS else ""
    try:
        plan["paper_year"] = int(raw.get("paper_year") or 0)
        plan["paper_limit"] = max(0, min(10, int(raw.get("paper_limit") or 0)))
    except (TypeError, ValueError):
        plan["paper_year"] = 0
        plan["paper_limit"] = 0
    route_stops: list[dict[str, str]] = []
    for item in raw.get("route_stops") or []:
        if isinstance(item, BaseModel):
            item = item.model_dump()
        if not isinstance(item, dict):
            continue
        query = str(item.get("query") or "").strip()[:160]
        near_query = str(item.get("near_query") or "").strip()[:160]
        if query:
            route_stops.append({"query": query, "near_query": near_query})
        if len(route_stops) >= 12:
            break
    plan["route_stops"] = route_stops if plan.get("needs_route") else []
    plan["route_city"] = str(raw.get("route_city") or "全国").strip()[:80] or "全国"
    route_mode = str(raw.get("route_mode") or "default").strip().lower()
    plan["route_mode"] = route_mode if route_mode in {
        "default", "driving", "transit", "walking", "bicycling",
    } else "default"
    route_strategy = str(raw.get("route_strategy") or "default").strip().lower()
    plan["route_strategy"] = route_strategy if route_strategy in {
        "default", "time_then_cost", "least_time", "least_cost",
    } else "default"
    plan["route_uses_current_location"] = bool(
        plan.get("needs_route") and raw.get("route_uses_current_location")
    )
    place_resolution_target = str(
        raw.get("place_resolution_target") or "none"
    ).strip().lower()
    plan["place_resolution_target"] = (
        place_resolution_target
        if place_resolution_target in {"none", "calendar"}
        else "none"
    )
    if plan.get("needs_calendar_action"):
        plan["needs_calendar_context"] = True
    if not plan.get("needs_nearby_places"):
        plan["nearby_query"] = ""
    # A real-world place ambiguity is resolvable only after provider lookup.
    # Restore the deterministic tool chain even if the semantic planner also
    # marked generic clarification. Missing dates/times keep target=none and
    # therefore remain genuine clarification blockers.
    if plan["place_resolution_target"] == "calendar":
        plan["needs_clarification"] = False
        plan["needs_places"] = True
        plan["needs_calendar_action"] = True
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
    # A disabled Skill is a terminal semantic planning state. The LLM planner,
    # not a keyword rule or business handler, decides whether the goal truly
    # depends on that Skill.
    if str(plan.get("blocked_skill") or "").strip():
        return ()

    # Missing critical information is a terminal planning state for this turn.
    # Ask once with a structured card before spending search/provider budget or
    # attempting a side effect with guessed inputs.
    if bool(plan.get("needs_clarification")):
        return ("ask_user_clarification",)

    required: list[str] = []
    if bool(plan.get("needs_web_search")):
        required.append("rich_search")
    if bool(plan.get("needs_current_location")):
        required.append("get_current_location")

    # The composite map tool verifies every model-selected place and prepares
    # the terminal map Action in one call.  For a single non-map location (most
    # commonly a calendar destination), retain the focused place lookup.
    if bool(plan.get("needs_route")):
        required.append("plan_route_between_places")
    elif bool(plan.get("needs_nearby_places")):
        required.append("recommend_nearby_places_on_map")
    elif bool(plan.get("needs_map_action")):
        required.append("recommend_places_on_map")
    elif bool(plan.get("needs_places")):
        required.append("search_places")

    if bool(plan.get("needs_calendar_action")):
        required.append("propose_calendar_changes")
    if bool(plan.get("needs_meeting_action")):
        required.append("propose_meeting")
    if bool(plan.get("needs_workflow_action")):
        required.append("propose_workflow")
    if bool(plan.get("needs_image_generation")):
        required.append("propose_image")
    if bool(plan.get("needs_papers")):
        required.append("search_arxiv")
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


def _preserve_explicit_calendar_intent(
    plan: dict[str, Any],
    user_message: str,
) -> dict[str, Any]:
    """Keep an unmistakable calendar request in a multi-tool plan."""
    if str(plan.get("blocked_skill") or "").strip():
        return plan
    normalized = "".join(str(user_message or "").lower().split())
    explicit_phrases = (
        "日程提案",
        "日历提案",
        "写入日程",
        "加入日程",
        "添加到日程",
        "创建日程",
        "新增日程",
        "calendarproposal",
        "addtomycalendar",
        "addtocalendar",
        "createacalendarevent",
    )
    if any(phrase in normalized for phrase in explicit_phrases):
        plan["needs_calendar_action"] = True
        plan["needs_calendar_context"] = True
    return plan


def explicit_location_intent(user_message: str) -> str:
    """Return a narrow, high-confidence browser-location intent."""
    normalized = "".join(str(user_message or "").lower().split())
    direct_location = bool(
        re.fullmatch(
            r"(?:请)?(?:告诉我)?我(?:现在|当前)?(?:具体)?在哪(?:里|儿)?[？?。！!]*",
            normalized,
        )
        or re.fullmatch(
            r"(?:请)?(?:告诉我)?(?:我的)?当前位置(?:是|在哪(?:里|儿)?)?[？?。！!]*",
            normalized,
        )
        or re.fullmatch(
            r"(?:你)?(?:知道|能看到|能读到|拿到)(?:我|我的)?(?:当前)?位置(?:吗)?[？?。！!]*",
            normalized,
        )
    )
    if direct_location:
        return "current"
    first_person_nearby = bool(
        re.search(r"(?:我|这|当前位置|当前地点)(?:这边|这里|这儿)?(?:附近|周边)", normalized)
        or re.match(r"(?:这|我这|这里|这儿)?附近(?:有|哪|找|推荐|什么)", normalized)
    )
    place_discovery = bool(re.search(
        r"(?:有什么|有没有|哪里有|哪儿有|找|推荐|好吃|好玩|餐|店|商场|"
        r"公园|景点|酒店|咖啡|超市|医院|厕所|充电)",
        normalized,
    ))
    return "nearby" if first_person_nearby and place_discovery else ""


def explicit_nearby_query(user_message: str) -> str:
    """Return a conservative provider category for obvious nearby requests."""
    normalized = "".join(str(user_message or "").lower().split())
    categories = (
        (("好吃", "美食", "吃饭", "餐厅", "饭店", "餐馆", "小吃"), "餐厅"),
        (("咖啡",), "咖啡馆"),
        (("好玩", "景点", "游玩"), "景点"),
        (("公园",), "公园"),
        (("酒店", "宾馆", "住宿"), "酒店"),
        (("商场", "购物"), "商场"),
        (("超市",), "超市"),
        (("医院",), "医院"),
        (("厕所", "卫生间"), "公共厕所"),
        (("充电",), "充电站"),
    )
    for terms, category in categories:
        if any(term in normalized for term in terms):
            return category
    return ""


def explicit_route_destination(user_message: str) -> str:
    """Extract only a complete, single-destination movement command."""
    normalized = " ".join(str(user_message or "").strip().split())
    match = re.fullmatch(
        r"(?:请)?(?:带我去|我想去|我要去|怎么去|如何去|导航到|导航去)"
        r"(?P<destination>[^？?。！!\n]{1,80})[？?。！!]*",
        normalized,
    )
    if not match:
        return ""
    destination = match.group("destination").strip(" ，,")
    if destination.startswith((
        "理解", "学习", "掌握", "实现", "处理", "解决", "解释", "分析", "使用",
    )):
        return ""
    return destination


def _preserve_explicit_location_intent(
    plan: dict[str, Any],
    user_message: str,
) -> dict[str, Any]:
    """Repair only unmistakable first-person location requests.

    The semantic planner remains responsible for general map routing. These
    narrow guards protect privacy and product truth when a fast model times out
    or drops a single boolean: the main model must not improvise an answer to
    "where am I" or a current-position nearby search without using map tools.
    """
    if str(plan.get("blocked_skill") or "").strip():
        return plan
    intent = explicit_location_intent(user_message)
    if intent == "current":
        plan["needs_clarification"] = False
        plan["needs_current_location"] = True
        return plan

    if intent == "nearby" and not plan.get("needs_route"):
        plan["needs_clarification"] = False
        plan["needs_current_location"] = False
        plan["needs_nearby_places"] = True
        plan["needs_places"] = False
        plan["needs_map_action"] = False
        if not str(plan.get("nearby_query") or "").strip():
            plan["nearby_query"] = explicit_nearby_query(user_message)
    return plan


def _restore_literal_route_queries(
    plan: dict[str, Any],
    user_message: str,
) -> dict[str, Any]:
    """Restore a near-identical place spelling from the user's own text.

    Structured-output models occasionally normalize an obvious typo while
    copying route stops. That would bypass the provider-backed correction
    contract. This post-validation does not guess a place: it only replaces a
    planned query with a same-length, high-similarity substring that visibly
    occurs in the current user message. Tencent still decides whether it is a
    valid correction, an ambiguity, or no match.
    """
    if not plan.get("needs_route") or not plan.get("route_stops"):
        return plan
    source = str(user_message or "")

    def literal(value: str) -> str:
        query = str(value or "").strip()
        if not query or query in source:
            return query
        # Limit this repair to compact CJK place tokens. Dialogue references,
        # long addresses and Latin names keep the semantic planner's value.
        if (
            not 2 <= len(query) <= 24
            or not re.fullmatch(r"[\w\u4e00-\u9fff]+", query)
            or not re.search(r"[\u4e00-\u9fff]", query)
        ):
            return query
        candidates = []
        for chunk_match in re.finditer(r"[\w\u4e00-\u9fff]+", source):
            chunk = chunk_match.group(0)
            if len(chunk) < len(query):
                continue
            for index in range(len(chunk) - len(query) + 1):
                candidate = chunk[index:index + len(query)]
                score = difflib.SequenceMatcher(None, query, candidate).ratio()
                aligned = sum(
                    left == right for left, right in zip(query, candidate)
                ) / len(query)
                candidates.append((
                    score,
                    aligned,
                    chunk_match.start() + index,
                    candidate,
                ))
        if not candidates:
            return query
        score, _aligned, _position, candidate = max(
            candidates,
            key=lambda item: (item[0], item[1], -item[2]),
        )
        threshold = 0.64 if len(query) == 3 else 0.72
        return candidate if score >= threshold else query

    plan["route_stops"] = [
        {
            "query": literal(str(stop.get("query") or "")),
            "near_query": literal(str(stop.get("near_query") or "")),
        }
        for stop in plan.get("route_stops") or []
        if isinstance(stop, dict) and str(stop.get("query") or "").strip()
    ][:12]
    return plan


def _finalize_plan(plan: dict[str, Any], user_message: str) -> dict[str, Any]:
    return _restore_literal_route_queries(
        _preserve_explicit_location_intent(
            _preserve_explicit_calendar_intent(plan, user_message),
            user_message,
        ),
        user_message,
    )


def _linked_trip_fallback(user_message: str) -> dict[str, Any]:
    """Preserve an unmistakable route→calendar chain after planner failure."""
    plan = _preserve_explicit_calendar_intent(
        dict(DEFAULT_PLAN), user_message,
    )
    if not plan["needs_calendar_action"]:
        return plan
    normalized = "".join(str(user_message or "").lower().split())
    route_subject = any(term in normalized for term in (
        "路线", "路程", "多站行程", "站间",
    ))
    route_action = any(term in normalized for term in (
        "规划", "怎么走", "如何走", "导航", "出发",
    ))
    route_negated = any(term in normalized for term in (
        "不要规划路线", "无需规划路线", "不需要规划路线",
        "不用规划路线", "只要日程提案",
    ))
    if route_subject and route_action and not route_negated:
        plan["needs_route"] = True
    return _finalize_plan(plan, user_message)


def planner_prompt_topics(user_message: str) -> tuple[str, ...]:
    """Select prompt detail, never the final capability decision.

    The compact semantic index remains present for every request, so an
    unfamiliar phrasing can still select any Skill. These broad signals only
    decide which operational edge cases are worth expanding in the prompt.
    """
    text = str(user_message or "").casefold()
    compact = "".join(text.split())
    topics: list[str] = ["core"]
    topic_patterns = {
        "web": (
            r"最新|今天|今日|新闻|进展|价格|查证|来源|搜索|检索|官网|网页|链接|"
            r"latest|news|search|source|price|current"
        ),
        "maps": (
            r"位置|附近|周边|地点|地图|路线|路程|导航|怎么去|多远|多久|打车|"
            r"公交|地铁|步行|骑行|景点|餐厅|酒店|商场|公园|旅行|行程|"
            r"location|nearby|map|route|drive|transit|walk|bike|travel"
        ),
        "calendar": (
            r"日程|日历|安排|议程|提醒|几点|上午|下午|今晚|明天|后天|"
            r"创建|新增|修改|删除|改到|推迟|提前|calendar|schedule|agenda|remind"
        ),
        "image": (
            r"图片|照片|图像|画一|画张|生图|生成图|海报|插画|视觉|"
            r"附图|这张图|image|photo|draw|poster|illustration"
        ),
        "paper": (
            r"论文|文献|学术|研究成果|arxiv|paper|literature|research"
        ),
        "meeting": (
            r"会议|开会|腾讯会议|视频会|线上会|meeting|conference"
        ),
        "proactive": (
            r"工作流|持续|每隔|定时|自动提醒|分步骤|长期跟进|主动通知|"
            r"workflow|recurring|proactive|followup"
        ),
    }
    for topic, pattern in topic_patterns.items():
        if re.search(pattern, compact, re.I):
            topics.append(topic)
    return tuple(topics)


PLANNER_PROMPT_DETAILS = {
    "web": (
        "【联网搜索】时效事实、用户要求查证或来源时 needs_web_search=true；"
        "search_query 合并为一次简洁事实查询。只有明确要求今天发布的内容才设 "
        "strict_today_only=true。图片确实帮助理解时再设 needs_images 并填写 image_query。"
    ),
    "maps": (
        "【地图与路线】直接问当前位置用 needs_current_location；周边商家只用 "
        "needs_nearby_places 并填写 nearby_query；目的地介绍/多地点推荐用 "
        "needs_places+needs_map_action；真实道路距离、耗时、费用或有序停靠用 needs_route。"
        "route_stops 逐字、按原顺序保留，不得在规划器中纠错、改名或选择分店；"
        "错字/同名交给腾讯地点服务处理，不得提前澄清。"
        "浏览器有新鲜位置且用户没给起点时 route_uses_current_location=true。"
    ),
    "calendar": (
        "【日程】只读/汇总当前日程用 needs_calendar_context；新增、修改、删除还要 "
        "needs_calendar_action。现实地点未核实时先 needs_places 且 "
        "place_resolution_target=calendar。明确未来时刻的多站可执行行程在日程 Skill "
        "开启时同时选择 route、calendar_context、calendar_action。"
    ),
    "image": (
        "【视觉与生图】生成新图片用 needs_image_generation。现实主体需要外观准确且用户"
        "没有参考图时，才同时选择 web_search+images；纯幻想、抽象画面或已有附图不搜索。"
    ),
    "paper": (
        "【论文】检索论文、文献或 arXiv 用 needs_papers，search_query 写研究主题；"
        "只有还要求普通网页、新闻或跨来源综述时才同时 web_search。作者、年份、数量分别"
        "写入 paper_author、paper_year、paper_limit。"
    ),
    "meeting": (
        "【会议】创建腾讯会议用 needs_meeting_action；会议依赖日程 Skill。只创建普通"
        "日程而不需要会议链接时不要选择 meeting。"
    ),
    "proactive": (
        "【主动服务】跨时间、多步骤、持续推进或定时主动触达用 needs_workflow_action；"
        "单次提醒仍是 calendar_action。只有回答完成后确实可能产生有价值的主动下一步，"
        "才设 needs_opportunity_review。"
    ),
}


def fallback_tools_for_prompt_topics(user_message: str) -> tuple[str, ...]:
    """Bound the recovery tool surface when the semantic router times out."""
    topic_tools = {
        "web": ("rich_search",),
        "maps": (
            "get_current_location",
            "search_places",
            "recommend_nearby_places_on_map",
            "recommend_places_on_map",
            "plan_route_between_places",
        ),
        "calendar": ("search_places", "propose_calendar_changes"),
        "image": ("propose_image", "rich_search"),
        "paper": ("rich_search", "search_arxiv"),
        "meeting": ("propose_meeting",),
        "proactive": ("propose_workflow",),
    }
    names: list[str] = []
    for topic in planner_prompt_topics(user_message):
        names.extend(topic_tools.get(topic, ()))
    return tuple(dict.fromkeys(names))


async def plan_capabilities(
    model,
    user_message: str,
    memory_context: str = "",
    skill_state: str = "",
    location_context: str = "",
) -> dict[str, Any]:
    today = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
    prompt = f"""你是 FLORIS 能力路由器，只填写给定 schema，不回答用户。当前北京时间日期：{today}。
总则：
- 理解完整目标，可同时选择多个能力；非必要字段保持默认值。blocked_skill 只填用户目标不可替代地依赖、且运行时明确关闭的 Skill id；可选增强关闭时不要阻塞。
- 只有缺失信息会阻断所有安全有用结果，或真实副作用对象无法唯一确定时，才设置 needs_clarification=true，并把其他 needs_* 设为 false。偏好未决定时直接交给主模型给方案，不要澄清。
- 用户只是探索思路、比较假设方案，且目的地、预算、同行或节奏尚未决定时，不需要外部事实、地点核验或地图；保持所有 needs_* 为 false，让主模型直接给 2–3 套假设方案。只有用户要求当前信息、来源、真实地点推荐或可执行路线时才选择相应能力。
- 现实地点可能有错字、同名或缺城市时，不得在调用地点服务之前设置 needs_clarification。先选择地点/路线能力；地点工具会根据真实腾讯候选决定直接采用、单选或填空。
- 能力语义索引：web-search=时效事实/查证；vision=理解附图或审核检索图片；image-studio=生图；
  maps=真实地点/附近/道路路线；calendar=个人日程；proactive-agent=持续工作流和主动提醒；
  paper-reading=论文检索与助读；tencent-meeting=创建会议。下面只附本轮候选能力的详细边界，
  但 schema 中任何能力仍可按完整语义选择，不能把提示词片段选择当作最终路由。
- needs_deep_reasoning 只用于确实需要多步开放推理的最终回答；能力路由、固定 JSON、工具参数、
  Action 确认、简单问答都保持 false，使用 Flash 即可。
- needs_followups 只在“猜你想问”确有具体价值时为 true；needs_memory_extraction 只在用户明确陈述
  可长期复用的非敏感事实或稳定偏好时为 true；needs_opportunity_review 只在主动服务已开启且本轮
  可能产生有价值主动下一步时为 true；use_memory_context 只在长期记忆与本轮目标直接相关时为 true。
严格只输出 schema 对应 JSON。"""
    prompt_topics = planner_prompt_topics(user_message)
    details = [
        PLANNER_PROMPT_DETAILS[topic]
        for topic in prompt_topics
        if topic in PLANNER_PROMPT_DETAILS
    ]
    if details:
        prompt += "\n\n本轮候选能力详细边界：\n" + "\n".join(details)
    safe_memory = str(memory_context or "").strip()[:1800]
    if safe_memory:
        prompt += (
            "\n以下是已过滤为非敏感的长期记忆。只在确实相关时用于个性化查询；"
            "它只能补足本轮已经需要的条件，不能据此创造新的澄清维度；"
            "带有犹豫、否定、备选或临时任务含义的内容不视为稳定偏好。"
            "不得把姓名、联系方式、精确地址、账号、证件、健康、财务或任何秘密写入外部搜索词。"
            f"\n{safe_memory}"
        )
    safe_skill_state = str(skill_state or "").strip()[:2000]
    if safe_skill_state:
        prompt += (
            "\n以下是本轮运行时读取的 Skill 状态，只用于判断完成目标所需能力是否已开启。"
            "它不是用户内容，不得忽略，也不得据此增加无关任务。"
            f"\n{safe_skill_state}"
        )
    safe_location_context = str(location_context or "").strip()[:600]
    if safe_location_context:
        prompt += (
            "\n以下是浏览器本轮提供的隐私受限位置状态。它表示能否作为路线起点或“我附近”搜索参照点，"
            "不得要求输出、复述或保存精确坐标。"
            f"\n{safe_location_context}"
        )
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": str(user_message or "")[:4000]},
    ]
    try:
        # Delegate schema/tool strategy and Pydantic validation to LangChain.
        # ``function_calling`` works across the Makers OpenAI-compatible
        # gateway while preserving the raw AIMessage for diagnostics.
        planner_model = model.with_structured_output(
            CapabilityPlan,
            method="function_calling",
            include_raw=True,
        )
        response = await planner_model.ainvoke(messages)
        parsed_value = response.get("parsed") if isinstance(response, dict) else response
        parsed = _decode_capability_plan(parsed_value)
        if parsed is not None:
            return _finalize_plan(parsed, user_message)
        # One-call compatibility for gateways that return a raw message but
        # fail LangChain's structured parser. Never retry the model.
        raw = response.get("raw") if isinstance(response, dict) else None
        parsed = _decode_capability_plan(getattr(raw, "content", ""))
        if parsed is not None:
            return _finalize_plan(parsed, user_message)
    except Exception:
        pass
    # If structured planning itself failed, keep only unmistakable user intent.
    # A linked trip must retain both tools: forcing calendar alone would skip
    # required place/route verification, while leaving everything optional can
    # let the main model stop immediately after the map action.
    return _linked_trip_fallback(user_message)


async def plan_capabilities_bounded(
    model,
    user_message: str,
    memory_context: str = "",
    skill_state: str = "",
    location_context: str = "",
    timeout_seconds: float = 6.0,
) -> tuple[dict[str, Any], bool]:
    """Run the semantic planner without letting it block the whole turn.

    A timeout does not replace semantic routing with keyword rules. The main
    chat model still receives the complete tool set and decides which tools to
    use; only the optional pre-plan and its forced-tool hints are omitted.
    """
    try:
        plan = await asyncio.wait_for(
            plan_capabilities(
                model, user_message, memory_context, skill_state, location_context,
            ),
            timeout=max(0.01, float(timeout_seconds)),
        )
        return plan, False
    except asyncio.TimeoutError:
        return _finalize_plan(dict(DEFAULT_PLAN), user_message), True
