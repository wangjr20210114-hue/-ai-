"""Pure, immutable Skill manifest models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class SkillToolBinding:
    name: str
    capability: str
    required: bool = True


@dataclass(frozen=True)
class SkillManifest:
    id: str
    version: str
    kind: str
    publisher: Mapping[str, Any]
    required_plan: str
    package_path: str
    order: int
    default_enabled: bool
    locked: bool
    capabilities: tuple[str, ...]
    plan_flags: tuple[str, ...]
    tools: tuple[SkillToolBinding, ...]
    action_kinds: tuple[str, ...]
    requires: tuple[str, ...]
    recommends: tuple[str, ...]
    degrade_when_capabilities: tuple[str, ...]
    unavailable_fallback: str
    permissions: frozenset[str]
    env_keys: tuple[str, ...]
    adapter: str
    preference_hook: str
    external: bool
    provider_env: tuple[str, ...]
    connect_url: str
    credential: Mapping[str, Any]
    icon: str
    names: Mapping[str, str]
    descriptions: Mapping[str, str]
    planner_summary: str
    prompt_topic: str
    prompt_instructions: str
    prompt_recovery_tools: tuple[str, ...]
    component_actions: tuple[str, ...]
    skill_instructions: str

    def public_dict(self, env: Mapping[str, Any] | None = None) -> dict[str, Any]:
        runtime_env = env or {}
        configured = (
            all(bool(str(runtime_env.get(key) or "").strip()) for key in self.provider_env)
            if self.provider_env
            else True
        )
        return {
            "id": self.id,
            "version": self.version,
            "kind": self.kind,
            "publisher": dict(self.publisher),
            "required_plan": self.required_plan,
            "package_path": self.package_path,
            "order": self.order,
            "default_enabled": self.default_enabled,
            "locked": self.locked,
            "capabilities": list(self.capabilities),
            "requires": list(self.requires),
            "recommends": list(self.recommends),
            "unavailable_fallback": self.unavailable_fallback,
            "external": self.external,
            "configured": configured,
            "connect_url": self.connect_url,
            "credential": dict(self.credential),
            "icon": self.icon,
            "name": dict(self.names),
            "description": dict(self.descriptions),
            "component_actions": list(self.component_actions),
        }
