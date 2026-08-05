from __future__ import annotations

import unittest
from types import SimpleNamespace

from agents._domain.identity import TenantIdentity
from agents._infrastructure.makers.identity import AuthError, MakerIdentityResolver, conversation_index_user_id
from agents._infrastructure.makers.request_context import (
    maker_request_id,
    request_id_for_turn,
)
from agents._tests.auth_helpers import authenticated_context, auth_env, session_token


def signed_context(**identity):
    return authenticated_context(SimpleNamespace(), **identity)


class MakerIdentityResolverTests(unittest.TestCase):
    def test_request_correlation_uses_only_the_makers_run_id(self) -> None:
        ctx = SimpleNamespace(
            run_id="maker-run-1",
            request=SimpleNamespace(
                body={"request_id": "browser-forged"},
                headers={"x-request-id": "header-forged"},
            ),
        )
        self.assertEqual(maker_request_id(ctx), "maker-run-1")
        self.assertEqual(request_id_for_turn(ctx), "maker-run-1")

    def test_local_runtime_gets_a_unique_compatibility_request_id(self) -> None:
        first = request_id_for_turn(SimpleNamespace())
        second = request_id_for_turn(SimpleNamespace())
        self.assertRegex(first, r"^chat-[0-9a-f]{32}$")
        self.assertNotEqual(first, second)

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

    def test_cloudbase_session_is_a_supported_trusted_identity(self) -> None:
        identity = MakerIdentityResolver().resolve(
            signed_context(
                auth_type="cloudbase",
                membership="free",
                subject_id="cloudbase-user-1",
                session_id="cloudbase-session-1",
            )
        )
        self.assertEqual(identity.auth_type, "cloudbase")
        self.assertEqual(identity.membership, "free")

    def test_native_bearer_uses_the_same_signed_tenant_identity(self) -> None:
        token = session_token(
            auth_type="cloudbase",
            membership="plus",
            subject_id="native-user-1",
            tenant_id="tenant-mobile",
        )
        ctx = SimpleNamespace(
            env=auth_env(),
            request=SimpleNamespace(headers={
                "authorization": f"Bearer {token}",
            }),
        )
        identity = MakerIdentityResolver().resolve(ctx)
        self.assertEqual(identity.tenant_id, "tenant-mobile")
        self.assertEqual(identity.user_id, "native-user-1")
        self.assertEqual(identity.auth_type, "cloudbase")
        self.assertEqual(identity.membership, "plus")

    def test_native_bearer_wins_over_an_unrelated_webview_cookie(self) -> None:
        cookie_token = session_token(
            auth_type="guest",
            membership="guest",
            subject_id="webview-guest",
        )
        bearer_token = session_token(
            auth_type="cloudbase",
            membership="free",
            subject_id="native-user-2",
        )
        ctx = SimpleNamespace(
            env=auth_env(),
            request=SimpleNamespace(headers={
                "cookie": f"floris_session={cookie_token}",
                "authorization": f"Bearer {bearer_token}",
            }),
        )
        identity = MakerIdentityResolver().resolve(ctx)
        self.assertEqual(identity.user_id, "native-user-2")
        self.assertEqual(identity.auth_type, "cloudbase")

    def test_invalid_signature_is_rejected(self) -> None:
        ctx = signed_context(subject_id="user-1")
        ctx.request.headers["cookie"] += "tampered"
        with self.assertRaises(AuthError):
            MakerIdentityResolver().resolve(ctx)

    def test_conversation_index_user_id_matches_the_node_contract(self) -> None:
        self.assertEqual(
            conversation_index_user_id(
                "floris:11111111-1111-4111-8111-111111111111"
            ),
            "uid_e236542cf226407ddc32fea8e80052d0bfde5881",
        )


if __name__ == "__main__":
    unittest.main()
