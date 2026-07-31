from __future__ import annotations

import asyncio
from types import SimpleNamespace

from agents._tests.auth_helpers import auth_env, auth_headers


class FakeStore:
    def __init__(self):
        self.values = {}

    async def aget(self, namespace, key):
        value = self.values.get((namespace, key))
        return None if value is None else {"value": value}

    async def aput(self, namespace, key, value):
        self.values[(namespace, key)] = value


class FakeCheckpointer:
    def __init__(self, messages):
        self.messages = messages

    async def aget_tuple(self, _config):
        return {"checkpoint": {"channel_values": {"messages": self.messages}}}


class MakersCheckpointMessage:
    """Mimic Makers' field proxy, which raises KeyError for missing fields."""

    def __init__(self, **values):
        self.values = values

    def __getattr__(self, key):
        if key in self.values:
            return self.values[key]
        raise KeyError(key)


class StructuredPlannerModel:
    def __init__(
        self,
        args=None,
        delay=0,
        topic_args=None,
        clarification_args=None,
        preflight_args=None,
    ):
        self.calls = 0
        self.args = args or {
            "needs_web_search": True,
            "needs_images": True,
            "search_query": "故宫历史",
            "image_query": "故宫建筑",
        }
        self.delay = delay
        self.topic_args = topic_args or {"topics": []}
        self.clarification_args = clarification_args or {
            "needs_clarification": False,
        }
        self.preflight_args = preflight_args or {
            **self.clarification_args,
            "topics": list(self.topic_args.get("topics") or []),
        }
        self.messages = []
        self.tool_choice = ""
        self.tools = []
        self.schema = None
        self.method = ""
        self.include_raw = False

    def with_structured_output(self, schema, **kwargs):
        self.schema = schema
        self.method = kwargs.get("method", "")
        self.include_raw = bool(kwargs.get("include_raw"))
        return self

    async def ainvoke(self, messages):
        if self.delay:
            await asyncio.sleep(self.delay)
        self.calls += 1
        self.messages = messages
        values = (
            self.preflight_args
            if self.schema.__name__ == "SemanticPreflight"
            else self.topic_args
            if self.schema.__name__ == "PromptTopicSelection"
            else self.args
        )
        if self.schema.__name__ == "CapabilityPlan":
            values = {"capabilities": [], **values}
        return {
            "parsed": self.schema(**values),
            "raw": SimpleNamespace(content=""),
            "parsing_error": None,
        }


class FailingStructuredPlannerModel(StructuredPlannerModel):
    async def ainvoke(self, messages):
        self.calls += 1
        self.messages = messages
        raise RuntimeError("structured planner rejected the request")


class RecoveringStructuredPlannerModel(StructuredPlannerModel):
    async def ainvoke(self, messages):
        self.calls += 1
        self.messages = messages
        if self.schema.__name__ == "CapabilityPlan":
            raise RuntimeError(
                "Error code: 400 - invalid_request: request envelope rejected"
            )
        values = {
            "needs_clarification": False,
            "topics": ["web"],
            "capabilities": ["web_search"],
            "needs_web_search": True,
            "strict_today_only": True,
            "search_query": "2026-07-29 AI 新闻",
            "needs_images": False,
        }
        return {
            "parsed": self.schema(**values),
            "raw": SimpleNamespace(content=""),
            "parsing_error": None,
        }


class FakeRequest:
    def __init__(self, body, headers=None):
        self.body = body
        self.headers = {**auth_headers(), **(headers or {})}


class FakeStores:
    def __init__(self, store):
        self.langgraph_store = store


class FakeContext:
    def __init__(self, store, body):
        self.conversation_id = "conversation-1"
        self.store = FakeStores(store)
        self.request = FakeRequest(body)
        self.env = auth_env()


