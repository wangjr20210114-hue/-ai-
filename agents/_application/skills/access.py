"""One runtime Skill-access decision shared by every feature Controller."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

from .registry import (
    capability_skill_map,
    enabled_skills_from_preferences,
    known_skill_ids,
    skill_required_plans,
)
from ..._domain.entitlements.policy import (
    allowed_skill_ids,
    effective_skill_preferences,
    skill_unavailability_reasons,
)


@dataclass(frozen=True)
class SkillAccess:
    """Resolved switches, dependencies and identity entitlements."""

    enabled_skills: frozenset[str]
    disabled_skills: frozenset[str]
    enabled_capabilities: frozenset[str]
    downgrade_reasons: Mapping[str, str]

    def allows_capability(self, capability: str) -> bool:
        return str(capability or "").strip() in self.enabled_capabilities

    def reason_for_capability(self, capability: str) -> str:
        skill_id = capability_skill_map().get(str(capability or "").strip())
        if not skill_id or skill_id in self.enabled_skills:
            return ""
        return str(self.downgrade_reasons.get(skill_id) or "degraded")

    def preference_map(self) -> dict[str, bool]:
        """Return an explicit map; missing keys may never regain defaults."""
        return {
            skill_id: skill_id in self.enabled_skills
            for skill_id in sorted(self.enabled_skills | self.disabled_skills)
        }


def resolve_skill_access(
    identity: Mapping[str, Any],
    preferences: Mapping[str, Any] | None,
) -> SkillAccess:
    """Resolve manifest defaults, dependencies and shared entitlement rules."""
    effective = effective_skill_preferences(identity, preferences)
    configured = enabled_skills_from_preferences(effective)
    enabled = allowed_skill_ids(
        identity,
        configured,
        required_plans=skill_required_plans(),
    )
    known = known_skill_ids()
    disabled = known - enabled
    capability_owners = capability_skill_map()
    return SkillAccess(
        enabled_skills=enabled,
        disabled_skills=disabled,
        enabled_capabilities=frozenset(
            capability
            for capability, skill_id in capability_owners.items()
            if skill_id in enabled
        ),
        downgrade_reasons=MappingProxyType(
            skill_unavailability_reasons(
                identity,
                disabled,
                enabled,
            ),
        ),
    )


__all__ = ["SkillAccess", "resolve_skill_access"]
