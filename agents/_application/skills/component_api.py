"""Versioned component contracts available to reviewed Skill adapters."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from ..i18n import localized_values, text


def _name(action: str) -> dict[str, str]:
    return localized_values(f"component.{action}.name")


def _description(action: str) -> dict[str, str]:
    return localized_values(f"component.{action}.description")


COMPONENT_API_VERSION = "2026-08-04"

# Trusted adapters can use every action below, but the marketplace documentation
# is deliberately smaller: it only describes components that a Skill author can
# render for a user. Session recovery, storage and orchestration remain platform
# capabilities instead of becoming a second public infrastructure API.
PUBLIC_COMPONENT_ACTIONS = frozenset({
    "clarification.request",
    "search.evidence.publish",
    "search.media.publish",
    "maps.place.select",
    "calendar.change.propose",
    "paper.results.publish",
    "image.result.publish",
    "workspace.action.propose",
})

_COMPONENT_ACTIONS: dict[str, dict[str, Any]] = {
    "clarification.request": {
        "category": "chat",
        "name": _name("clarification.request"),
        "permission": "components.chat",
        "description": text("component.clarification.request.description", "en"),
        "description_i18n": _description("clarification.request"),
        "input": {"clarification": "clarification"},
        "required": ["clarification"],
    },
    "chat.progress.publish": {
        "category": "chat",
        "name": _name("chat.progress.publish"),
        "permission": "components.chat",
        "description": text("component.chat.progress.publish.description", "en"),
        "description_i18n": _description("chat.progress.publish"),
        "input": {
            "stage": "planning|retrieval|verification|synthesis|finalizing|complete",
            "activity": "registered-activity-enum",
            "status": "active|completed|skipped",
        },
        "required": ["stage", "status"],
    },
    "search.evidence.publish": {
        "category": "search",
        "name": _name("search.evidence.publish"),
        "permission": "components.search",
        "description": text("component.search.evidence.publish.description", "en"),
        "description_i18n": _description("search.evidence.publish"),
        "input": {"source_id": "string", "title": "string", "url": "https-url"},
        "required": ["source_id", "title", "url"],
    },
    "search.media.publish": {
        "category": "search",
        "name": _name("search.media.publish"),
        "permission": "components.search",
        "description": text("component.search.media.publish.description", "en"),
        "description_i18n": _description("search.media.publish"),
        "input": {"source_id": "string", "media": "reviewed-media[]"},
        "required": ["source_id", "media"],
    },
    "workspace.action.propose": {
        "category": "workspace",
        "name": _name("workspace.action.propose"),
        "permission": "components.workspace",
        "description": text("component.workspace.action.propose.description", "en"),
        "description_i18n": _description("workspace.action.propose"),
        "input": {"kind": "registered-action-kind", "payload": "object"},
        "required": ["kind", "payload"],
    },
    "workspace.state.read": {
        "category": "workspace",
        "name": _name("workspace.state.read"),
        "permission": "components.workspace",
        "description": text("component.workspace.state.read.description", "en"),
        "description_i18n": _description("workspace.state.read"),
        "input": {"fields": "string[]"},
        "required": ["fields"],
    },
    "files.scoped.read": {
        "category": "files",
        "name": _name("files.scoped.read"),
        "permission": "components.files",
        "description": text("component.files.scoped.read.description", "en"),
        "description_i18n": _description("files.scoped.read"),
        "input": {"storage_key": "tenant-scoped-key"},
        "required": ["storage_key"],
    },
    "files.scoped.upload": {
        "category": "files",
        "name": _name("files.scoped.upload"),
        "permission": "components.files",
        "description": text("component.files.scoped.upload.description", "en"),
        "description_i18n": _description("files.scoped.upload"),
        "input": {"name": "string", "content_type": "string", "size": "integer"},
        "required": ["name", "content_type", "size"],
    },
    "maps.place.select": {
        "category": "maps",
        "name": _name("maps.place.select"),
        "permission": "components.maps",
        "description": text("component.maps.place.select.description", "en"),
        "description_i18n": _description("maps.place.select"),
        "input": {"places": "verified-place[]", "route": "verified-route?"},
        "required": ["places"],
    },
    "calendar.change.propose": {
        "category": "calendar",
        "name": _name("calendar.change.propose"),
        "permission": "components.calendar",
        "description": text("component.calendar.change.propose.description", "en"),
        "description_i18n": _description("calendar.change.propose"),
        "input": {"changes": "calendar-change[]", "warnings": "string[]"},
        "required": ["changes"],
    },
    "paper.results.publish": {
        "category": "paper",
        "name": _name("paper.results.publish"),
        "permission": "components.paper",
        "description": text("component.paper.results.publish.description", "en"),
        "description_i18n": _description("paper.results.publish"),
        "input": {"papers": "verified-paper[]", "topic": "string"},
        "required": ["papers"],
    },
    "image.result.publish": {
        "category": "image",
        "name": _name("image.result.publish"),
        "permission": "components.image",
        "description": text("component.image.result.publish.description", "en"),
        "description_i18n": _description("image.result.publish"),
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
    publication_key: str = "",
) -> dict[str, Any]:
    """Build a signed-identity component request from untrusted tool payload."""
    clean_action = str(action or "").strip()
    contract = _COMPONENT_ACTIONS.get(clean_action)
    if contract is None:
        raise ValueError(f"Unknown Floris component action {clean_action!r}")
    if not isinstance(payload, Mapping):
        raise TypeError("Component payload must be an object")
    forbidden = {
        "tenant_id",
        "user_id",
        "request_id",
        "publication_key",
        "version",
        "action",
    }
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
    envelope = {
        "version": COMPONENT_API_VERSION,
        "action": clean_action,
        "request_id": str(request_id or ""),
        "tenant_id": str(tenant_id or ""),
        "user_id": str(user_id or ""),
        "payload": dict(payload),
    }
    if publication_key:
        envelope["publication_key"] = str(publication_key)
    return envelope


def public_component_api() -> dict[str, Any]:
    return {
        "version": COMPONENT_API_VERSION,
        "actions": [
            {"id": action, **deepcopy(contract)}
            for action, contract in sorted(_COMPONENT_ACTIONS.items())
            if action in PUBLIC_COMPONENT_ACTIONS
        ],
        "security": {
            "identity_source": "signed_session",
            "model_is_authorization_boundary": False,
            "tenant_prefix_required": True,
            "raw_chain_of_thought_allowed": False,
        },
    }


class ComponentPublicationJournal:
    """Turn-local host for signed Adapter component publications.

    Signed identity stays inside the server journal.  Client events receive
    only the version, action and validated payload, so neither the model nor a
    cross-platform renderer becomes an authorization boundary.
    """

    __slots__ = ("_signed",)

    def __init__(self) -> None:
        self._signed: list[dict[str, Any]] = []

    def _handler(self, expected_action: str):
        def record(envelope: Mapping[str, Any]) -> dict[str, Any]:
            value = deepcopy(dict(envelope))
            if value.get("action") != expected_action:
                raise ValueError("Component handler received the wrong action")
            self._signed.append(value)
            return value

        return record

    def handlers(self) -> Mapping[str, Any]:
        return {
            action: self._handler(action)
            for action in known_component_actions()
        }

    def signed_snapshot(self) -> tuple[dict[str, Any], ...]:
        return tuple(deepcopy(self._signed))

    def drain_public(self, publication_key: str = "") -> list[dict[str, Any]]:
        clean_key = str(publication_key or "")
        if clean_key:
            values = [
                value for value in self._signed
                if value.get("publication_key") == clean_key
            ]
            self._signed = [
                value for value in self._signed
                if value.get("publication_key") != clean_key
            ]
        else:
            values = self._signed
            self._signed = []
        return [
            {
                "version": str(value.get("version") or COMPONENT_API_VERSION),
                "action": str(value.get("action") or ""),
                "payload": deepcopy(value.get("payload") or {}),
            }
            for value in values
            if value.get("action") in PUBLIC_COMPONENT_ACTIONS
        ]


def component_publication_payload(
    publications: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...],
) -> dict[str, Any]:
    """Return the forward-compatible client projection for component events."""
    return {
        "version": COMPONENT_API_VERSION,
        "publications": [deepcopy(dict(value)) for value in publications],
    }


def attach_component_publications(
    payload: Mapping[str, Any],
    publications: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...],
) -> dict[str, Any]:
    """Attach a public journal projection without mutating trusted output."""
    value = deepcopy(dict(payload))
    if publications:
        value["component_api"] = component_publication_payload(publications)
    return value
