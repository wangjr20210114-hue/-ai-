"""Shared lifecycle rules for one chat turn.

The Makers LangGraph checkpoint is a trusted runtime cache, not the public
transcript.  A turn becomes visible and reusable as dialogue context only
after its run reaches ``completed``.  Explicitly stopped turns remain in the
checkpoint for platform diagnostics but are never projected back to a client
or supplied to a later model call.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Literal


TurnProjection = Literal["committed", "pending", "discarded", "legacy"]


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    try:
        return getattr(value, name, default)
    except (AttributeError, KeyError, TypeError):
        return default


def checkpoint_client_message_id(message: Any) -> str:
    additional = _field(message, "additional_kwargs", {}) or {}
    if not isinstance(additional, dict):
        return ""
    return str(additional.get("floris_client_message_id") or "").strip()


def turn_projection(
    run: dict[str, Any] | None,
    client_message_id: str,
) -> TurnProjection:
    """Resolve whether one checkpoint turn may cross the public boundary."""
    client_id = str(client_message_id or "").strip()
    if not client_id or not isinstance(run, dict):
        return "legacy"
    discarded = {
        str(value)
        for value in (run.get("discarded_client_message_ids") or [])
        if str(value)
    }
    if client_id in discarded:
        return "discarded"
    if client_id != str(run.get("client_message_id") or ""):
        return "committed"
    status = str(run.get("status") or "")
    if status == "completed":
        return "committed"
    if status == "cancelled":
        return "discarded"
    if status in {"running", "cancel_requested"}:
        return "pending"
    # Failed or unknown terminal runs must not promote a checkpoint fragment.
    return "discarded"


def committed_checkpoint_messages(
    messages: Iterable[Any],
    run: dict[str, Any] | None,
) -> list[Any]:
    """Return model-safe history with pending/stopped turns removed entirely."""
    output: list[Any] = []
    projection: TurnProjection = "legacy"
    for message in messages:
        role = str(
            _field(message, "type", _field(message, "role", "")) or ""
        ).lower()
        if role in {"human", "user"}:
            projection = turn_projection(
                run,
                checkpoint_client_message_id(message),
            )
        if projection in {"pending", "discarded"}:
            continue
        output.append(message)
    return output


__all__ = (
    "TurnProjection",
    "checkpoint_client_message_id",
    "committed_checkpoint_messages",
    "turn_projection",
)
