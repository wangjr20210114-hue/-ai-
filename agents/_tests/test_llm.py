import unittest
from unittest.mock import MagicMock, patch

from agents.chat._llm import (
    DEFAULT_FALLBACK_MODEL,
    QuotaFailoverModel,
    _model_cache,
    _thinking_mode,
    get_model,
)


class ModelConfigurationTests(unittest.TestCase):
    def tearDown(self):
        _model_cache.clear()

    @patch("agents.chat._llm.ChatOpenAI")
    def test_direct_fallback_uses_current_supported_model_name(self, chat_open_ai):
        primary = MagicMock()
        fallback = MagicMock()
        chat_open_ai.side_effect = [primary, fallback]

        model = get_model({
            "AI_GATEWAY_API_KEY": "makers-key",
            "AI_GATEWAY_BASE_URL": "https://ai-gateway.edgeone.link/v1",
            "DEEPSEEK_API_KEY": "direct-key",
        })

        self.assertIsInstance(model, QuotaFailoverModel)
        self.assertEqual(
            chat_open_ai.call_args_list[1].kwargs["model"],
            DEFAULT_FALLBACK_MODEL,
        )
        self.assertEqual(DEFAULT_FALLBACK_MODEL, "deepseek-v4-pro")
        self.assertEqual(
            chat_open_ai.call_args_list[0].kwargs["extra_body"],
            {"thinking": {"type": "enabled"}},
        )
        self.assertEqual(
            chat_open_ai.call_args_list[1].kwargs["extra_body"],
            {"thinking": {"type": "enabled"}},
        )

    @patch("agents.chat._llm.ChatOpenAI")
    def test_thinking_mode_can_be_disabled_for_final_answers(self, chat_open_ai):
        chat_open_ai.return_value = MagicMock()
        get_model({
            "AI_GATEWAY_API_KEY": "makers-key",
            "AI_GATEWAY_BASE_URL": "https://ai-gateway.edgeone.link/v1",
        }, thinking_mode="disabled")
        self.assertEqual(
            chat_open_ai.call_args.kwargs["extra_body"],
            {"thinking": {"type": "disabled"}},
        )

    def test_invalid_thinking_mode_uses_safe_default(self):
        self.assertEqual(_thinking_mode({}, "AI_GATEWAY_THINKING_MODE"), "enabled")
        self.assertEqual(
            _thinking_mode(
                {"AI_GATEWAY_THINKING_MODE": "unsupported"},
                "AI_GATEWAY_THINKING_MODE",
            ),
            "enabled",
        )


if __name__ == "__main__":
    unittest.main()
