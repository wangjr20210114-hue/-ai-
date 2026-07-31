from __future__ import annotations

import unittest

from agents._domain.identity import TenantIdentity
from agents._infrastructure.makers.repository import MakerRepository


def identity(tenant_id: str, user_id: str) -> TenantIdentity:
    return TenantIdentity(
        tenant_id=tenant_id,
        user_id=user_id,
        auth_type="wechat",
        membership="free",
        session_id=f"session-{tenant_id}-{user_id}",
    )


class MakerRepositoryTests(unittest.TestCase):
    def test_repository_prefixes_tenant_and_user(self) -> None:
        key = MakerRepository.scoped_key(
            identity("tenant-a", "user-1"),
            "workspace",
            "current",
        )
        self.assertEqual(
            key,
            "tenants/tenant-a/users/user-1/workspace/current",
        )

    def test_identical_user_ids_in_two_tenants_are_isolated(self) -> None:
        first = MakerRepository.scoped_key(
            identity("tenant-a", "user-1"),
            "workspace",
            "current",
        )
        second = MakerRepository.scoped_key(
            identity("tenant-b", "user-1"),
            "workspace",
            "current",
        )
        self.assertNotEqual(first, second)

    def test_two_users_in_one_tenant_are_isolated(self) -> None:
        first = MakerRepository.scoped_key(
            identity("tenant-a", "user-1"),
            "evidence",
            "query/hash",
        )
        second = MakerRepository.scoped_key(
            identity("tenant-a", "user-2"),
            "evidence",
            "query/hash",
        )
        self.assertNotEqual(first, second)

    def test_traversal_and_cross_tenant_keys_are_rejected(self) -> None:
        current = identity("tenant-a", "user-1")
        for aggregate, key in (
            ("workspace", "../tenant-b"),
            ("workspace", "/absolute"),
            ("workspace", "tenants/tenant-b"),
            ("../workspace", "current"),
            ("users", "user-2/current"),
        ):
            with self.subTest(aggregate=aggregate, key=key):
                with self.assertRaises(ValueError):
                    MakerRepository.scoped_key(current, aggregate, key)


if __name__ == "__main__":
    unittest.main()
