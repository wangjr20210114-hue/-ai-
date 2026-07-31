"""Versioned website component contracts available to reviewed Skill adapters."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


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
    },
    "search.evidence.publish": {
        "permission": "components.search",
        "description": "Attach verified evidence and source citations to the current answer.",
        "input": {"source_id": "string", "title": "string", "url": "https-url"},
    },
    "search.media.publish": {
        "permission": "components.search",
        "description": "Attach reviewed media to an exact source_id; free-form model placement is not allowed.",
        "input": {"source_id": "string", "media": "reviewed-media[]"},
    },
    "workspace.action.propose": {
        "permission": "components.workspace",
        "description": "Create a typed, user-visible proposal that still requires the platform confirmation policy.",
        "input": {"kind": "registered-action-kind", "payload": "object"},
    },
    "workspace.state.read": {
        "permission": "components.workspace",
        "description": "Read the authenticated user's scoped workspace projection.",
        "input": {"fields": "string[]"},
    },
    "files.scoped.read": {
        "permission": "components.files",
        "description": "Read a file only through the authenticated tenant/user Blob prefix.",
        "input": {"storage_key": "tenant-scoped-key"},
    },
    "files.scoped.upload": {
        "permission": "components.files",
        "description": "Request a tenant-scoped Makers Blob upload URL.",
        "input": {"name": "string", "content_type": "string", "size": "integer"},
    },
    "maps.place.select": {
        "permission": "components.maps",
        "description": "Render provider-verified places or a verified route in the map component.",
        "input": {"places": "verified-place[]", "route": "verified-route?"},
    },
    "calendar.change.propose": {
        "permission": "components.calendar",
        "description": "Render a versioned calendar change proposal without applying it automatically.",
        "input": {"changes": "calendar-change[]", "warnings": "string[]"},
    },
    "image.result.publish": {
        "permission": "components.image",
        "description": "Publish a generated image already persisted under the user's Makers Blob prefix.",
        "input": {"storage_key": "tenant-scoped-key", "versions": "image-version[]"},
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
