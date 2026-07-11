"""Explicit memory proposal, confirmation, editing, and export service."""
from __future__ import annotations

from typing import Any

from database.repositories import memory_repo

_SENSITIVE_KEYS = ("password", "token", "secret", "身份证", "银行卡", "密码", "密钥")


class MemoryService:
    async def propose_memory(
        self,
        source_message_id: str,
        candidate: dict[str, Any],
    ) -> dict[str, Any]:
        """Create a reviewable proposal; memories are never silently committed."""
        key = str(candidate.get("key") or "").strip()
        sensitivity = str(candidate.get("sensitivity") or "normal")
        if any(term.lower() in key.lower() for term in _SENSITIVE_KEYS):
            sensitivity = "sensitive"
        normalized = {
            "key": key,
            "value": candidate.get("value"),
            "confidence": min(1.0, max(0.0, float(candidate.get("confidence") or 1.0))),
            "reason": str(candidate.get("reason") or "explicit_user_preference"),
            "sensitivity": sensitivity,
            "expected_memory_version": candidate.get("expected_memory_version"),
        }
        return await memory_repo.create_proposal(source_message_id, normalized)

    async def upsert_confirmed_memory(
        self,
        proposal_id: str,
        version: int,
    ) -> dict[str, Any]:
        proposal, memory = await memory_repo.confirm_proposal(proposal_id, version)
        return {"proposal": proposal, "memory": memory}

    async def reject_proposal(self, proposal_id: str) -> dict[str, Any] | None:
        return await memory_repo.reject_proposal(proposal_id)

    async def list_proposals(self, status: str | None = "awaiting_confirmation") -> list[dict[str, Any]]:
        return await memory_repo.list_proposals(status)

    async def list_memories(self) -> list[dict[str, Any]]:
        return await memory_repo.list_memories()

    async def update_memory(
        self,
        memory_id: str,
        *,
        value: Any,
        version: int,
        confidence: float | None = None,
        sensitivity: str | None = None,
    ) -> dict[str, Any]:
        return await memory_repo.update_memory(
            memory_id,
            value=value,
            version=version,
            confidence=confidence,
            sensitivity=sensitivity,
        )

    async def delete_memory(self, memory_id: str) -> bool:
        return await memory_repo.delete_memory(memory_id)

    async def clear_memories(self) -> int:
        return await memory_repo.clear_memories()

    async def export_memories(self) -> dict[str, Any]:
        return {"schema_version": 1, "memories": await self.list_memories()}
