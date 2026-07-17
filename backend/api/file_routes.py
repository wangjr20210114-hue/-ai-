"""Safe persistent local file API."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from config import settings
from database.repositories.conversation_repo import DEFAULT_CONVERSATION_ID, get_conversation
from database.repositories.file_repo import get_file
from services.file_service import MAX_FILE_BYTES, store_pdf

router = APIRouter(prefix="/api/files", tags=["files"])


def _public_file(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item["id"],
        "original_name": item["original_name"],
        "mime_type": item["mime_type"],
        "size_bytes": item["size_bytes"],
        "page_count": item["page_count"],
        "total_chars": len(item.get("extracted_text") or ""),
        "preview": (item.get("extracted_text") or "")[:500],
        "metadata": item.get("metadata") or {},
        "created_at": item["created_at"],
    }


@router.post("")
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    conversation_id: str = Form(DEFAULT_CONVERSATION_ID),
) -> dict[str, Any]:
    if await get_conversation(conversation_id) is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    content = await file.read(MAX_FILE_BYTES + 1)
    try:
        item = await store_pdf(content, file.filename or "document.pdf", conversation_id)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    public_item = _public_file(item)
    signal = await request.app.state.file_collector.on_file_persisted(item, conversation_id)
    await request.app.state.proactive_event_service.process_signal(signal.to_dict())
    return {"file": public_item}


@router.get("/{file_id}")
async def file_metadata(file_id: str) -> dict[str, Any]:
    item = await get_file(file_id)
    if item is None:
        raise HTTPException(status_code=404, detail="file not found")
    return {"file": _public_file(item)}


@router.get("/{file_id}/content")
async def file_content(file_id: str):
    item = await get_file(file_id)
    if item is None:
        raise HTTPException(status_code=404, detail="file not found")
    root = Path(settings.file_storage_dir).resolve()
    path = Path(item["storage_path"]).resolve()
    if root not in path.parents or not path.is_file():
        raise HTTPException(status_code=404, detail="file content not found")
    return FileResponse(path, media_type="application/pdf", filename=item["original_name"])
