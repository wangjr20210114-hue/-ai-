"""Safe local PDF storage and text extraction."""
from __future__ import annotations

import asyncio
import hashlib
import time
import uuid
from pathlib import Path
from typing import Any

from config import settings
from database.repositories.conversation_repo import LOCAL_USER_ID
from database.repositories.file_repo import get_file_by_hash, save_file

MAX_FILE_BYTES = 50 * 1024 * 1024
MAX_PDF_PAGES = 500


def _extract_pdf(content: bytes) -> tuple[str, int]:
    import fitz

    document = fitz.open(stream=content, filetype="pdf")
    try:
        if document.needs_pass:
            raise ValueError("PDF 已加密，暂不支持")
        if document.page_count > MAX_PDF_PAGES:
            raise ValueError(f"PDF 页数超过 {MAX_PDF_PAGES} 页限制")
        text = "\n\n".join(page.get_text() for page in document)
        if not text.strip():
            raise ValueError("无法提取 PDF 文本，可能是扫描件")
        return text, document.page_count
    finally:
        document.close()


async def store_pdf(
    content: bytes,
    original_name: str,
    conversation_id: str | None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not content.startswith(b"%PDF-"):
        raise ValueError("文件签名不是有效 PDF")
    if len(content) > MAX_FILE_BYTES:
        raise ValueError("文件过大，请上传 50MB 以下的 PDF")
    digest = hashlib.sha256(content).hexdigest()
    existing = await get_file_by_hash(digest)
    if existing and Path(existing["storage_path"]).is_file():
        return existing

    extracted_text, page_count = await asyncio.to_thread(_extract_pdf, content)
    file_id = existing["id"] if existing else f"file-{uuid.uuid4().hex[:16]}"
    storage_dir = Path(settings.file_storage_dir).resolve()
    storage_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{file_id}.pdf"
    path = storage_dir / stored_name
    await asyncio.to_thread(path.write_bytes, content)
    now = time.time()
    item = {
        "id": file_id,
        "owner_id": LOCAL_USER_ID,
        "conversation_id": existing.get("conversation_id") if existing else conversation_id,
        "sha256": digest,
        "original_name": existing["original_name"] if existing else Path(original_name).name[:255] or "document.pdf",
        "stored_name": stored_name,
        "storage_path": str(path),
        "mime_type": "application/pdf",
        "size_bytes": len(content),
        "page_count": page_count,
        "extracted_text": extracted_text,
        "metadata": existing.get("metadata", {}) if existing else metadata or {},
        "created_at": existing["created_at"] if existing else now,
    }
    await save_file(item)
    return item


async def import_legacy_paper_files() -> int:
    """Adopt saved pre-M1 paper files and rewrite their database references."""
    from database.connection import get_db

    db = await get_db()
    cursor = await db.execute(
        "SELECT DISTINCT file_id FROM papers WHERE file_id NOT IN (SELECT id FROM files)"
    )
    legacy_ids = [row[0] for row in await cursor.fetchall()]
    legacy_dir = Path("./uploads/papers").resolve()
    imported = 0
    for legacy_id in legacy_ids:
        candidates = [path for path in legacy_dir.glob("*.pdf") if path.name.startswith(f"{legacy_id}_")]
        if not candidates:
            continue
        path = candidates[0]
        try:
            stored = await store_pdf(
                await asyncio.to_thread(path.read_bytes),
                path.name.split("_", 1)[-1],
                "default-conversation",
                {"source": "legacy-paper", "legacy_file_id": legacy_id},
            )
        except (OSError, ValueError):
            continue
        await db.execute("UPDATE papers SET file_id=? WHERE file_id=?", (stored["id"], legacy_id))
        imported += 1
    if imported:
        await db.commit()
    return imported
