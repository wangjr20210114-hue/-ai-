"""LangGraph state graph backed by Makers checkpointer and store adapters."""

from typing import Iterable, Literal
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


def tool_completion_fallback(tool_names: Iterable[str]) -> str:
    """Return safe prose when a successful action tool is followed by an empty model turn."""
    names = set(tool_names)
    if names & {"prepare_map_recommendation", "recommend_places_on_map"}:
        return "地点已经过真实地点服务核实。请点击下方按钮显示地点；未核实的地点不会进入地图。"
    if "propose_meeting" in names:
        return "腾讯会议确认卡已准备好，请在卡片中补齐并核对条件后继续。"
    if "propose_calendar_changes" in names:
        return "日程变更确认卡已准备好，请核对后再确认。"
    if "propose_image" in names:
        return "图片任务已准备好，可在下方图片工坊查看结果。"
    return ""


def _tool_failure_message(exc: Exception) -> str:
    """Keep safe validation feedback so the model can answer naturally."""
    if isinstance(exc, ValueError):
        detail = str(exc).strip()[:500] or "输入不符合要求"
        return f"操作未完成：{detail}。请自然说明原因和下一步，不要声称已经成功。"
    return TOOL_FAILURE_MESSAGE


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
        for message in reversed(state["messages"]):
            if getattr(message, "type", "") in {"human", "user"}:
                break
            if getattr(message, "type", "") == "tool":
                tools_this_turn += 1
                used_tool_names.append(getattr(message, "name", ""))
        # A model can occasionally keep reformulating the same search. Preserve
        # multi-tool reasoning, but after a generous turn-local budget force a
        # normal answer from the evidence already collected instead of exposing
        # LangGraph's recursion error to the user.
        force_finalize = tools_this_turn >= 4
        rich_search_used = "rich_search" in used_tool_names
        required_name = "" if force_finalize else next_required_tool(
            required_sequence, used_tool_names, allowed_tool_names,
        )
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
        tools_closed = force_finalize or finalize_after_rich_search
        if tools_closed:
            active_model = model
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
        elif finalize_after_rich_search:
            messages.append(SystemMessage(content=(
                "本轮唯一一次富搜索已经完成，工具阶段现在结束。请直接基于已有证据回答，"
                "不要再次调用或描述搜索过程；用户未指定长文时用 3–5 个重点简洁综合。"
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
            for tool_call in response_tool_calls:
                name = tool_call.get("name", "") if isinstance(tool_call, dict) else ""
                if name == "rich_search":
                    if rich_search_used:
                        suppressed_rich_search = True
                        continue
                    rich_search_used = True
                filtered_tool_calls.append(tool_call)
            if suppressed_rich_search:
                if filtered_tool_calls:
                    response = response.model_copy(update={"tool_calls": filtered_tool_calls})
                else:
                    response = await model.ainvoke([
                        SystemMessage(content=system_prompt),
                        *history,
                        SystemMessage(content=(
                            "本轮唯一一次富搜索已经完成。请直接基于已有结果回答，"
                            "不要再次调用 rich_search，也不要描述内部搜索过程。"
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
        if not getattr(response, "tool_calls", None) and not public_content(getattr(response, "content", "")).strip():
            fallback = tool_completion_fallback(used_tool_names)
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
