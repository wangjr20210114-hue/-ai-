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

from pydantic import BaseModel, ConfigDict, Field


DEFAULT_PLAN = {
    "needs_clarification": False,
    "needs_web_search": False,
    "strict_today_only": False,
    "needs_rich_answer": False,
    "needs_images": False,
    "needs_places": False,
    "needs_nearby_places": False,
    "needs_route": False,
    "needs_map_action": False,
    "needs_calendar_action": False,
    "needs_meeting_action": False,
    "needs_workflow_action": False,
    "needs_image_generation": False,
    "needs_papers": False,
    "search_query": "",
    "image_query": "",
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
    needs_rich_answer: bool = False
    needs_images: bool = False
    needs_places: bool = False
    needs_nearby_places: bool = False
    needs_route: bool = False
    needs_map_action: bool = False
    needs_calendar_action: bool = False
    needs_meeting_action: bool = False
    needs_workflow_action: bool = False
    needs_image_generation: bool = False
    needs_papers: bool = False
    search_query: str = ""
    image_query: str = ""
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
    return plan


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
    return plan


async def plan_capabilities(
    model,
    user_message: str,
    memory_context: str = "",
    skill_state: str = "",
    location_context: str = "",
) -> dict[str, Any]:
    today = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
    prompt = f"""你是能力路由器，只判断完成本轮用户请求需要哪些能力，不回答问题。当前北京时间日期是运行时得到的 {today}；“今天、今日、今年、最近 N 年”等相对时间必须据此解析并写入搜索查询，绝不能沿用训练数据、示例或旧会话里的日期。
严格填写提供的结构化 schema，不要在字段外补充文字。
判断原则：
- 这些字段只是给主模型的能力建议，绝不是工具开关；主模型始终可以自主决定是否搜索、使用多少素材以及怎样组织回答。
- Skill 状态会在下方单独提供。先理解用户真正要完成的目标，再判断它是否不可替代地依赖某个已关闭 Skill；若是，blocked_skill 必须填写该 Skill 的精确 id，其他 needs_* 全部为 false，让主模型自然提醒用户开启。不得因为问题中出现日期、地点、图片等表面词语就机械判定依赖，也不得把可选的富媒体增强当成阻塞；只有缺少该能力就无法完成用户明确要求的最终结果时才阻塞。Skill 已开启或任务不依赖已关闭能力时 blocked_skill 为空字符串。
- 只有缺失信息会阻断所有安全且有用的回答，或无法唯一确定将要执行的真实副作用对象时，needs_clarification=true，而且本轮其他能力全部设为 false。“不同偏好会改变结果”“知道后会更好”或用户尚未决定，都不足以触发澄清；只要能够基于不同合理假设给出至少两套不误导的方案，needs_clarification 必须为 false，并让主模型直接给出 2–3 套带假设与取舍的方案。这个判断必须泛化到任何主题和偏好，不能按某个任务类别套用固定问题。普通事实问答、存在低风险默认值时也不要澄清。特别地，现实地点名称可能同名、缺少城市或有错字时，不得在调用地点服务之前设置 needs_clarification；应先设置 needs_places（路线则设置 needs_route），由地点工具基于真实结果执行“唯一候选直接采用、多个候选单选、无候选填空”。如果这个未核实地点属于日程新增或修改，无论你是否同时误判 needs_clarification，都必须设置 place_resolution_target=calendar；只有缺日期、时间、标题等非地点必要参数时 place_resolution_target 才保持 none。澄清字段只能来自用户本轮明确目标、当前对话里尚未解决的条件、与本任务直接相关的安全长期记忆或当前可核验状态；不得套用某类任务常见的画像问卷，也不得因为“可能有帮助”就追加问题。已有上下文、可靠记忆、核实结果或其他必要字段能够推导的内容不要再问；记忆与本轮表达冲突或仍不确定时，以本轮表达为准。澄清卡只收齐继续执行所不可缺少的最少字段：有限候选优先单选/多选，能用是/否表达就用判断，只缺日期用 date、日期已知只缺时刻用 time、两者都缺才用 datetime，只有答案无法枚举时才用短文本；不要在长回答末尾再追问。
- 先语义判断是否需要外部事实。简单计算、脑筋急转弯、闲聊或模型可直接可靠回答的请求不搜索；时效事实、用户明确要求查证、需要来源或现实世界信息时搜索。
- 独立判断图片是否能明显加快理解。现实事件的新闻/近期进展综述，如果现场、人物、产品或实物图片能帮助用户区分各条进展，通常设置 needs_images=true；只有用户明确要极简文字、主题高度抽象或确实没有有意义视觉对象时才设为 false。地点、产品、动植物、历史实物等同理。不能机械地按“用户有没有说图片”判断。
- search_query 必须把完成目标所需的事实约束合并成一次高质量查询；不要拆成多个近义查询，也不要预留“第二次再搜”。近期进展综述要在同一查询中要求多个独立事件、可核验日期和可靠来源，避免只命中一条宽泛报道。image_query 只表达最能代表这些事实的视觉对象，可与事实搜索并发。
- rich_answer/images 表示富媒体素材可能有帮助，不规定最终版式；模型可以采用、穿插、重排或完全舍弃素材。
- 旅行目的地介绍、第一次去某城市、请介绍当地有什么好玩/好吃/值得去，回答天然会包含多个可到访点，所以 needs_places 和 needs_map_action 都必须为 true；不能因为用户没说“地图”就关掉地图能力。
- 单一地点的历史、文化或原理解说不需要 map_action，除非用户同时要求周边或路线。
- 用户要找某个已知地点、当前位置或日程地点“附近/周边”的餐馆、早餐店、酒店、商店、景点等真实地点时，needs_nearby_places=true；该组合能力会复用工作区内已核实的参照地点并调用真实附近检索，同时生成仅含核实结果的地图。用户给出多个备选参照点时仍只需要这一项能力，主模型会把全部备选点一次交给组合工具，不能在规划阶段擅自缩成一个。不要仅为了发现附近地点设置 needs_web_search；只有用户还要求点评、营业时间、新闻等地图服务之外的时效事实时才同时设置 web_search。needs_nearby_places 已包含地点核验和地图 Action，不必再设置 needs_places 或 needs_map_action。
  - 用户询问两个地点之间“多远、多久、怎么走、打车多少钱”，明确要求道路路线，或给出出发地与一个/多个依次停靠地点并要求规划出行/行程时，needs_route=true。“我想去/带我去/怎么去某地”这类明确移动意图，即使只给了目的地，只要下方说明有新鲜且已授权的浏览器当前位置，也要设置 needs_route=true 并使用该位置作为隐式起点，不要追问起点。多段行程仍只调用一次路线能力，并严格保留用户给出的停靠顺序。真实距离由地点与路线服务核验，不要为了距离本身设置 needs_web_search，也不要用网页结果估算；只有用户还要求沿途新闻、实时政策等额外事实时才同时设置 web_search。needs_route 已包含全部端点与中途站的地点核验，不必为了同一批地点再额外设置 needs_places 或 map_action。
  - needs_route=true 时，route_stops 必须包含用户明确要求经过的全部文本地点，第一项通常是起点，最后一项是终点，中间项按原顺序保留，不能因为某个地点可能有多个候选而省略。若使用已授权当前位置作为隐式起点，不要把坐标或“当前位置”伪造为普通地点搜索词；只把用户说出的目的地/途经地写入 route_stops，并设置 route_uses_current_location=true。浏览器当前位置不可用时 route_uses_current_location=false，缺少起点且无法安全继续才需要澄清。普通地点写 query；“某参照点附近的某品牌/类别”拆成 query=品牌或类别、near_query=参照地点。对话中的“那个店、那里、这个酒店”等指代应结合提供的原始目标与上下文原样保留或解析，不得擅自删除。route_city 填已明确的共同城市，无法确定时填“全国”。非路线请求 route_stops 为空。
  - route_mode 只记录用户明确指定的出行方式：驾车=driving、公交/地铁/公共交通=transit、步行=walking、骑行/自行车=bicycling；用户未指定时填 default，由用户设置决定。不能把“怎么去”擅自理解成驾车。
  - route_strategy 只记录用户明确指定的路线取舍：明确只要最快填 least_time，明确费用最低或最省钱填 least_cost，明确“省时优先、时间相近时省钱”填 time_then_cost；未指定填 default，由用户设置和已学习的明确选择决定。
- 用户要求新增/修改/删除行程日程时需要 calendar_action。另一个主动服务例外是：用户给出了明确的未来日期或出发时刻，并要求规划包含多个有序站点的可执行行程时，如果日程 Skill 已开启，同时设置 needs_route=true 与 needs_calendar_action=true；路线核实后主动生成一张可编辑的日程确认提案，不要等用户再次询问能否写入。该提案只是等待确认，不能自动生效。若日程 Skill 关闭，这个主动增强不是完成路线的必要条件，不得设置 blocked_skill，也不得阻塞正常路线回答。仅说计划去某地且没有明确时刻，仍不等于写日程。
- 新增或修改日程时，只要用户给出了现实地点且本轮没有可唯一复用的已核实地点，就设置 place_resolution_target=calendar，并同时设置 needs_places=true，让地点核实先于 calendar_action；不得因为缺少城市、可能同名或疑似错字而提前设置 needs_clarification，也不得直接把自由文本地点或猜测的地点 ID 交给日程工具。地点工具会根据真实腾讯候选决定直接采用、单选或填空。没有待核实现实地点时 place_resolution_target=none。
- 创建会议需要 meeting_action；生成新图片需要 image_generation。若图片主体是现实中的具体人物、地点、产品、动物品种或其他需要外观准确的对象，同时设置 web_search 和 images，并用 image_query 描述该真实主体；纯幻想、抽象画面或用户已给参考图则不搜索。
- 用户明确要求建立跨时间、多步骤、会持续推进或定时主动触达的提醒流程时需要 workflow_action；单次提醒或普通日程仍使用 calendar_action，不能用多条日程冒充主动工作流。
- 搜索论文、文献、arXiv 或某研究方向的学术成果需要 papers；papers 会调用独立 arXiv 能力，不要求同时开启 web-search。只有用户还要求查网页、新闻、官方资料或跨来源综述时才额外设置 needs_web_search。search_query 写论文主题。用户指定作者时 paper_author 使用其常见英文学术署名（如能确定），指定年份和数量时分别填写 paper_year、paper_limit；没有则为 0 或空字符串。
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
            "\n以下是浏览器本轮提供的隐私受限位置状态。它只表示能否作为路线起点，"
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
            return _preserve_explicit_calendar_intent(parsed, user_message)
        # One-call compatibility for gateways that return a raw message but
        # fail LangChain's structured parser. Never retry the model.
        raw = response.get("raw") if isinstance(response, dict) else None
        parsed = _decode_capability_plan(getattr(raw, "content", ""))
        if parsed is not None:
            return _preserve_explicit_calendar_intent(parsed, user_message)
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
        return dict(DEFAULT_PLAN), True
