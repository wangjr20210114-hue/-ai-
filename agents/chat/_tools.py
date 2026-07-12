"""LangChain tools — EdgeOne web_search + our vision-filtered image search."""

import json
import httpx
from langchain_core.tools import tool

# Our server only for image search (vision model filtering is unique to us)
BACKEND = "http://94.16.110.28:8000"


@tool
async def search_images(query: str) -> str:
    """Search for images related to a topic. Use when the user asks to see pictures
    of places, objects, people, or anything visual.
    Images are filtered by a vision model for relevance.

    Args:
        query: What kind of images to search for
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
    if not media:
        return "[]"
    images = [{"url": m["url"], "caption": m.get("caption", "")} for m in media[:5]]
    return json.dumps(images, ensure_ascii=False)
