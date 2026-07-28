import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from agents.chat._llm import (
    DEFAULT_FAST_FALLBACK_MODEL,
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

    @patch("agents.chat._llm.ChatOpenAI")
    def test_fast_profile_uses_flash_for_direct_provider_failover(self, chat_open_ai):
        chat_open_ai.side_effect = [MagicMock(), MagicMock()]
        get_model({
            "AI_GATEWAY_API_KEY": "makers-key",
            "AI_GATEWAY_BASE_URL": "https://ai-gateway.edgeone.link/v1",
            "DEEPSEEK_API_KEY": "direct-key",
            "DEEPSEEK_THINKING_MODE": "enabled",
        }, thinking_mode="disabled", fallback_profile="fast")
        fallback = chat_open_ai.call_args_list[1].kwargs
        self.assertEqual(fallback["model"], DEFAULT_FAST_FALLBACK_MODEL)
        self.assertEqual(DEFAULT_FAST_FALLBACK_MODEL, "deepseek-v4-flash")
        self.assertEqual(
            fallback["extra_body"],
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


class ModelFailoverTests(unittest.IsolatedAsyncioTestCase):
    async def test_recoverable_provider_400_switches_once_before_output(self):
        primary = MagicMock()
        fallback = MagicMock()
        primary.ainvoke = AsyncMock(side_effect=RuntimeError(
            "Error code: 400 - invalid_request: request envelope rejected"
        ))
        fallback.ainvoke = AsyncMock(return_value="recovered")
        model = QuotaFailoverModel(primary, fallback)

        self.assertEqual(await model.ainvoke([{"role": "user", "content": "hi"}]), "recovered")
        primary.ainvoke.assert_awaited_once()
        fallback.ainvoke.assert_awaited_once()

    async def test_configuration_400_is_not_retried(self):
        primary = MagicMock()
        fallback = MagicMock()
        primary.ainvoke = AsyncMock(side_effect=RuntimeError(
            "Error code: 400 - Model ID must include provider prefix"
        ))
        fallback.ainvoke = AsyncMock(return_value="must-not-run")
        model = QuotaFailoverModel(primary, fallback)

        with self.assertRaises(RuntimeError):
            await model.ainvoke([{"role": "user", "content": "hi"}])
        fallback.ainvoke.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
