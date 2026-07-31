"""Compatibility exports for signed Maker identity infrastructure."""

from .._infrastructure.makers.identity import (
    AuthError,
    MakerIdentityResolver,
    require_user,
    required_user_id,
    scoped_conversation_id,
    tenant_storage_prefix,
)

__all__ = (
    "AuthError",
    "MakerIdentityResolver",
    "require_user",
    "required_user_id",
    "scoped_conversation_id",
    "tenant_storage_prefix",
)
