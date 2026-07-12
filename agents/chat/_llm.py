"""LangGraph agent model via EdgeOne AI Gateway."""

from langchain_openai import ChatOpenAI

DEFAULT_MODEL = "@makers/deepseek-v4-flash"
_model_cache: dict = {}


def get_model(env: dict) -> ChatOpenAI:
    cache_key = env.get("AI_GATEWAY_BASE_URL", "")
    if cache_key in _model_cache:
        return _model_cache[cache_key]
    llm = ChatOpenAI(
        model=env.get("AI_GATEWAY_MODEL", DEFAULT_MODEL),
        api_key=env["AI_GATEWAY_API_KEY"],
        base_url=env.get("AI_GATEWAY_BASE_URL", "https://api.deepseek.com/v1"),
        temperature=0.0,
        timeout=300,
        streaming=True,
    )
    _model_cache[cache_key] = llm
    return llm
