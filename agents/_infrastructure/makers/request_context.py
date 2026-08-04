"""Trusted request correlation supplied by the Makers runtime."""

from __future__ import annotations

import uuid
from typing import Any


def maker_request_id(ctx: Any) -> str:
    """Return Makers' run id without trusting browser-controlled input."""
    return str(getattr(ctx, "run_id", "") or "").strip()


def request_id_for_turn(ctx: Any) -> str:
    """Use the native Makers id, with a local-runtime compatibility fallback."""
    return maker_request_id(ctx) or f"chat-{uuid.uuid4().hex}"
