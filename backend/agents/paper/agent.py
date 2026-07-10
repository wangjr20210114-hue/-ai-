"""PaperAgent: literature search, ingestion, reading assistance shell."""
from __future__ import annotations

from agents.paper.models import PaperBundle, PaperSearchRequest


class PaperAgent:
    """Domain shell for paper workflows.

    Current implementation delegates to the existing API helper route logic in
    `api.paper_routes`. Future steps should move search/download/QA internals
    here and keep routes as thin adapters.
    """

    async def search(self, request: PaperSearchRequest | dict) -> PaperBundle:
        req = request if isinstance(request, PaperSearchRequest) else PaperSearchRequest(**request)
        from api.paper_routes import search_papers
        data = await search_papers(topic=req.topic, user_message=req.user_message or req.topic)
        return PaperBundle(topic=data.get("topic", req.topic), papers=data.get("papers", []), source="arxiv")