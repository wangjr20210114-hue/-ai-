"""Identity adapter shared by every Makers Agent route.

The existing web client remains the personal local owner. WeChat mini-program
requests carry a short-lived HMAC session issued after ``wx.login``; business
state continues to live in Makers stores and is scoped by the derived user id.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

from .data_version import scoped_conversation
from .workspace import USER_WORKSPACE_ID


def _header(ctx: Any, name: str) -> str:
    request = getattr(ctx, "request", None)
    headers = getattr(request, "headers", {}) or {}
    getter = getattr(headers, "get", None)
    if callable(getter):
        for candidate in (name, name.lower(), name.title()):
            value = getter(candidate)
            if value:
                return str(value)
    try:
        for key, value in headers.items():
            if str(key).lower() == name.lower():
                return str(value)
    except (AttributeError, TypeError):
        pass
    return ""


def _environment(ctx: Any, name: str) -> str:
    env = getattr(ctx, "env", {}) or {}
    getter = getattr(env, "get", None)
    return str(getter(name) or "") if callable(getter) else ""


def _decode_payload(value: str) -> dict[str, Any]:
    padded = value + "=" * (-len(value) % 4)
    return json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))


def conversation_prefix_for_user(user_id: str) -> str:
    if user_id == USER_WORKSPACE_ID:
        return "yb7_"
    tag = "".join(character for character in str(user_id) if character.isalnum())[-10:]
    if not tag:
        raise ValueError("无效用户身份")
    return f"yb7_{tag}_"


def _verify_miniapp_session(token: str, secret: str, now: float | None = None) -> dict[str, Any]:
    try:
        payload, supplied_signature = token.split(".")
        expected_signature = (
            base64.urlsafe_b64encode(
                hmac.new(secret.encode("utf-8"), payload.encode("ascii"), hashlib.sha256).digest()
            )
            .decode("ascii")
            .rstrip("=")
        )
        if not hmac.compare_digest(supplied_signature, expected_signature):
            raise ValueError("Unauthorized")
        claims = _decode_payload(payload)
        user_id = str(claims.get("sub") or "")
        prefix = conversation_prefix_for_user(user_id)
        if (
            claims.get("v") != 1
            or not user_id.startswith("wx_")
            or int(claims.get("exp") or 0) <= int(now if now is not None else time.time())
            or claims.get("conversation_prefix") != prefix
        ):
            raise ValueError("Unauthorized")
    except (TypeError, ValueError, KeyError, json.JSONDecodeError, UnicodeDecodeError):
        raise ValueError("Unauthorized") from None
    return {
        "user_id": user_id,
        "username": str(claims.get("name") or "微信用户"),
        "roles": ["member"],
        "system": False,
        "conversation_prefix": prefix,
    }


def require_user(ctx: Any) -> dict[str, Any]:
    authorization = _header(ctx, "authorization")
    if authorization:
        prefix, _, token = authorization.partition(" ")
        secret = _environment(ctx, "MINIAPP_SESSION_SECRET")
        if prefix.lower() != "bearer" or not token.strip() or not secret:
            raise ValueError("Unauthorized")
        return _verify_miniapp_session(token.strip(), secret)
    return {
        "user_id": USER_WORKSPACE_ID,
        "username": "local-user",
        "roles": ["owner"],
        "system": False,
        "conversation_prefix": conversation_prefix_for_user(USER_WORKSPACE_ID),
    }


def scoped_conversation_id(ctx: Any, user_id: str, conversation_id: str | None = None) -> str:
    raw = str(conversation_id if conversation_id is not None else getattr(ctx, "conversation_id", "") or "")
    if not raw or len(raw) > 180:
        raise ValueError("无效会话 ID")
    if user_id != USER_WORKSPACE_ID:
        expected_prefix = conversation_prefix_for_user(user_id)
        if (
            len(raw) > 36
            or not raw.startswith(expected_prefix)
            or any(character not in "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz._-" for character in raw)
        ):
            raise ValueError("无效会话 ID")
        return raw
    return scoped_conversation(raw)
