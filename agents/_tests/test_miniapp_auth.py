import base64
import hashlib
import hmac
import json
import time
import unittest
from types import SimpleNamespace

from agents._shared.auth import (
    conversation_prefix_for_user,
    require_user,
    scoped_conversation_id,
)
from agents._shared.workspace import USER_WORKSPACE_ID


def token_for(user_id: str, secret: str, expires_at: int | None = None) -> str:
    payload = {
        "v": 1,
        "sub": user_id,
        "name": "微信用户",
        "exp": expires_at or int(time.time()) + 60,
        "conversation_prefix": conversation_prefix_for_user(user_id),
    }
    encoded = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ).decode("ascii").rstrip("=")
    signature = base64.urlsafe_b64encode(
        hmac.new(secret.encode("utf-8"), encoded.encode("ascii"), hashlib.sha256).digest()
    ).decode("ascii").rstrip("=")
    return f"{encoded}.{signature}"


class MiniappAuthTests(unittest.TestCase):
    def test_request_without_token_keeps_personal_web_owner(self):
        identity = require_user(SimpleNamespace())
        self.assertEqual(identity["user_id"], USER_WORKSPACE_ID)

    def test_signed_session_is_read_by_every_agent_handler(self):
        secret = "test-only-miniapp-session-secret"
        user_id = "wx_1234567890abcdef12345678"
        token = token_for(user_id, secret)
        ctx = SimpleNamespace(
            request=SimpleNamespace(headers={"Authorization": f"Bearer {token}"}),
            env={"MINIAPP_SESSION_SECRET": secret},
        )
        identity = require_user(ctx)
        self.assertEqual(identity["user_id"], user_id)
        conversation_id = f"{identity['conversation_prefix']}abc123"
        self.assertEqual(
            scoped_conversation_id(ctx, user_id, conversation_id),
            conversation_id,
        )
        with self.assertRaisesRegex(ValueError, "无效会话"):
            scoped_conversation_id(ctx, user_id, "yb7_other-user_abc")

    def test_invalid_or_expired_token_is_rejected(self):
        secret = "test-only-miniapp-session-secret"
        expired = token_for(
            "wx_1234567890abcdef12345678",
            secret,
            int(time.time()) - 1,
        )
        ctx = SimpleNamespace(
            request=SimpleNamespace(headers={"authorization": f"Bearer {expired}"}),
            env={"MINIAPP_SESSION_SECRET": secret},
        )
        with self.assertRaisesRegex(ValueError, "Unauthorized"):
            require_user(ctx)


if __name__ == "__main__":
    unittest.main()
