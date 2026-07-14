import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch


_MODULE_PATH = Path(__file__).resolve().parents[1] / "agents" / "chat" / "_llm.py"
_SPEC = importlib.util.spec_from_file_location("edgeone_hunyuan_llm", _MODULE_PATH)
assert _SPEC and _SPEC.loader
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


class EdgeOneHunyuanModelTests(unittest.TestCase):
    def setUp(self) -> None:
        _MODULE._model_cache.clear()

    def test_hunyuan_api_key_is_required(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "HUNYUAN_API_KEY"):
            _MODULE.get_model({"AI_GATEWAY_API_KEY": "unused-makers-key"})

    def test_uses_token_plan_defaults_and_ignores_makers_gateway(self) -> None:
        model = object()
        with patch.object(_MODULE, "ChatOpenAI", return_value=model) as constructor:
            result = _MODULE.get_model({
                "HUNYUAN_API_KEY": "test-hunyuan-key",
                "AI_GATEWAY_API_KEY": "unused-makers-key",
                "AI_GATEWAY_BASE_URL": "https://unused.example/v1",
            })

        self.assertIs(result, model)
        constructor.assert_called_once_with(
            model="hy3",
            api_key="test-hunyuan-key",
            base_url="https://api.lkeap.cloud.tencent.com/plan/v3",
            temperature=0.0,
            timeout=300,
            streaming=True,
        )

    def test_allows_hunyuan_endpoint_and_model_overrides(self) -> None:
        with patch.object(_MODULE, "ChatOpenAI") as constructor:
            _MODULE.get_model({
                "HUNYUAN_API_KEY": "test-hunyuan-key",
                "HUNYUAN_BASE_URL": "https://hunyuan.example/v1/",
                "HUNYUAN_MODEL": "hy3-preview",
            })

        self.assertEqual(constructor.call_args.kwargs["model"], "hy3-preview")
        self.assertEqual(
            constructor.call_args.kwargs["base_url"],
            "https://hunyuan.example/v1",
        )

    def test_model_instance_is_cached_per_credentials(self) -> None:
        model = object()
        env = {"HUNYUAN_API_KEY": "test-hunyuan-key"}
        with patch.object(_MODULE, "ChatOpenAI", return_value=model) as constructor:
            self.assertIs(_MODULE.get_model(env), model)
            self.assertIs(_MODULE.get_model(env), model)

        constructor.assert_called_once()


if __name__ == "__main__":
    unittest.main()
