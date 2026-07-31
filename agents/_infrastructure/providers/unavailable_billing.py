"""Explicit no-payment adapter used until a reviewed provider is connected."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from ..._application.billing.ports import (
    BillingEvent,
    BillingUnavailable,
    CheckoutSession,
    Transaction,
)
from ..._domain.identity import TenantIdentity


class UnavailableBillingProvider:
    payment_available = False

    async def create_checkout(
        self,
        identity: TenantIdentity,
        plan: str,
    ) -> CheckoutSession:
        del identity, plan
        raise BillingUnavailable("Billing checkout is not configured")

    async def verify_webhook(
        self,
        headers: Mapping[str, str],
        body: bytes,
    ) -> BillingEvent:
        del headers, body
        raise BillingUnavailable("Billing webhook verification is not configured")

    async def list_transactions(
        self,
        identity: TenantIdentity,
    ) -> Sequence[Transaction]:
        del identity
        return ()
