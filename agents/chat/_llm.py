"""LangGraph model configured exclusively through the Makers AI Gateway."""

from typing import Any

from langchain_openai import ChatOpenAI

DEFAULT_MODEL = "@makers/deepseek-v4-flash"
_model_cache: dict[tuple[str, str, bool, float, float], Any] = {}


def _model_timeout(env: dict, key: str, default: float) -> float:
    try:
        return max(5.0, min(30.0, float(env.get(key) or default)))
    except (TypeError, ValueError):
        return default


def _is_quota_error(error: Exception) -> bool:
    text = str(error).lower()
    return any(marker in text for marker in (
        "quota exhausted", "free quota", "aig_free_quota_exhausted",
        "rate limit", "rate_limit", "status code: 429", "error code: 429",
    ))


def _is_transient_gateway_error(error: Exception) -> bool:
    text = str(error).lower()
    return any(marker in text for marker in (
        "connection error", "connecterror", "timed out", "timeout",
        "service unavailable", "bad gateway", "gateway timeout",
    ))


class QuotaFailoverModel:
    """Keep Makers first; fail over on quota or transient gateway outages."""

    def __init__(self, primary: Any, fallback: Any):
        self.primary = primary
        self.fallback = fallback

    def bind_tools(self, tools, **kwargs):
        return QuotaFailoverModel(
            self.primary.bind_tools(tools, **kwargs),
            self.fallback.bind_tools(tools, **kwargs),
        )

    async def ainvoke(self, messages, **kwargs):
        try:
            return await self.primary.ainvoke(messages, **kwargs)
        except Exception as exc:
            if not (_is_quota_error(exc) or _is_transient_gateway_error(exc)):
                raise
            return await self.fallback.ainvoke(messages, **kwargs)


def get_model(env: dict):
    missing = [
        key
        for key in ("AI_GATEWAY_API_KEY", "AI_GATEWAY_BASE_URL")
        if not str(env.get(key, "")).strip()
    ]
    if missing:
        raise RuntimeError(f"Missing environment variables: {', '.join(missing)}")

    model_name = str(env.get("AI_GATEWAY_MODEL") or DEFAULT_MODEL)
    base_url = str(env["AI_GATEWAY_BASE_URL"]).rstrip("/")
    direct_key = str(env.get("DEEPSEEK_API_KEY") or "").strip()
    gateway_timeout = _model_timeout(env, "AI_GATEWAY_TIMEOUT_SECONDS", 12.0)
    fallback_timeout = _model_timeout(env, "DEEPSEEK_TIMEOUT_SECONDS", 12.0)
    cache_key = (model_name, base_url, bool(direct_key), gateway_timeout, fallback_timeout)
    if cache_key in _model_cache:
        return _model_cache[cache_key]

    model: Any = ChatOpenAI(
        model=model_name,
        api_key=env["AI_GATEWAY_API_KEY"],
        base_url=base_url,
        temperature=0.0,
        timeout=gateway_timeout,
        streaming=True,
    )
    if direct_key:
        fallback = ChatOpenAI(
            model=str(env.get("DEEPSEEK_MODEL") or "deepseek-chat"),
            api_key=direct_key,
            base_url=str(env.get("DEEPSEEK_BASE_URL") or "https://api.deepseek.com/v1").rstrip("/"),
            temperature=0.0,
            timeout=fallback_timeout,
            streaming=True,
        )
        model = QuotaFailoverModel(model, fallback)
    _model_cache[cache_key] = model
    return model
