"""Trusted tenant identity used by application and Maker repository boundaries."""

from __future__ import annotations

from dataclasses import dataclass

from .entitlements.policy import normalize_membership
from .entitlements.generated_contract import AUTH_TYPES


def _required_segment(value: str, field: str) -> str:
    segment = str(value or "").strip()
    if (
        not segment
        or segment in {".", ".."}
        or "/" in segment
        or "\\" in segment
        or any(ord(character) < 32 for character in segment)
    ):
        raise ValueError(f"{field} must be a non-empty safe path segment")
    return segment


@dataclass(frozen=True, slots=True)
class TenantIdentity:
    tenant_id: str
    user_id: str
    auth_type: str
    membership: str
    session_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "tenant_id",
            _required_segment(self.tenant_id, "tenant_id"),
        )
        object.__setattr__(
            self,
            "user_id",
            _required_segment(self.user_id, "user_id"),
        )
        object.__setattr__(
            self,
            "session_id",
            _required_segment(self.session_id, "session_id"),
        )
        auth_type = str(self.auth_type or "").strip().lower()
        if auth_type not in AUTH_TYPES:
            raise ValueError(
                f"auth_type must be one of {', '.join(AUTH_TYPES)}"
            )
        object.__setattr__(self, "auth_type", auth_type)
        object.__setattr__(
            self,
            "membership",
            normalize_membership(self.membership, auth_type),
        )

    @property
    def storage_user_id(self) -> str:
        return f"{self.tenant_id}:{self.user_id}"
