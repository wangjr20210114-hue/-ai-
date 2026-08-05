"""Authenticated adapter for text extracted from tenant-scoped Makers Blobs."""

from __future__ import annotations

from urllib.parse import urlsplit

import httpx


class DocumentTextError(RuntimeError):
    def __init__(self, code: str = "DOCUMENT_TEXT_UNAVAILABLE") -> None:
        super().__init__(code)
        self.code = str(code or "DOCUMENT_TEXT_UNAVAILABLE")


def _header(headers, name: str) -> str:
    if hasattr(headers, "get"):
        return str(headers.get(name) or headers.get(name.title()) or "")
    return ""


def _document_text_url(ctx) -> str:
    request_url = str(getattr(getattr(ctx, "request", None), "url", "") or "")
    parsed = urlsplit(request_url)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}/document-text"
    configured = str((getattr(ctx, "env", {}) or {}).get("FLORIS_INTERNAL_ORIGIN") or "").rstrip("/")
    parsed = urlsplit(configured)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}/document-text"
    raise DocumentTextError("DOCUMENT_TEXT_ORIGIN_UNAVAILABLE")


async def load_document_text(ctx, file_id: str) -> dict:
    headers = getattr(getattr(ctx, "request", None), "headers", {}) or {}
    forwarded = {
        name: value
        for name in ("authorization", "cookie")
        if (value := _header(headers, name))
    }
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                _document_text_url(ctx),
                headers=forwarded,
                json={"file_id": str(file_id or "")},
            )
        payload = response.json()
    except DocumentTextError:
        raise
    except Exception as exc:
        raise DocumentTextError() from exc
    if response.status_code >= 400 or not isinstance(payload, dict):
        code = payload.get("code") if isinstance(payload, dict) else ""
        raise DocumentTextError(str(code or "DOCUMENT_TEXT_UNAVAILABLE"))
    text = str(payload.get("text") or "").strip()
    if not text:
        raise DocumentTextError("PDF_TEXT_UNAVAILABLE")
    return {
        "file_id": str(payload.get("file_id") or file_id),
        "storage_key": str(payload.get("storage_key") or file_id),
        "text": text,
        "preview": str(payload.get("preview") or text[:1200]),
        "page_count": max(0, int(payload.get("page_count") or 0)),
        "truncated": bool(payload.get("truncated")),
    }
