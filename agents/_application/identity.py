"""Application port for resolving a trusted multi-tenant identity."""

from __future__ import annotations

from typing import Any, Protocol

from .._domain.identity import TenantIdentity


class IdentityResolver(Protocol):
    def resolve(self, ctx: Any, request_body: Any = None) -> TenantIdentity: ...


class ResolveIdentity:
    def __init__(self, resolver: IdentityResolver) -> None:
        self._resolver = resolver

    def execute(self, ctx: Any, request_body: Any = None) -> TenantIdentity:
        return self._resolver.resolve(ctx, request_body=request_body)
