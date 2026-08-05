"""Maker-backed snapshots for reconnectable chat presentation state."""

from __future__ import annotations

import copy
import logging
from typing import Any

from .data_version import namespace as data_namespace


def _item_value(item: Any) -> dict[str, Any] | None:
    if isinstance(item, dict):
        value = item.get("value", item)
    else:
        value = getattr(item, "value", None)
    return copy.deepcopy(value) if isinstance(value, dict) else None


async def load_presentation_snapshot(
    store: Any,
    conversation_id: str,
    run_id: str,
) -> dict[str, Any] | None:
    if store is None or not run_id:
        return None
    try:
        snapshot = _item_value(await store.aget(
            data_namespace("chat_presentation", conversation_id),
            run_id,
        ))
    except Exception as exc:
        logging.warning("chat presentation snapshot read failed: %s", exc)
        return None
    if (
        not isinstance(snapshot, dict)
        or str(snapshot.get("run_id") or "") != str(run_id)
    ):
        return None
    return snapshot


async def save_presentation_snapshot(
    store: Any,
    conversation_id: str,
    run_id: str,
    snapshot: dict[str, Any],
) -> None:
    if store is None or not run_id:
        return
    try:
        await store.aput(
            data_namespace("chat_presentation", conversation_id),
            run_id,
            copy.deepcopy(snapshot),
        )
    except Exception as exc:
        # Presentation recovery is additive. The native LangGraph checkpoint
        # and terminal run marker remain authoritative when this optional
        # projection cannot be written.
        logging.warning("chat presentation snapshot write failed: %s", exc)


async def delete_presentation_snapshot(
    store: Any,
    conversation_id: str,
    run_id: str,
) -> None:
    if store is None or not run_id or not hasattr(store, "adelete"):
        return
    try:
        await store.adelete(
            data_namespace("chat_presentation", conversation_id),
            run_id,
        )
    except Exception as exc:
        logging.warning("chat presentation snapshot cleanup failed: %s", exc)
