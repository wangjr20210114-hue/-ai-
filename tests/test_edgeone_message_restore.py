import importlib.util
import unittest
from pathlib import Path


_MODULE_PATH = Path(__file__).resolve().parents[1] / "agents" / "messages" / "index.py"
_SPEC = importlib.util.spec_from_file_location("edgeone_messages", _MODULE_PATH)
assert _SPEC and _SPEC.loader
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


class _Message:
    def __init__(self, role, content, *, message_id="", additional_kwargs=None):
        self.type = role
        self.content = content
        self.id = message_id
        self.additional_kwargs = additional_kwargs or {}


class _CheckpointTuple:
    def __init__(self, messages):
        self.checkpoint = {"channel_values": {"messages": messages}}


class _Checkpointer:
    def __init__(self, messages):
        self.messages = messages

    async def aget_tuple(self, _config):
        return _CheckpointTuple(self.messages)


class _Store:
    def __init__(self, messages):
        self.langgraph_checkpointer = _Checkpointer(messages)


class _Context:
    def __init__(self, messages):
        self.conversation_id = "conversation-a"
        self.store = _Store(messages)


class EdgeOneMessageRestoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_messages_restore_travel_schedules_and_date_from_ai_checkpoint(self):
        schedule = {
            "id": "travel-1",
            "title": "故宫博物院",
            "start_time": 1784077200,
            "duration_minutes": 120,
        }
        travel_plan = {
            "id": "plan-1",
            "city": "北京",
            "start_date": "2026-07-15",
            "days": 1,
            "tentative_date": False,
            "schedules": [schedule],
        }
        ctx = _Context([
            _Message("human", "明天去故宫", message_id="human-1"),
            _Message(
                "ai",
                "行程已写入右侧日历。",
                message_id="ai-1",
                additional_kwargs={
                    "follow_ups": ["怎么预约？"],
                    "map_places": [{"name": "故宫博物院", "lat": 39.9163, "lng": 116.3972}],
                    "travel_plan": travel_plan,
                },
            ),
        ])

        result = await _MODULE.handler(ctx)

        self.assertEqual(result["travel_plan"]["start_date"], "2026-07-15")
        self.assertEqual(result["schedules"], [schedule])
        self.assertEqual(result["messages"][1]["followUps"], ["怎么预约？"])
        self.assertEqual(result["messages"][1]["mapPlaces"][0]["name"], "故宫博物院")


if __name__ == "__main__":
    unittest.main()
