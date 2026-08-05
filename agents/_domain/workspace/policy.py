"""Deterministic workspace action integrity policy."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .models import WorkspaceSnapshotError


def action_snapshot_hash(kind: str, payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        {"kind": str(kind), "payload": payload},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def seal_action_snapshot(action: dict[str, Any]) -> None:
    digest = action_snapshot_hash(
        str(action.get("kind") or ""),
        action.get("payload") or {},
    )
    action["snapshot_hash"] = digest
    action["idempotency_key"] = f"{action.get('id')}:{digest[:16]}"


def verify_action_snapshot(action: dict[str, Any]) -> None:
    expected = str(action.get("snapshot_hash") or "")
    actual = action_snapshot_hash(
        str(action.get("kind") or ""),
        action.get("payload") or {},
    )
    if expected and expected != actual:
        raise WorkspaceSnapshotError
    if not expected:
        action["snapshot_hash"] = actual
        action["idempotency_key"] = str(
            action.get("idempotency_key")
            or f"{action.get('id')}:{actual[:16]}"
        )
