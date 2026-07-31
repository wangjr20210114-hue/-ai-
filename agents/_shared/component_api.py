"""Versioned website component contracts available to reviewed Skill adapters."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping


COMPONENT_API_VERSION = "2026-07-31"

_COMPONENT_ACTIONS: dict[str, dict[str, Any]] = {
    "chat.progress.publish": {
        "permission": "components.chat",
        "description": "Publish a trusted structured progress stage; raw model reasoning is forbidden.",
        "input": {
            "stage": "planning|retrieval|verification|synthesis|finalizing|complete",
            "activity": "registered-activity-enum",
            "status": "active|completed|skipped",
        },
        "required": ["stage", "status"],
    },
    "search.evidence.publish": {
        "permission": "components.search",
        "description": "Attach verified evidence and source citations to the current answer.",
        "input": {"source_id": "string", "title": "string", "url": "https-url"},
        "required": ["source_id", "title", "url"],
    },
    "search.media.publish": {
        "permission": "components.search",
        "description": "Attach reviewed media to an exact source_id; free-form model placement is not allowed.",
        "input": {"source_id": "string", "media": "reviewed-media[]"},
        "required": ["source_id", "media"],
    },
    "workspace.action.propose": {
        "permission": "components.workspace",
        "description": "Create a typed, user-visible proposal that still requires the platform confirmation policy.",
        "input": {"kind": "registered-action-kind", "payload": "object"},
        "required": ["kind", "payload"],
    },
    "workspace.state.read": {
        "permission": "components.workspace",
        "description": "Read the authenticated user's scoped workspace projection.",
        "input": {"fields": "string[]"},
        "required": ["fields"],
    },
    "files.scoped.read": {
        "permission": "components.files",
        "description": "Read a file only through the authenticated tenant/user Blob prefix.",
        "input": {"storage_key": "tenant-scoped-key"},
        "required": ["storage_key"],
    },
    "files.scoped.upload": {
        "permission": "components.files",
        "description": "Request a tenant-scoped Makers Blob upload URL.",
        "input": {"name": "string", "content_type": "string", "size": "integer"},
        "required": ["name", "content_type", "size"],
    },
    "maps.place.select": {
        "permission": "components.maps",
        "description": "Render provider-verified places or a verified route in the map component.",
        "input": {"places": "verified-place[]", "route": "verified-route?"},
        "required": ["places"],
    },
    "calendar.change.propose": {
        "permission": "components.calendar",
        "description": "Render a versioned calendar change proposal without applying it automatically.",
        "input": {"changes": "calendar-change[]", "warnings": "string[]"},
        "required": ["changes"],
    },
    "image.result.publish": {
        "permission": "components.image",
        "description": "Publish a generated image already persisted under the user's Makers Blob prefix.",
        "input": {"storage_key": "tenant-scoped-key", "versions": "image-version[]"},
        "required": ["storage_key", "versions"],
    },
}

COMPONENT_PERMISSIONS = frozenset(
    str(value["permission"]) for value in _COMPONENT_ACTIONS.values()
)


def known_component_actions() -> frozenset[str]:
    return frozenset(_COMPONENT_ACTIONS)


def component_permission(action: str) -> str:
    value = _COMPONENT_ACTIONS.get(str(action or ""))
    return str((value or {}).get("permission") or "")


def component_envelope(
    action: str,
    payload: Mapping[str, Any],
    *,
    request_id: str,
    tenant_id: str,
    user_id: str,
) -> dict[str, Any]:
    """Build a signed-identity component request from untrusted tool payload."""
    clean_action = str(action or "").strip()
    contract = _COMPONENT_ACTIONS.get(clean_action)
    if contract is None:
        raise ValueError(f"Unknown Floris component action {clean_action!r}")
    if not isinstance(payload, Mapping):
        raise TypeError("Component payload must be an object")
    forbidden = {"tenant_id", "user_id", "request_id", "version", "action"}
    supplied_identity = forbidden.intersection(payload)
    if supplied_identity:
        raise ValueError(
            "Component payload cannot override signed envelope fields "
            f"{sorted(supplied_identity)}"
        )
    missing = [
        field
        for field in contract.get("required") or ()
        if field not in payload
    ]
    if missing:
        raise ValueError(
            f"Component action {clean_action} requires fields {missing}"
        )
    return {
        "version": COMPONENT_API_VERSION,
        "action": clean_action,
        "request_id": str(request_id or ""),
        "tenant_id": str(tenant_id or ""),
        "user_id": str(user_id or ""),
        "payload": dict(payload),
    }


def public_component_api() -> dict[str, Any]:
    return {
        "version": COMPONENT_API_VERSION,
        "actions": [
            {"id": action, **deepcopy(contract)}
            for action, contract in sorted(_COMPONENT_ACTIONS.items())
        ],
        "security": {
            "identity_source": "signed_session",
            "model_is_authorization_boundary": False,
            "tenant_prefix_required": True,
            "raw_chain_of_thought_allowed": False,
        },
    }
