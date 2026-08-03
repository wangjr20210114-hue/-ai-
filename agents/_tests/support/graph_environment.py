import json
import unittest

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool

from agents.chat._graph import (
    _linked_trip_result_answer,
    _route_result_answer,
    blocked_capability_response,
    build_graph,
    grounded_route_action_answer,
    grounded_route_stream_answer,
    tool_result_fallback,
)


class _BoundModel:
    def __init__(self, owner):
        self.owner = owner

    async def ainvoke(self, _messages, **_kwargs):
        self.owner.bound_calls += 1
        return AIMessage(content="bound answer")


class _RecordingModel:
    def __init__(self):
        self.bound_calls = 0
        self.unbound_calls = 0

    def bind_tools(self, _tools, **_kwargs):
        return _BoundModel(self)

    async def ainvoke(self, _messages, **_kwargs):
        self.unbound_calls += 1
        return AIMessage(content="final answer")


class _RouteChainBoundModel:
    def __init__(self, owner, tool_choice=""):
        self.owner = owner
        self.tool_choice = tool_choice

    async def ainvoke(self, _messages, **_kwargs):
        if self.tool_choice == "plan_route_between_places":
            self.owner.route_calls += 1
            return AIMessage(content="", tool_calls=[{
                "name": "plan_route_between_places",
                "args": {"origin_query": "北京站", "destination_query": "北京301医院"},
                "id": "route-1",
            }])
        self.owner.final_calls += 1
        return AIMessage(content="真实道路距离为 13.8 公里。")


class _RouteChainModel:
    def __init__(self):
        self.route_calls = 0
        self.final_calls = 0

    def bind_tools(self, _tools, **kwargs):
        return _RouteChainBoundModel(self, kwargs.get("tool_choice", ""))

    async def ainvoke(self, _messages, **_kwargs):
        self.final_calls += 1
        return AIMessage(content="真实道路距离为 13.8 公里。")


@tool
def rich_search(query: str) -> str:
    """Return search evidence."""
    return query


@tool("rich_search")
def failing_rich_search(query: str) -> str:
    """Simulate one transient provider failure."""
    del query
    raise TimeoutError("search provider timed out")


@tool
def ask_user_clarification(title: str) -> str:
    """Return one structured clarification."""
    return title


@tool
def plan_route_between_places(origin_query: str, destination_query: str) -> str:
    """Return one verified route."""
    return f"{origin_query}->{destination_query}:13.8km"


@tool("plan_route_between_places")
def verified_route_action(origin_query: str, destination_query: str) -> str:
    """Return one structured verified Tencent route."""
    return json.dumps({
        "ui_action": "map_action",
        "ordered_stops": [
            {"name": origin_query},
            {"name": destination_query},
        ],
        "route": {
            "mode": "transit",
            "distance_kilometers": 5.0,
            "duration_minutes": 50,
            "transit": {
                "lines": ["地铁2号线内环", "60路"],
                "walking_distance_meters": 1596,
            },
            "fare": {
                "transit": {
                    "provider_estimate": True,
                    "estimate": 5,
                },
            },
        },
    }, ensure_ascii=False)


@tool("plan_route_between_places")
def linked_verified_route_action(origin_query: str, destination_query: str) -> str:
    """Return one structured verified Tencent route with an identity."""
    return json.dumps({
        "ui_action": "map_action",
        "route_plan_id": "current-route",
        "ordered_stops": [
            {"name": origin_query},
            {"name": destination_query},
        ],
        "route": {
            "mode": "transit",
            "distance_kilometers": 5.0,
            "duration_minutes": 50,
        },
    }, ensure_ascii=False)


@tool
def propose_calendar_changes(summary: str) -> str:
    """Return one calendar proposal."""
    return summary


@tool("propose_calendar_changes")
def mismatched_linked_calendar_action(summary: str) -> str:
    """Return a real proposal whose stale route identity must not unground prose."""
    return json.dumps({
        "ui_action": "calendar_action",
        "action": {
            "payload": {
                "summary": summary,
                "source_route_plan_id": "stale-route",
                "changes": [
                    {"operation": "create"},
                    {"operation": "create"},
                ],
            },
        },
    }, ensure_ascii=False)


@tool
def search_places(query: str) -> str:
    """Return verified places."""
    return '{"places":[{"place_id":"breakfast-1","name":"早餐店","address":"酒店东侧"}],"count":1}'

@tool
def search_arxiv(
    topic: str = "",
    limit: int = 5,
    author: str = "",
    year: int = 0,
) -> str:
    """Return structured arXiv papers."""
    return (
        '{"ui_action":"paper_results","papers":['
        f'{{"title":"{topic}","year":{year}}}'
        f'],"limit":{limit},"author":"{author}"}}'
    )


@tool("search_arxiv")
def empty_search_arxiv(topic: str = "", limit: int = 5) -> str:
    """Return a verified empty paper result."""
    return json.dumps({
        "ui_action": "paper_results",
        "papers": [],
        "topic": topic,
        "limit": limit,
    }, ensure_ascii=False)


class _ClarificationChoiceBoundModel:
    def __init__(self, owner, tools, tool_choice):
        self.owner = owner
        self.tools = tools
        self.tool_choice = tool_choice

    async def ainvoke(self, _messages, **_kwargs):
        self.owner.tool_names = {tool.name for tool in self.tools}
        self.owner.tool_choice = self.tool_choice
        return AIMessage(content="", tool_calls=[{
            "name": "ask_user_clarification",
            "args": {"title": "只补充真正缺少的信息"},
            "id": "clarify-global-1",
        }])


class _ClarificationChoiceModel:
    def __init__(self):
        self.tool_names = set()
        self.tool_choice = ""

    def bind_tools(self, tools, **kwargs):
        return _ClarificationChoiceBoundModel(self, tools, kwargs.get("tool_choice", ""))

    async def ainvoke(self, _messages, **_kwargs):
        return AIMessage(content="unexpected")


class _RetryRequiredBoundModel:
    def __init__(self, owner):
        self.owner = owner

    async def ainvoke(self, _messages, **_kwargs):
        self.owner.calls += 1
        if self.owner.calls == 1:
            return AIMessage(content="请告诉我更多信息")
        return AIMessage(content="", tool_calls=[{
            "name": "ask_user_clarification",
            "args": {"title": "请补充必要信息"},
            "id": "clarify-required-retry",
        }])


class _RetryRequiredModel:
    def __init__(self):
        self.calls = 0

    def bind_tools(self, _tools, **_kwargs):
        return _RetryRequiredBoundModel(self)

    async def ainvoke(self, _messages, **_kwargs):
        return AIMessage(content="unexpected")


class _ContinuationBoundModel:
    def __init__(self, owner, tools, tool_choice):
        self.owner = owner
        self.tools = tools
        self.tool_choice = tool_choice

    async def ainvoke(self, _messages, **_kwargs):
        self.owner.calls += 1
        if self.owner.calls == 1:
            self.owner.first_tool_names = {tool.name for tool in self.tools}
            return AIMessage(content="", tool_calls=[{
                "name": "propose_calendar_changes",
                "args": {"summary": "07:04 出发"},
                "id": "calendar-1",
            }])
        return AIMessage(content="日程确认卡已经准备好。")


class _ContinuationModel:
    def __init__(self):
        self.calls = 0
        self.first_tool_names = set()

    def bind_tools(self, tools, **kwargs):
        return _ContinuationBoundModel(self, tools, kwargs.get("tool_choice", ""))

    async def ainvoke(self, _messages, **_kwargs):
        return AIMessage(content="日程确认卡已经准备好。")


class _LinkedRouteCalendarBoundModel:
    def __init__(self, owner, tools, tool_choice):
        self.owner = owner
        self.tools = tools
        self.tool_choice = tool_choice

    async def ainvoke(self, _messages, **_kwargs):
        tool_names = {tool.name for tool in self.tools}
        self.owner.decisions.append((tool_names, self.tool_choice))
        if "plan_route_between_places" in tool_names:
            return AIMessage(content="", tool_calls=[{
                "name": "plan_route_between_places",
                "args": {
                    "origin_query": "北京站",
                    "destination_query": "北京西站",
                },
                "id": "linked-route-1",
            }])
        return AIMessage(content="", tool_calls=[{
            "name": "propose_calendar_changes",
            "args": {"summary": "六站日程提案"},
            "id": "linked-calendar-1",
        }])


class _LinkedRouteCalendarModel:
    def __init__(self):
        self.decisions = []

    def bind_tools(self, tools, **kwargs):
        return _LinkedRouteCalendarBoundModel(
            self, tools, kwargs.get("tool_choice", ""),
        )

    async def ainvoke(self, _messages, **_kwargs):
        return AIMessage(content="路线和日程提案已准备好。")


class _CalendarStageGuardBoundModel:
    def __init__(self, owner):
        self.owner = owner

    async def ainvoke(self, _messages, **_kwargs):
        self.owner.calls += 1
        return AIMessage(content="", tool_calls=[
            {
                "name": "search_places",
                "args": {"query": "北京西站"},
                "id": f"out-of-stage-{self.owner.calls}",
            },
            {
                "name": "propose_calendar_changes",
                "args": {"summary": "路线日程提案"},
                "id": f"calendar-stage-{self.owner.calls}",
            },
        ])


class _CalendarStageGuardModel:
    def __init__(self):
        self.calls = 0

    def bind_tools(self, _tools, **_kwargs):
        return _CalendarStageGuardBoundModel(self)

    async def ainvoke(self, _messages, **_kwargs):
        return AIMessage(content="日程提案已准备好。")


class _BlankAfterToolBoundModel:
    async def ainvoke(self, _messages, **_kwargs):
        return AIMessage(content="")


class _BlankAfterToolModel:
    def __init__(self):
        self.recovery_calls = 0

    def bind_tools(self, _tools, **_kwargs):
        return _BlankAfterToolBoundModel()

    async def ainvoke(self, _messages, **_kwargs):
        self.recovery_calls += 1
        return AIMessage(content="已根据核实路线整理好结果。")


class _UnavailableRequiredModel:
    def __init__(self):
        self.bound_calls = 0
        self.unbound_calls = 0
        self.last_messages = []

    def bind_tools(self, _tools, **_kwargs):
        self.bound_calls += 1
        return self

    async def ainvoke(self, messages, **_kwargs):
        self.unbound_calls += 1
        self.last_messages = messages
        return AIMessage(content="对应能力当前不可用，请先开启 Skill 或完成连接。")


class _RepeatingPlaceBoundModel:
    def __init__(self, owner):
        self.owner = owner

    async def ainvoke(self, _messages, **_kwargs):
        self.owner.bound_calls += 1
        return AIMessage(content="", tool_calls=[{
            "name": "search_places",
            "args": {"query": "桔子酒店附近早餐店"},
            "id": f"place-{self.owner.bound_calls}",
        }])


class _RepeatingPlaceModel:
    def __init__(self, final_content="附近有已核实的早餐店。"):
        self.bound_calls = 0
        self.unbound_calls = 0
        self.final_content = final_content

    def bind_tools(self, _tools, **_kwargs):
        return _RepeatingPlaceBoundModel(self)

    async def ainvoke(self, _messages, **_kwargs):
        self.unbound_calls += 1
        return AIMessage(content=self.final_content)


class _BurstPlaceBoundModel:
    def __init__(self, owner):
        self.owner = owner

    async def ainvoke(self, _messages, **_kwargs):
        self.owner.bound_calls += 1
        return AIMessage(content="", tool_calls=[
            {
                "name": "search_places",
                "args": {"query": query},
                "id": f"place-burst-{index}",
            }
            for index, query in enumerate(
                ["桔子酒店附近早餐店", "中关村软件园早餐店", "西北旺早餐店"],
                start=1,
            )
        ])


class _BurstPlaceModel(_RepeatingPlaceModel):
    def bind_tools(self, _tools, **_kwargs):
        return _BurstPlaceBoundModel(self)

__all__ = [name for name in globals() if not name.startswith("__")]
