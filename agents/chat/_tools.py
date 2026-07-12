"""LangChain tools — vision-filtered image search."""

import json
import httpx
from langchain_core.tools import tool

BACKEND = "http://94.16.110.28:8000"


@tool
async def search_images(query: str) -> str:
    """Search for images. Use when the user wants pictures. Returns JSON [{url, caption}].

    Args:
        query: What images to search for
    """
    try:
        async with httpx.AsyncClient(timeout=25) as cl:
            r = await cl.get(f"{BACKEND}/api/search/basic", params={"q": query})
            if r.status_code != 200:
                return json.dumps([])
            data = r.json()
        media = data.get("media", [])
        if not media:
            return json.dumps([])
        result = [{"url": m["url"], "caption": m.get("caption", "")} for m in media[:5]]
        return json.dumps(result, ensure_ascii=False)
    except Exception:
        return json.dumps([])
