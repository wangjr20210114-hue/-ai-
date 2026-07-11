"""File event adapter invoked after durable file persistence."""
from __future__ import annotations

from typing import Any

from agent.collectors.base import CollectedSignal


class FileCollector:
    name = "file"

    async def on_file_persisted(
        self,
        item: dict[str, Any],
        conversation_id: str,
    ) -> CollectedSignal:
        return CollectedSignal(
            event_type="file.uploaded",
            source="file_collector",
            subject_id=str(item["id"]),
            dedup_key=f"file-uploaded:{item['id']}:{item['sha256']}",
            occurred_at=float(item["created_at"]),
            payload={
                "id": item["id"],
                "original_name": item["original_name"],
                "mime_type": item["mime_type"],
                "size_bytes": item["size_bytes"],
                "page_count": item["page_count"],
                "total_chars": len(item.get("extracted_text") or ""),
                "conversation_id": conversation_id,
            },
        )
