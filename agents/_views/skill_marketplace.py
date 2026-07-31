"""JSON View for the Skill marketplace controller."""

from __future__ import annotations

from typing import Any, Mapping

from .._infrastructure.http import response


def marketplace_view(
    *,
    skills: list[dict[str, Any]],
    preferences: Mapping[str, bool],
    entitlements: Mapping[str, Any],
    dependency_graph: Mapping[str, Any],
    component_api: Mapping[str, Any],
    connections: Mapping[str, Any],
    identity: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "skills": skills,
        "preferences": dict(preferences),
        "entitlements": dict(entitlements),
        "dependency_graph": dict(dependency_graph),
        "component_api": dict(component_api),
        "connections": dict(connections),
        "identity": dict(identity),
    }


def skill_package_view(package: Mapping[str, Any]) -> dict[str, Any]:
    return {"package": dict(package)}


def skill_error_view(
    message: str,
    *,
    code: str,
    status: int,
) -> dict[str, Any]:
    """Return a stable error envelope understood by Makers Agent routes."""
    return response(
        {"error": message, "code": code},
        status,
    )
