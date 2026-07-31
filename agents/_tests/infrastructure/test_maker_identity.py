from __future__ import annotations

import unittest
from types import SimpleNamespace

from agents._domain.identity import TenantIdentity
from agents._infrastructure.makers.identity import AuthError, MakerIdentityResolver
from agents._tests.auth_helpers import authenticated_context


def signed_context(**identity):
    return authenticated_context(SimpleNamespace(), **identity)


class MakerIdentityResolverTests(unittest.TestCase):
    def test_request_body_cannot_override_signed_identity(self) -> None:
        ctx = signed_context(
            tenant_id="tenant-a",
            subject_id="user-1",
            session_id="session-a",
        )
        identity = MakerIdentityResolver().resolve(
            ctx,
            request_body={"tenant_id": "tenant-b", "user_id": "attacker"},
        )
        self.assertEqual(
            (identity.tenant_id, identity.user_id),
            ("tenant-a", "user-1"),
        )

    def test_guest_sessions_receive_distinct_signed_subjects(self) -> None:
        first = MakerIdentityResolver().resolve(
            signed_context(
                auth_type="guest",
                membership="guest",
                subject_id="guest-1",
                session_id="guest-session-1",
            )
        )
        second = MakerIdentityResolver().resolve(
            signed_context(
                auth_type="guest",
                membership="guest",
                subject_id="guest-2",
                session_id="guest-session-2",
            )
        )
        self.assertIsInstance(first, TenantIdentity)
        self.assertNotEqual(first.user_id, second.user_id)
        self.assertNotEqual(first.session_id, second.session_id)

    def test_invalid_signature_is_rejected(self) -> None:
        ctx = signed_context(subject_id="user-1")
        ctx.request.headers["cookie"] += "tampered"
        with self.assertRaises(AuthError):
            MakerIdentityResolver().resolve(ctx)


if __name__ == "__main__":
    unittest.main()
