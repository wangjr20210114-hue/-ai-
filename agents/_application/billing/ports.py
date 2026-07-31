"""Provider-neutral billing extension contract."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from ..._domain.identity import TenantIdentity


class BillingUnavailable(RuntimeError):
    """Raised when no reviewed payment provider is configured."""


@dataclass(frozen=True, slots=True)
class CheckoutSession:
    id: str
    url: str


@dataclass(frozen=True, slots=True)
class BillingEvent:
    id: str
    kind: str


@dataclass(frozen=True, slots=True)
class Transaction:
    id: str
    amount: int
    currency: str
    status: str


class BillingProvider(Protocol):
    payment_available: bool

    async def create_checkout(
        self,
        identity: TenantIdentity,
        plan: str,
    ) -> CheckoutSession: ...

    async def verify_webhook(
        self,
        headers: Mapping[str, str],
        body: bytes,
    ) -> BillingEvent: ...

    async def list_transactions(
        self,
        identity: TenantIdentity,
    ) -> Sequence[Transaction]: ...
