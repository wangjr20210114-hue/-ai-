from __future__ import annotations

import unittest
from types import SimpleNamespace

from agents._shared.opportunities import (
    detect_opportunity,
    file_opportunity_signal,
    opportunity_signal,
    parse_opportunity,
)
from agents._shared.proactive import empty_proactive_state, process_schedule_signals, public_proactive_state
from agents.chat.index import _document_context


class FakeModel:
    def __init__(self, content: str):
        self.content = content
        self.calls = 0

    async def ainvoke(self, _messages):
        self.calls += 1
        return SimpleNamespace(content=self.content)


class OpportunityTests(unittest.IsolatedAsyncioTestCase):
    def test_uploaded_document_context_is_bounded_and_explicitly_delimited(self):
        context = _document_context({
            "document_context": {
                "filename": "周报.pdf",
                "text": "搜索提速和主动服务闭环。\x00",
            }
        })
        self.assertIn('filename="周报.pdf"', context)
        self.assertIn("搜索提速和主动服务闭环。", context)
        self.assertNotIn("\x00", context)
        self.assertEqual(_document_context({"document_context": {"filename": "empty.pdf"}}), "")

    def test_parser_accepts_one_high_confidence_semantic_opportunity(self):
        value = parse_opportunity(
            '{"should_notify":true,"type":"writing_improvement","title":"适配正式汇报",'
            '"body":"当前草稿可以进一步压缩为管理层摘要。","action_prompt":"请把刚才的草稿改成300字管理层摘要",'
            '"priority":"low","confidence":0.86,"expires_in_hours":48,"reason":"有明确受众"}'
        )
        self.assertEqual(value["type"], "writing_improvement")
        self.assertEqual(value["expires_in_hours"], 48)

    def test_parser_rejects_low_confidence_and_unknown_types(self):
        low = parse_opportunity(
            '{"should_notify":true,"type":"task_next_step","title":"继续",'
            '"body":"继续处理","action_prompt":"继续","confidence":0.4}'
        )
        unknown = parse_opportunity(
            '{"should_notify":true,"type":"marketing","title":"继续",'
            '"body":"继续处理","action_prompt":"继续","confidence":0.9}'
        )
        self.assertIsNone(low)
        self.assertIsNone(unknown)

    async def test_detector_skips_pending_side_effect_without_calling_model(self):
        model = FakeModel('{}')
        result = await detect_opportunity(
            model,
            user_message="帮我建立日程",
            answer="请确认日程",
            has_pending_action=True,
        )
        self.assertIsNone(result)
        self.assertEqual(model.calls, 0)

    def test_semantic_opportunities_have_cooldown_and_expire(self):
        now = 100_000
        opportunity = {
            "type": "search_update", "title": "进展待跟进", "body": "发布仍在推进中。",
            "action_prompt": "请检查这项发布是否有新进展", "priority": "normal",
            "confidence": 0.9, "expires_in_hours": 1, "reason": "仍有待确认节点",
        }
        state = empty_proactive_state()
        first = opportunity_signal(opportunity, source_id="message-1", now=now)
        second = opportunity_signal(opportunity, source_id="message-2", now=now + 60)
        stats = process_schedule_signals(state, [first, second], now)
        self.assertEqual(stats["notifications_created"], 1)
        self.assertEqual(stats["skipped"], 1)
        self.assertEqual(len(public_proactive_state(state, now)["notifications"]), 1)
        self.assertEqual(len(public_proactive_state(state, now + 3601)["notifications"]), 0)

    def test_document_upload_creates_actionable_persistent_notification(self):
        signal = file_opportunity_signal(
            {"file_id": "file-1", "filename": "方案.pdf", "is_paper": False},
            dedup_key="blob-1",
            now=100,
        )
        state = empty_proactive_state()
        stats = process_schedule_signals(state, [signal], 100)
        notification = public_proactive_state(state, 100)["notifications"][0]
        self.assertEqual(stats["notifications_created"], 1)
        self.assertEqual(notification["type"], "opportunity_document_next_step")
        self.assertIn("行动项", notification["action_prompt"])


if __name__ == "__main__":
    unittest.main()
