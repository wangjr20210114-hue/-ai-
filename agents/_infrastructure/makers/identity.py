"""Resolve signed EdgeOne Maker session identity."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

from ..._domain.identity import TenantIdentity
from .data_version import CONVERSATION_PREFIX


class AuthError(ValueError):
    """A public authentication failure without leaking token details."""


def required_user_id(value: Any) -> str:
    """Fail closed when a storage/model operation lacks authenticated scope."""
    user_id = str(value or "").strip()
    if not user_id:
        raise AuthError("缺少经过验证的用户身份")
    return user_id


def conversation_index_user_id(user_id: Any) -> str:
    """Return the canonical path-safe Makers user-index identifier."""
    value = required_user_id(user_id)
    return f"uid_{hashlib.sha256(value.encode('utf-8')).hexdigest()[:40]}"


def _mapping_value(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _env_value(env: Any, key: str) -> str:
    if isinstance(env, dict):
        return str(env.get(key) or "")
    getter = getattr(env, "get", None)
    if callable(getter):
        return str(getter(key) or "")
    return str(getattr(env, key, "") or "")


def _request_header(ctx: Any, name: str) -> str:
    request = getattr(ctx, "request", None)
    headers = _mapping_value(request, "headers", {}) or {}
    getter = getattr(headers, "get", None)
    if callable(getter):
        return str(getter(name) or getter(name.lower()) or "")
    if isinstance(headers, dict):
        return str(
            headers.get(name)
            or headers.get(name.lower())
            or headers.get(name.title())
            or ""
        )
    return ""


def _cookie(ctx: Any, name: str) -> str:
    for part in _request_header(ctx, "cookie").split(";"):
        key, separator, value = part.strip().partition("=")
        if separator and key == name:
            return value.strip()
    return ""


def _session_token(ctx: Any) -> str:
    authorization = _request_header(ctx, "authorization").strip()
    scheme, separator, value = authorization.partition(" ")
    if separator and scheme.lower() == "bearer" and value.strip():
        return value.strip()
    return _cookie(ctx, "floris_session")


def _base64url_decode(value: str) -> bytes:
    raw = str(value or "").replace("-", "+").replace("_", "/")
    return base64.b64decode(raw + "=" * ((4 - len(raw) % 4) % 4))


def _verify_session(token: str, secret: str) -> dict[str, Any]:
    parts = str(token or "").split(".")
    if len(parts) != 3:
        raise AuthError("需要有效的登录会话")
    try:
        header = json.loads(_base64url_decode(parts[0]).decode("utf-8"))
        payload = json.loads(_base64url_decode(parts[1]).decode("utf-8"))
        supplied_signature = _base64url_decode(parts[2])
    except Exception as exc:
        raise AuthError("登录会话格式无效") from exc
    if header.get("alg") != "HS256" or header.get("typ") != "JWT":
        raise AuthError("登录会话算法无效")
    expected_signature = hmac.new(
        secret.encode("utf-8"),
        f"{parts[0]}.{parts[1]}".encode("utf-8"),
        hashlib.sha256,
    ).digest()
    if not hmac.compare_digest(supplied_signature, expected_signature):
        raise AuthError("登录会话签名无效")
    now = int(time.time())
    if int(payload.get("exp") or 0) <= now:
        raise AuthError("登录会话已过期")
    if int(payload.get("nbf") or 0) > now:
        raise AuthError("登录会话尚未生效")
    return payload


def _safe_segment(value: Any, fallback: str) -> str:
    output = "".join(
        character if character.isascii() and (
            character.isalnum() or character in "._-"
        ) else "-"
        for character in str(value or "").strip()
    ).strip("-")[:96]
    return output or fallback


def _identity_from_payload(
    payload: dict[str, Any],
    token: str,
) -> TenantIdentity:
    tenant_id = str(payload.get("tenant_id") or "").strip()
    subject_id = str(
        payload.get("sub") or payload.get("subject_id") or ""
    ).strip()
    if not tenant_id or not subject_id:
        raise AuthError("登录会话缺少租户或用户身份")
    session_id = str(
        payload.get("sid")
        or payload.get("jti")
        or hashlib.sha256(token.encode("utf-8")).hexdigest()[:32]
    ).strip()
    try:
        return TenantIdentity(
            tenant_id=tenant_id,
            user_id=subject_id,
            auth_type=str(payload.get("auth_type") or "guest"),
            membership=str(payload.get("membership") or ""),
            session_id=session_id,
        )
    except ValueError as exc:
        raise AuthError(str(exc)) from exc


class MakerIdentityResolver:
    """Resolve only a signed session; request and model values are ignored."""

    def resolve(
        self,
        ctx: Any,
        request_body: Any = None,
    ) -> TenantIdentity:
        del request_body
        env = getattr(ctx, "env", None) or {}
        secret = _env_value(env, "JWT_SECRET").strip()
        if len(secret) < 32:
            raise AuthError("服务端登录签名尚未配置")
        token = _session_token(ctx)
        return _identity_from_payload(_verify_session(token, secret), token)


def require_user(ctx: Any) -> dict[str, Any]:
    env = getattr(ctx, "env", None) or {}
    secret = _env_value(env, "JWT_SECRET").strip()
    if len(secret) < 32:
        raise AuthError("服务端登录签名尚未配置")
    token = _session_token(ctx)
    payload = _verify_session(token, secret)
    identity = _identity_from_payload(payload, token)
    tenant_id = identity.tenant_id
    subject_id = identity.user_id
    auth_type = identity.auth_type
    membership = identity.membership
    roles = payload.get("roles")
    return {
        "user_id": f"{tenant_id}:{subject_id}",
        "subject_id": subject_id,
        "tenant_id": tenant_id,
        "username": str(
            payload.get("username")
            or payload.get("display_name")
            or auth_type
        )[:80],
        "display_name": str(payload.get("display_name") or "")[:120],
        "avatar_url": str(payload.get("avatar_url") or "")[:1000],
        "auth_type": auth_type,
        "membership": membership,
        "roles": (
            [str(value) for value in roles if str(value)][:8]
            if isinstance(roles, list)
            else ["guest" if auth_type == "guest" else "user"]
        ),
        "session_version": max(1, int(payload.get("session_version") or 1)),
        "session_id": identity.session_id,
        "system": False,
    }


def scoped_conversation_id(ctx: Any, user_id: str, conversation_id: str | None = None) -> str:
    raw = str(conversation_id if conversation_id is not None else getattr(ctx, "conversation_id", "") or "")
    if not raw or len(raw) > 180:
        raise ValueError("无效会话 ID")
    digest = hashlib.sha256(
        f"{str(user_id or '')}:{raw}".encode("utf-8")
    ).hexdigest()[:32]
    return f"{CONVERSATION_PREFIX}{digest}"


def tenant_storage_prefix(identity_or_user_id: Any) -> str:
    """Return the canonical Makers Blob prefix for one authenticated subject."""
    if isinstance(identity_or_user_id, TenantIdentity):
        tenant_id = identity_or_user_id.tenant_id
        subject_id = identity_or_user_id.user_id
    elif isinstance(identity_or_user_id, dict):
        tenant_id = _safe_segment(identity_or_user_id.get("tenant_id"), "default")
        subject_id = _safe_segment(identity_or_user_id.get("subject_id"), "anonymous")
    else:
        tenant, separator, subject = required_user_id(identity_or_user_id).partition(":")
        tenant_id = _safe_segment(tenant if separator else "", "default")
        subject_id = _safe_segment(subject if separator else tenant, "anonymous")
    return f"tenants/{tenant_id}/users/{subject_id}/"
