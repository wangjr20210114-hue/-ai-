from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from types import SimpleNamespace


TEST_JWT_SECRET = "test-only-jwt-secret-with-more-than-32-characters"
TEST_SUBJECT_ID = "11111111-1111-4111-8111-111111111111"
TEST_USER_ID = f"floris:{TEST_SUBJECT_ID}"


class InMemoryConversationIndexStore:
    def __init__(self):
        self.values: dict[str, object] = {}

    async def get(self, key: str, **_options):
        return self.values.get(key)

    async def set_json(self, key: str, value, **_options) -> None:
        self.values[key] = value


def _base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def session_token(
    *,
    auth_type: str = "wechat",
    membership: str = "free",
    roles: list[str] | None = None,
    subject_id: str = TEST_SUBJECT_ID,
    tenant_id: str = "floris",
    session_id: str = "test-session",
) -> str:
    header = _base64url(json.dumps(
        {"alg": "HS256", "typ": "JWT"},
        separators=(",", ":"),
    ).encode("utf-8"))
    now = int(time.time())
    payload = _base64url(json.dumps({
        "sub": subject_id,
        "tenant_id": tenant_id,
        "sid": session_id,
        "username": "tester",
        "display_name": "测试用户",
        "avatar_url": "",
        "auth_type": auth_type,
        "membership": membership,
        "roles": roles or (["guest"] if auth_type == "guest" else ["user"]),
        "session_version": 1,
        "iat": now,
        "exp": now + 1_000_000_000,
    }, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    body = f"{header}.{payload}"
    signature = _base64url(hmac.new(
        TEST_JWT_SECRET.encode("utf-8"),
        body.encode("utf-8"),
        hashlib.sha256,
    ).digest())
    return f"{body}.{signature}"


def auth_headers(**identity) -> dict[str, str]:
    return {"cookie": f"floris_session={session_token(**identity)}"}


def auth_env(**values) -> dict[str, str]:
    return {"JWT_SECRET": TEST_JWT_SECRET, **values}


def authenticated_context(ctx, **identity):
    env = getattr(ctx, "env", None)
    ctx.env = auth_env(**(env if isinstance(env, dict) else {}))
    request = getattr(ctx, "request", None)
    if request is None:
        request = SimpleNamespace(body={}, headers={})
        ctx.request = request
    headers = getattr(request, "headers", None)
    if not isinstance(headers, dict):
        headers = {}
    request.headers = {**headers, **auth_headers(**identity)}
    return ctx


def authenticated_namespace(**values):
    values.setdefault("conversation_index_store", InMemoryConversationIndexStore())
    return authenticated_context(SimpleNamespace(**values))
