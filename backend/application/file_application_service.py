"""File lifecycle application service."""
from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from agent.collectors.file_collector import FileCollector
from application.proactive_event_service import ProactiveEventService
from database.repositories.conversation_repo import LOCAL_USER_ID
from database.repositories.file_repo import get_file, save_file
from services.file_service import MAX_FILE_BYTES, store_pdf


class FileApplicationService:
    def __init__(
        self,
        *,
        collector: FileCollector,
        proactive_events: ProactiveEventService,
    ) -> None:
        self.collector = collector
        self.proactive_events = proactive_events

    async def store_upload(
        self,
        *,
        owner_id: str,
        conversation_id: str,
        filename: str,
        content_type: str,
        stream: AsyncIterator[bytes],
    ) -> dict[str, Any]:
        if owner_id != LOCAL_USER_ID:
            raise PermissionError("file owner is invalid")
        if content_type not in {"application/pdf", "application/octet-stream", ""}:
            raise ValueError("当前只支持 PDF")
        chunks: list[bytes] = []
        total = 0
        async for chunk in stream:
            total += len(chunk)
            if total > MAX_FILE_BYTES:
                raise ValueError("文件过大，请上传 50MB 以下的 PDF")
            chunks.append(chunk)
        item = await store_pdf(b"".join(chunks), filename, conversation_id)
        signal = await self.collector.on_file_persisted(item, conversation_id)
        await self.proactive_events.process_signal(signal.to_dict())
        return item

    async def recover_missing_file(
        self,
        *,
        file_id: str,
        candidate_hash: str,
        candidate_path: Path,
    ) -> dict[str, Any]:
        item = await get_file(file_id)
        if item is None:
            return {"recovered": False, "reason": "file_not_found"}
        if Path(item["storage_path"]).is_file():
            return {"recovered": True, "reason": "already_present", "file": item}
        content = candidate_path.read_bytes()
        actual_hash = hashlib.sha256(content).hexdigest()
        if actual_hash != candidate_hash or actual_hash != item["sha256"]:
            return {"recovered": False, "reason": "hash_mismatch"}
        target = Path(item["storage_path"])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        item["storage_path"] = str(target.resolve())
        await save_file(item)
        return {"recovered": True, "reason": "restored", "file": item}
