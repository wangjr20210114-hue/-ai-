from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class SignedIdentity:
    tenant_id: str
    user_id: str
    subject_id: str
    membership: str
    auth_type: str = "wechat"
    trusted: bool = True


def signed_identity(
    tenant_id: str = "tenant-a",
    user_id: str = "user-1",
    membership: str = "free",
) -> SignedIdentity:
    """Return an explicit trusted identity without deriving it from request data."""
    return SignedIdentity(
        tenant_id=tenant_id,
        user_id=user_id,
        subject_id=f"{tenant_id}:{user_id}",
        membership=membership,
    )


def deterministic_clock(
    value: datetime = datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc),
):
    return lambda: value


def deterministic_ids(prefix: str = "test") -> Iterator[str]:
    index = 0
    while True:
        index += 1
        yield f"{prefix}-{index:04d}"
