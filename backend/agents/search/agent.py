"""SearchAgent: multi-source retrieval and rich answer preparation."""
from __future__ import annotations

from agents.search.models import SearchBundle, SearchRequest


class SearchAgent:
    async def retrieve(self, request: SearchRequest | dict) -> SearchBundle:
        req = request if isinstance(request, SearchRequest) else SearchRequest(**request)
        from services.search_system import search
        data = await search(req.query, intent=req.intent, time_sensitive=req.time_sensitive, depth=req.depth)
        return SearchBundle(
            query=data.get("query", req.query),
            results=data.get("results", []),
            images=data.get("images", []),
            image_descriptions=data.get("image_descriptions", []),
            sources_used=data.get("sources_used", []),
            total=data.get("total", 0),
        )

    async def build_answer_stream(self, bundle: SearchBundle):
        from services.search_service import build_search_prompt
        return await build_search_prompt(bundle.query, bundle.results, bundle.images, bundle.sources_used, bundle.image_descriptions)