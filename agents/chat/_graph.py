"""LangGraph state graph backed by Makers checkpointer and store adapters."""

from typing import Iterable, Literal
import json
import logging
import uuid

from langchain_core.messages import AIMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from ._history import bounded_history
from ._protocol import action_fallback_content, dsml_tool_calls, public_content
from ._capability_plan import next_required_tool


TOOL_FAILURE_MESSAGE = (
    "工具暂时没有完成。请基于已经获得的信息向用户说明限制，"
    "不要假装操作成功，也不要重复调用同一工具。"
)

# These tools already accept a batch, a composite request, or one complete
# side-effect proposal. Calling the same capability again in one logical turn
# is therefore retry churn, not additional reasoning. The LLM still plans the
# tool and its arguments; this is only a runtime safety budget.
TURN_SINGLE_USE_TOOLS = {
    "rich_search",
    "search_places",
    "search_places_batch",
    "plan_route_between_places",
    "prepare_map_recommendation",
    "recommend_places_on_map",
    "recommend_nearby_places_on_map",
    "propose_calendar_changes",
    "propose_meeting",
    "propose_image",
    "search_arxiv",
    "ask_user_clarification",
}

SKILL_DISPLAY_NAMES = {
    "web-search": {"zh-CN": "联网搜索", "zh-TW": "聯網搜尋", "en": "Web Search"},
    "vision": {"zh-CN": "视觉理解", "zh-TW": "視覺理解", "en": "Vision"},
    "image-studio": {"zh-CN": "图片工坊", "zh-TW": "圖片工坊", "en": "Image Studio"},
    "maps": {"zh-CN": "地图", "zh-TW": "地圖", "en": "Maps"},
    "calendar": {"zh-CN": "日程管理", "zh-TW": "日程管理", "en": "Calendar"},
    "proactive-agent": {"zh-CN": "主动式 Agent", "zh-TW": "主動式 Agent", "en": "Proactive Agent"},
    "paper-reading": {"zh-CN": "论文阅读", "zh-TW": "論文閱讀", "en": "Paper Reading"},
    "tencent-meeting": {"zh-CN": "腾讯会议", "zh-TW": "騰訊會議", "en": "Tencent Meeting"},
}

TOOL_CAPABILITIES = {
    "rich_search": "web-search",
    "collect_page_images": "web-search",
    "analyze_images_parallel": "vision",
    "search_places": "maps",
    "search_places_batch": "maps",
    "plan_route_between_places": "maps",
    "prepare_map_recommendation": "maps",
    "recommend_places_on_map": "maps",
    "recommend_nearby_places_on_map": "maps",
    "propose_calendar_changes": "calendar",
    "propose_meeting": "tencent-meeting",
    "propose_workflow": "proactive-agent",
    "propose_image": "image-studio",
    "search_arxiv": "paper-reading",
}


def _capability_names(capability_ids: Iterable[str], response_language: str) -> str:
    language = response_language if response_language in {"zh-CN", "zh-TW", "en"} else "zh-CN"
    names = []
    for capability_id in capability_ids:
        skill_id = TOOL_CAPABILITIES.get(capability_id, capability_id)
        localized = SKILL_DISPLAY_NAMES.get(skill_id, {}).get(language)
        name = localized or SKILL_DISPLAY_NAMES.get(skill_id, {}).get("zh-CN") or "对应"
        if name not in names:
            names.append(name)
    separator = ", " if language == "en" else "、"
    return separator.join(names) or ("the required" if language == "en" else "对应")


def blocked_capability_response(
    capability_ids: Iterable[str],
    response_language: str = "zh-CN",
    *,
    configured: bool = False,
) -> str:
    """Return one truthful terminal response after the LLM planner finds a blocked capability."""
    names = _capability_names(capability_ids, response_language)
    if response_language == "en":
        state = "is not enabled or configured" if configured else "is currently disabled"
        next_step = (
            "Enable the relevant Skill or finish connecting its external provider, then try again."
            if configured
            else "Enable it in the Skills marketplace, then try again."
        )
        return (
            f"This request requires {names}, but that capability {state}. "
            "Nothing was executed, and no card, proposal, or result was created. "
            f"{next_step}"
        )
    if response_language == "zh-TW":
        state = "尚未開啟或完成設定" if configured else "目前處於關閉狀態"
        next_step = "請到 Skills 廣場開啟相應能力或完成外部連線後再試。" if configured else "請到 Skills 廣場開啟後再試。"
        return (
            f"這次請求需要「{names}」能力，但它{state}，所以我沒有執行，"
            f"也沒有產生任何卡片、提案或結果。{next_step}"
        )
    state = "尚未开启或完成配置" if configured else "当前处于关闭状态"
    next_step = "请到 Skills 广场开启相应能力或完成外部连接后再试。" if configured else "请到 Skills 广场开启后再试。"
    suffix = "喵。" if response_language == "cat-cute" else "。"
    return (
        f"这次请求需要「{names}」能力，但它{state}，所以我没有执行，"
        f"也没有生成任何卡片、提案或结果。{next_step.rstrip('。')}{suffix}"
    )


def _logical_turn_messages(messages: Iterable) -> list:
    """Return messages belonging to the current user goal.

    A hidden structured-card answer continues its original goal, so it may
    cross one human boundary. Normal user messages always start a new turn.
    """
    logical_turn_messages: list = []
    crossed_clarification_answer = False
    for message in reversed(list(messages)):
        if getattr(message, "type", "") in {"human", "user"}:
            if not crossed_clarification_answer and _hidden_clarification_answer(message):
                crossed_clarification_answer = True
                continue
            break
        logical_turn_messages.append(message)
    return logical_turn_messages


def action_completion_fallback(messages: Iterable) -> str:
    """Return prose only for an Action that was actually created this turn.

    Looking only at the called tool name is unsafe: ToolNode records a
    ToolMessage even when argument validation or a provider call failed. That
    previously let a failed calendar proposal claim that a confirmation card
    was ready although no durable Action existed.
    """
    actions: list[dict] = []
    workflow_ready = False
    for message in reversed(_logical_turn_messages(messages)):
        if getattr(message, "type", "") != "tool":
            continue
        try:
            payload = json.loads(str(getattr(message, "content", "") or ""))
        except (TypeError, json.JSONDecodeError):
            continue
        if (
            isinstance(payload, dict)
            and payload.get("ui_action") in {
                "map_action", "calendar_action", "side_effect_action",
            }
            and isinstance(payload.get("action"), dict)
        ):
            actions.append(payload)
        workflow_ready = workflow_ready or (
            isinstance(payload, dict)
            and isinstance(payload.get("workflow_proposal"), dict)
        )
    if actions:
        return action_fallback_content(actions)
    if workflow_ready:
        return "主动工作流提案已加入主动提醒中心，请核对后再决定是否启用。"
    return ""


def tool_failure_fallback(messages: Iterable) -> str:
    """Expose the real validation failure if both model synthesis passes are empty."""
    for message in _logical_turn_messages(messages):
        if getattr(message, "type", "") != "tool":
            continue
        content = str(getattr(message, "content", "") or "").strip()
        if not content.startswith("操作未完成："):
            continue
        detail = content[len("操作未完成："):].split("。请自然说明", 1)[0].strip("。 ")
        if detail:
            return f"这次没有生成确认卡：{detail}。请检查后重试。"
    return ""


def tool_result_fallback(messages: Iterable) -> str:
    """Build a truthful minimal answer from successful place lookup output.

    This is used only after both the normal synthesis pass and its clean
    tool-free retry return no public prose. It prevents a completed provider
    lookup from collapsing into the generic empty-answer error.
    """
    logical_turn_messages = _logical_turn_messages(messages)

    places: list[dict] = []
    seen: set[str] = set()
    nearby_failure = False
    for message in logical_turn_messages:
        if getattr(message, "type", "") != "tool":
            continue
        tool_name = getattr(message, "name", "")
        if tool_name not in {
            "search_places",
            "search_places_batch",
            "recommend_nearby_places_on_map",
        }:
            continue
        raw_content = str(getattr(message, "content", "") or "")
        if tool_name == "recommend_nearby_places_on_map" and raw_content.startswith(
            ("操作未完成：", "工具暂时没有完成")
        ):
            nearby_failure = True
        try:
            payload = json.loads(raw_content)
        except (TypeError, json.JSONDecodeError):
            continue
        candidates = payload.get("places") if isinstance(payload, dict) else []
        if not isinstance(candidates, list):
            continue
        for place in candidates:
            if not isinstance(place, dict):
                continue
            name = str(place.get("name") or "").strip()
            address = str(place.get("address") or "").strip()
            if not name:
                continue
            identity = str(place.get("place_id") or f"{name}|{address}")
            if identity in seen:
                continue
            seen.add(identity)
            places.append({"name": name, "address": address})
        if places:
            break
    if not places and nearby_failure:
        return (
            "地点服务这次没有核实到符合条件的附近地点，我没有用不相关结果凑数。"
            "你可以扩大查找范围，或稍后点击重试。"
        )
    if not places:
        return ""
    visible = places[:5]
    lines = [
        f"- **{place['name']}**" + (f" — {place['address']}" if place["address"] else "")
        for place in visible
    ]
    suffix = f"\n\n另有 {len(places) - len(visible)} 个已核实结果。" if len(places) > len(visible) else ""
    return "我找到了这些经过地点服务核实的结果：\n\n" + "\n".join(lines) + suffix


def _tool_call_signature(tool_call: dict) -> str:
    name = str(tool_call.get("name") or "")
    args = tool_call.get("args") if isinstance(tool_call, dict) else {}
    return f"{name}:{json.dumps(args, ensure_ascii=False, sort_keys=True, default=str, separators=(',', ':'))}"


def _tool_failure_message(exc: Exception) -> str:
    """Keep safe validation feedback so the model can answer naturally."""
    if isinstance(exc, ValueError):
        detail = str(exc).strip()[:500] or "输入不符合要求"
        return f"操作未完成：{detail}。请自然说明原因和下一步，不要声称已经成功。"
    return TOOL_FAILURE_MESSAGE


def _hidden_clarification_answer(message) -> bool:
    if getattr(message, "type", "") not in {"human", "user"}:
        return False
    additional = getattr(message, "additional_kwargs", None) or {}
    return (
        isinstance(additional, dict)
        and additional.get("floris_interaction") == "clarification"
    )


def build_graph(
    model: ChatOpenAI,
    tools: list,
    system_prompt: str,
    checkpointer=None,
    store=None,
    required_tool: str = "",
    required_tools: Iterable[str] | None = None,
    blocked_skill: str = "",
    response_language: str = "zh-CN",
):
    model_with_tools = model.bind_tools(tools) if tools else model
    allowed_tool_names = {getattr(tool, "name", "") for tool in tools}
    required_sequence = tuple(required_tools or (() if not required_tool else (required_tool,)))

    async def agent_node(state: MessagesState):
        # The semantic LLM planner—not a keyword rule—decides that a disabled
        # Skill is indispensable. Once decided, the runtime enforces the UI
        # truth contract: no model may simulate a card, search result or side
        # effect that cannot exist.
        if blocked_skill:
            return {"messages": [AIMessage(content=blocked_capability_response(
                [blocked_skill], response_language,
            ))]}
        tools_this_turn = 0
        used_tool_names = []
        seen_tool_call_signatures: set[str] = set()
        clarification_ready = False
        crossed_clarification_answer = False
        for message in reversed(state["messages"]):
            if getattr(message, "type", "") in {"human", "user"}:
                # A structured-card answer is a continuation of the original
                # logical turn, not a brand-new task. Reuse completed route,
                # place and search tools from before the card so submitting one
                # missing time does not repeat expensive work. The prior
                # clarification tool itself is deliberately excluded below:
                # its card was terminal only before the user answered it.
                if not crossed_clarification_answer and _hidden_clarification_answer(message):
                    crossed_clarification_answer = True
                    continue
                break
            if getattr(message, "type", "") == "tool":
                name = getattr(message, "name", "")
                if crossed_clarification_answer and name == "ask_user_clarification":
                    continue
                if not crossed_clarification_answer:
                    tools_this_turn += 1
                used_tool_names.append(name)
                try:
                    payload = json.loads(str(getattr(message, "content", "") or ""))
                    clarification_ready = clarification_ready or (
                        not crossed_clarification_answer
                        and isinstance(payload, dict)
                        and payload.get("ui_action") == "clarification_action"
                    )
                except (TypeError, json.JSONDecodeError):
                    pass
            if getattr(message, "type", "") in {"ai", "assistant"}:
                for tool_call in list(getattr(message, "tool_calls", None) or []):
                    if isinstance(tool_call, dict):
                        seen_tool_call_signatures.add(_tool_call_signature(tool_call))
        # The structured card is the complete response for a clarification
        # turn. Do not run a second prose pass that repeats the questions after
        # the card and makes the interaction feel like an afterthought.
        if "ask_user_clarification" in used_tool_names or clarification_ready:
            return {"messages": [AIMessage(content="")]}
        # A model can occasionally keep reformulating the same search. Preserve
        # multi-tool reasoning, but after a generous turn-local budget force a
        # normal answer from the evidence already collected instead of exposing
        # LangGraph's recursion error to the user.
        force_finalize = tools_this_turn >= 4
        rich_search_used = "rich_search" in used_tool_names
        unavailable_required_tools = [
            name for name in required_sequence
            if name not in allowed_tool_names and name not in used_tool_names
        ]
        if unavailable_required_tools:
            return {"messages": [AIMessage(content=blocked_capability_response(
                unavailable_required_tools,
                response_language,
                configured=True,
            ))]}
        required_name = "" if force_finalize else next_required_tool(
            required_sequence, used_tool_names, allowed_tool_names,
        )
        planned_sequence_complete = bool(required_sequence) and not required_name
        # The semantic LLM planner has already decided that rich_search is
        # required and the tool adapter already owns its merged search query.
        # Asking a second tool-bound LLM to merely echo that decision adds a
        # full model round without changing any provider input.  Emit the
        # planned call directly; all search decisions still come from the LLM
        # plan and the answering pass remains model-generated.
        if required_name == "rich_search" and not rich_search_used:
            return {"messages": [AIMessage(content="", tool_calls=[{
                "name": "rich_search",
                "args": {"query": "使用本轮 LLM 规划器已合并的查询"},
                "id": f"planned-rich-search-{uuid.uuid4().hex}",
            }])]}
        # Once the planner-required rich search is complete and no other
        # capability remains, close the tool surface for the answer pass.  A
        # tool-bound answer model otherwise tends to request rich_search again;
        # the request is safely suppressed below, but that costs a second LLM
        # round after the provider has already returned.
        finalize_after_rich_search = rich_search_used and not required_name
        remaining_tools = [
            tool for tool in tools
            if getattr(tool, "name", "") != "rich_search"
        ]
        tools_closed = (
            force_finalize
            or planned_sequence_complete
            or (finalize_after_rich_search and not remaining_tools)
        )
        if force_finalize:
            active_model = model
        elif planned_sequence_complete:
            # The semantic planner's shortest capability chain has completed.
            # Close the tool surface for synthesis so the answer model cannot
            # restart a successful place/search/action capability.
            active_model = model
        elif finalize_after_rich_search:
            active_model = model.bind_tools(remaining_tools) if remaining_tools else model
        elif required_name and "ask_user_clarification" in allowed_tool_names:
            # The planner guarantees that one capability is required, while
            # the full-history model decides whether the dialogue has actually
            # supplied every blocking parameter. This applies uniformly to
            # writing, translation, image, place, route, calendar, meeting and
            # other tool-backed Q&A—not to a hard-coded task category.
            required_or_question_tools = [
                tool for tool in tools
                if getattr(tool, "name", "") in {
                    required_name, "ask_user_clarification",
                }
            ]
            active_model = model.bind_tools(required_or_question_tools, tool_choice="required")
        else:
            active_model = (
                model.bind_tools(tools, tool_choice=required_name)
                if required_name else model_with_tools
            )
        history = bounded_history(state["messages"])
        messages = [SystemMessage(content=system_prompt), *history]
        if force_finalize:
            messages.append(SystemMessage(content=(
                "本轮工具阶段已经结束。不要再描述搜索过程，不要再输出或模拟任何工具调用。"
                "请直接基于已有工具结果回答用户；结果不足时明确说明缺少多少和检索边界。"
            )))
        elif planned_sequence_complete:
            messages.append(SystemMessage(content=(
                "能力规划选定的工具已经全部完成。现在只基于已有结果输出最终回答，"
                "不要再次调用、模拟或描述任何工具协议。"
            )))
        elif finalize_after_rich_search:
            messages.append(SystemMessage(content=(
                "本轮唯一一次富搜索已经完成，不得再次调用 rich_search。"
                "若请求仍需地点核验、真实路线、结构化澄清或其他非搜索能力，可以继续调用对应工具；"
                "否则直接基于已有证据回答。不要描述内部搜索过程。"
            )))
        response = await active_model.ainvoke(messages)
        if not tools_closed and not getattr(response, "tool_calls", None):
            normalized = dsml_tool_calls(getattr(response, "content", ""), allowed_tool_names)
            if normalized:
                response = AIMessage(content="", tool_calls=normalized)
        response_tool_calls = list(getattr(response, "tool_calls", None) or [])
        if not tools_closed and response_tool_calls:
            filtered_tool_calls = []
            suppressed_rich_search = False
            suppressed_duplicate = False
            used_tool_name_set = set(used_tool_names)
            accepted_signatures = set(seen_tool_call_signatures)
            accepted_single_use_names = set(used_tool_name_set)
            for tool_call in response_tool_calls:
                name = tool_call.get("name", "") if isinstance(tool_call, dict) else ""
                signature = _tool_call_signature(tool_call) if isinstance(tool_call, dict) else ""
                if (
                    signature in accepted_signatures
                    or (name in TURN_SINGLE_USE_TOOLS and name in accepted_single_use_names)
                ):
                    suppressed_duplicate = True
                    logging.info("suppressed repeated tool call name=%s", name)
                    continue
                if name == "rich_search":
                    if rich_search_used:
                        suppressed_rich_search = True
                        continue
                    rich_search_used = True
                filtered_tool_calls.append(tool_call)
                if signature:
                    accepted_signatures.add(signature)
                if name in TURN_SINGLE_USE_TOOLS:
                    accepted_single_use_names.add(name)
            if suppressed_rich_search or suppressed_duplicate:
                if filtered_tool_calls:
                    response = response.model_copy(update={"tool_calls": filtered_tool_calls})
                else:
                    response = await model.ainvoke([
                        SystemMessage(content=system_prompt),
                        *history,
                        SystemMessage(content=(
                            "本轮需要的工具已经成功执行；重复调用已被忽略。"
                            "请直接基于已有结果给出用户可读的最终回答，"
                            "不要再次调用、模拟或描述任何工具协议。"
                        )),
                    ])
        if force_finalize and not public_content(getattr(response, "content", "")).strip():
            # Some provider models keep imitating their previous DSML transport
            # after tools are unbound. One clean retry yields prose without
            # exposing a placeholder or inventing results.
            response = await model.ainvoke([
                SystemMessage(content=system_prompt),
                *history,
                SystemMessage(content=(
                    "现在只输出给用户看的最终回答，禁止 XML、DSML、tool_calls、invoke 或参数。"
                    "若没有满足条件的结果，直接如实说明。"
                )),
            ])
            if not public_content(getattr(response, "content", "")).strip():
                response = AIMessage(content="没有获得足够且符合条件的可靠信息；我没有用不相关内容凑数。你可以缩小范围或补充约束后再试。")
        if (
            used_tool_names
            and "ask_user_clarification" not in used_tool_names
            and not getattr(response, "tool_calls", None)
            and not public_content(getattr(response, "content", "")).strip()
        ):
            # Empty answer turns are not limited to the recursion-budget path.
            # Some OpenAI-compatible providers emit an empty assistant message
            # immediately after a successful tool result. Give that completed
            # tool history one clean, tool-free synthesis pass so a valid route
            # or calendar proposal cannot collapse into the generic
            # “模型未返回有效回答” terminal error.
            response = await model.ainvoke([
                SystemMessage(content=system_prompt),
                *history,
                SystemMessage(content=(
                    "工具阶段已经完成。现在只输出给用户看的最终回答，禁止调用、模拟或描述工具协议。"
                    "若工具返回了确认卡，简短提示用户核对卡片；若某项操作失败，如实说明失败原因和可执行的下一步。"
                )),
            ])
        if not getattr(response, "tool_calls", None) and not public_content(getattr(response, "content", "")).strip():
            fallback = (
                action_completion_fallback(state["messages"])
                or tool_failure_fallback(state["messages"])
                or tool_result_fallback(state["messages"])
            )
            if fallback:
                response = AIMessage(content=fallback)
        return {"messages": [response]}

    def should_continue(state: MessagesState) -> Literal["tools", "__end__"]:
        last = state["messages"][-1]
        return "tools" if getattr(last, "tool_calls", None) else END

    graph = StateGraph(MessagesState)
    graph.add_node("agent", agent_node)
    graph.add_edge(START, "agent")
    if tools:
        graph.add_node(
            "tools",
            ToolNode(
                tools,
                handle_tool_errors=_tool_failure_message,
            ),
        )
        graph.add_conditional_edges("agent", should_continue)
        graph.add_edge("tools", "agent")
    else:
        graph.add_edge("agent", END)

    return graph.compile(checkpointer=checkpointer, store=store)
