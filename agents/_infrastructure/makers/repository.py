"""Canonical tenant/user scoping for EdgeOne Makers repositories."""

from __future__ import annotations

from ..._domain.identity import TenantIdentity


def _relative_path(value: str, field: str, *, nested: bool) -> str:
    path = str(value or "").strip().replace("\\", "/")
    if not path or path.startswith("/") or path.endswith("/"):
        raise ValueError(f"{field} must be a relative Maker key")
    parts = path.split("/")
    if (
        (not nested and len(parts) != 1)
        or any(not part or part in {".", ".."} for part in parts)
        or any(any(ord(character) < 32 for character in part) for part in parts)
        or parts[0] in {"tenants", "users"}
    ):
        raise ValueError(f"{field} contains an unsafe or cross-tenant segment")
    return "/".join(parts)


class MakerRepository:
    """Build Maker-friendly keys while preserving platform isolation semantics."""

    @staticmethod
    def scoped_key(
        identity: TenantIdentity,
        aggregate: str,
        key: str,
    ) -> str:
        if not isinstance(identity, TenantIdentity):
            raise TypeError("identity must be a trusted TenantIdentity")
        aggregate_path = _relative_path(aggregate, "aggregate", nested=False)
        relative_key = _relative_path(key, "key", nested=True)
        return (
            f"tenants/{identity.tenant_id}/users/{identity.user_id}/"
            f"{aggregate_path}/{relative_key}"
        )
