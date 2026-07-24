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
from ._protocol import dsml_tool_calls, public_content
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


def tool_completion_fallback(tool_names: Iterable[str]) -> str:
    """Return safe prose when a successful action tool is followed by an empty model turn."""
    names = set(tool_names)
    if names & {
        "prepare_map_recommendation",
        "recommend_places_on_map",
    }:
        return "地点已经过真实地点服务核实。请点击下方按钮显示地点；未核实的地点不会进入地图。"
    if "propose_meeting" in names:
        return "腾讯会议确认卡已准备好，请在卡片中补齐并核对条件后继续。"
    if "propose_calendar_changes" in names:
        return "日程变更确认卡已准备好，请核对后再确认。"
    if "propose_image" in names:
        return "图片任务已准备好，可在下方图片工坊查看结果。"
    if "ask_user_clarification" in names:
        return ""
    return ""


def tool_result_fallback(messages: Iterable) -> str:
    """Build a truthful minimal answer from successful place lookup output.

    This is used only after both the normal synthesis pass and its clean
    tool-free retry return no public prose. It prevents a completed provider
    lookup from collapsing into the generic empty-answer error.
    """
    logical_turn_messages: list = []
    crossed_clarification_answer = False
    for message in reversed(list(messages)):
        if getattr(message, "type", "") in {"human", "user"}:
            if (
                not crossed_clarification_answer
                and _hidden_clarification_answer(message)
            ):
                crossed_clarification_answer = True
                continue
            break
        logical_turn_messages.append(message)

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
):
    model_with_tools = model.bind_tools(tools) if tools else model
    allowed_tool_names = {getattr(tool, "name", "") for tool in tools}
    required_sequence = tuple(required_tools or (() if not required_tool else (required_tool,)))

    async def agent_node(state: MessagesState):
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
            fallback = tool_completion_fallback(used_tool_names) or tool_result_fallback(state["messages"])
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
