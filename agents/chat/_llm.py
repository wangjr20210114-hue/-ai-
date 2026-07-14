"""LangGraph model configured for the Tencent Hunyuan Token Plan API."""

from langchain_openai import ChatOpenAI

DEFAULT_BASE_URL = "https://api.lkeap.cloud.tencent.com/plan/v3"
DEFAULT_MODEL = "hy3"
_model_cache: dict[tuple[str, str, str], ChatOpenAI] = {}


def get_model(env: dict) -> ChatOpenAI:
    api_key = str(env.get("HUNYUAN_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("Missing environment variable: HUNYUAN_API_KEY")

    model_name = str(env.get("HUNYUAN_MODEL") or DEFAULT_MODEL).strip()
    base_url = str(env.get("HUNYUAN_BASE_URL") or DEFAULT_BASE_URL).strip().rstrip("/")
    cache_key = (model_name, base_url, api_key)
    if cache_key in _model_cache:
        return _model_cache[cache_key]

    model = ChatOpenAI(
        model=model_name,
        api_key=api_key,
        base_url=base_url,
        temperature=0.0,
        timeout=300,
        streaming=True,
    )
    _model_cache[cache_key] = model
    return model
