"""LangChain tools — search/vision via our backend server, model via AI_GATEWAY."""

import json
import httpx
from langchain_core.tools import tool

# Our backend server handles heavy lifting (search, vision, image gen)
BACKEND = "http://94.16.110.28:8000"


@tool
async def search_web(query: str) -> str:
    """Search the web for up-to-date information. Use when the user asks about
    recent events, facts, news, or anything needing current data.

    Args:
        query: The search query
    Returns:
        Search results with source, title, and snippet.
    """
    try:
        async with httpx.AsyncClient(timeout=25) as cl:
            r = await cl.get(f"{BACKEND}/api/search/basic", params={"q": query})
            if r.status_code != 200:
                return "搜索服务暂时不可用。"
            data = r.json()
    except Exception:
        return "搜索请求失败，请稍后重试。"

    results = data.get("results", [])
    if not results:
        return "未找到相关结果。"

    lines = []
    for item in results[:8]:
        src = item.get("source", "web")
        title = (item.get("title") or "").strip()
        snippet = (item.get("snippet") or "").strip()
        lines.append(f"[{src}] {title}\n{snippet}")
    return "\n\n".join(lines)


@tool
async def search_images(query: str) -> str:
    """Search for images related to a topic. Use when the user wants pictures.

    Args:
        query: What images to search for
    Returns:
        JSON array of {url, caption} objects.
    """
    try:
        async with httpx.AsyncClient(timeout=25) as cl:
            r = await cl.get(f"{BACKEND}/api/search/basic", params={"q": query})
            if r.status_code != 200:
                return "[]"
            data = r.json()
    except Exception:
        return "[]"

    media = data.get("media", [])
    images = [{"url": m["url"], "caption": m.get("caption", "")} for m in media[:5]]
    return json.dumps(images, ensure_ascii=False)
