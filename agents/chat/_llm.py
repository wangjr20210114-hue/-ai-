"""LangGraph model configured exclusively through the Makers AI Gateway."""

from langchain_openai import ChatOpenAI

DEFAULT_MODEL = "@makers/deepseek-v4-flash"
_model_cache: dict[tuple[str, str], ChatOpenAI] = {}


def get_model(env: dict) -> ChatOpenAI:
    missing = [
        key
        for key in ("AI_GATEWAY_API_KEY", "AI_GATEWAY_BASE_URL")
        if not str(env.get(key, "")).strip()
    ]
    if missing:
        raise RuntimeError(f"Missing environment variables: {', '.join(missing)}")

    model_name = str(env.get("AI_GATEWAY_MODEL") or DEFAULT_MODEL)
    base_url = str(env["AI_GATEWAY_BASE_URL"]).rstrip("/")
    cache_key = (model_name, base_url)
    if cache_key in _model_cache:
        return _model_cache[cache_key]

    model = ChatOpenAI(
        model=model_name,
        api_key=env["AI_GATEWAY_API_KEY"],
        base_url=base_url,
        temperature=0.0,
        timeout=300,
        streaming=True,
    )
    _model_cache[cache_key] = model
    return model
