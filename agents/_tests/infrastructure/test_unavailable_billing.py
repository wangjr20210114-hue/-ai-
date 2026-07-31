from __future__ import annotations

import unittest

from agents._application.billing.ports import BillingUnavailable
from agents._domain.identity import TenantIdentity
from agents._infrastructure.providers.unavailable_billing import (
    UnavailableBillingProvider,
)


class UnavailableBillingProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_provider_is_explicitly_unavailable_without_external_calls(self) -> None:
        provider = UnavailableBillingProvider()
        identity = TenantIdentity(
            tenant_id="tenant-a",
            user_id="user-1",
            auth_type="wechat",
            membership="free",
            session_id="session-1",
        )
        self.assertFalse(provider.payment_available)
        with self.assertRaises(BillingUnavailable):
            await provider.create_checkout(identity, "plus")
        with self.assertRaises(BillingUnavailable):
            await provider.verify_webhook({}, b"")
        self.assertEqual(await provider.list_transactions(identity), ())


if __name__ == "__main__":
    unittest.main()
