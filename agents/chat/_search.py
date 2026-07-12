"""Web search tool adapted for EdgeOne runtime — wraps search_system.py."""

import asyncio
import json
import re
import sys
import os

# Ensure project root is on path so we can import services
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)
if os.path.join(_project_root, "backend") not in sys.path:
    sys.path.insert(0, os.path.join(_project_root, "backend"))


async def web_search(query: str, max_results: int = 8) -> dict:
    """Search web with multi-source aggregation + vision-based image filtering."""
    try:
        from services.search_system import search as do_search
        results = await asyncio.wait_for(
            do_search(query, intent="general", depth="basic"),
            timeout=25,
        )
        web_results = results.get("results", [])
        media = results.get("media", [])

        # Build a text context for the model
        lines = []
        for i, r in enumerate(web_results[:max_results]):
            source = r.get("source", "web")
            title = (r.get("title") or "").strip()
            snippet = (r.get("snippet") or "").strip()
            # Clean internal markers
            snippet = re.sub(r"\[\[[^\]]*\]([^\]]*)\]", r"\1", snippet)
            title = re.sub(r"\[\[[^\]]*\]\]", "", title)
            lines.append(f"[{source}] {title}\n{snippet}")

        return {
            "context": "\n\n".join(lines),
            "results": web_results[:max_results],
            "media": media[:8],
            "count": len(web_results),
        }
    except Exception as e:
        print(f"[search] web_search failed: {e}")
        return {"context": "", "results": [], "media": [], "count": 0}


async def image_search(query: str) -> list[dict]:
    """Search specifically for images related to query."""
    try:
        from services.search_system import search as do_search
        results = await asyncio.wait_for(
            do_search(query, intent="general", depth="basic"),
            timeout=20,
        )
        media = results.get("media", [])[:5]
        return [{"url": m.get("url", ""), "caption": m.get("caption", "")} for m in media]
    except Exception:
        return []
