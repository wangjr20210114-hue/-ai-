"""Declarative, discoverable Skill registry and restricted Makers runtime SDK.

A Skill is installed by adding ``agents/skills/<package>/manifest.py``.  The
manifest owns product metadata, semantic capabilities, tool names, dependencies
and requested Makers permissions.  An optional adapter entry point may return
additional LangChain tools without editing the central chat graph.

Existing FLORIS business functions remain in their current modules.  Their
manifests claim ownership of those tools, so migration does not rewrite or
weaken any provider, validation, clarification, confirmation or persistence
logic.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
import re
from dataclasses import dataclass
from functools import lru_cache
from types import MappingProxyType
from typing import Any, Iterable, Mapping


SKILL_MANIFEST_SCHEMA_VERSION = 1
_SKILL_ID = re.compile(r"^[a-z][a-z0-9-]{1,63}$")
_CAPABILITY_ID = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
_TOOL_ID = re.compile(r"^[a-z][a-z0-9_]{1,95}$")
_ACTION_ID = re.compile(r"^[a-z][a-z0-9_]{1,95}$")
_PERMISSIONS = {
    "makers.state",
    "makers.checkpointer",
    "makers.blob",
    "makers.model",
    "makers.trace",
    "conversation.read",
    "user.read",
    "browser.location",
}


def _runtime_root_package() -> str:
    """Return ``agents`` locally and EdgeOne's ``pages_agents`` after bundling."""
    return str(__package__ or "agents._shared").rsplit(".", 1)[0]


def _runtime_module_name(module_name: str) -> str:
    """Translate source entry points into the package name chosen by Makers."""
    clean_name = str(module_name or "").strip()
    if clean_name == "agents":
        return _runtime_root_package()
    if clean_name.startswith("agents."):
        return f"{_runtime_root_package()}{clean_name[len('agents'):]}"
    return clean_name


@dataclass(frozen=True)
class SkillToolBinding:
    name: str
    capability: str
    required: bool = True


@dataclass(frozen=True)
class SkillManifest:
    id: str
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

    def public_dict(self, env: Mapping[str, Any] | None = None) -> dict[str, Any]:
        runtime_env = env or {}
        configured = (
            all(bool(str(runtime_env.get(key) or "").strip()) for key in self.provider_env)
            if self.provider_env
            else True
        )
        return {
            "id": self.id,
            "order": self.order,
            "default_enabled": self.default_enabled,
            "locked": self.locked,
            "capabilities": list(self.capabilities),
            "requires": list(self.requires),
            "recommends": list(self.recommends),
            "external": self.external,
            "configured": configured,
            "connect_url": self.connect_url,
            "credential": dict(self.credential),
            "icon": self.icon,
            "name": dict(self.names),
            "description": dict(self.descriptions),
        }


class SkillRuntimeContext:
    """Least-privilege Makers handles exposed to one plug-in adapter."""

    __slots__ = (
        "skill_id",
        "permissions",
        "conversation_id",
        "user_id",
        "env",
        "_state_store",
        "_checkpointer",
        "_model",
        "_tracer",
        "_browser_location",
    )

    def __init__(self, manifest: SkillManifest, runtime: Mapping[str, Any]):
        self.skill_id = manifest.id
        self.permissions = manifest.permissions
        self.conversation_id = (
            str(runtime.get("conversation_id") or "")
            if "conversation.read" in self.permissions
            else ""
        )
        self.user_id = (
            str(runtime.get("user_id") or "")
            if "user.read" in self.permissions
            else ""
        )
        raw_env = runtime.get("env") if isinstance(runtime.get("env"), Mapping) else {}
        self.env = MappingProxyType({
            key: raw_env.get(key)
            for key in manifest.env_keys
            if key in raw_env
        })
        self._state_store = (
            runtime.get("state_store")
            if "makers.state" in self.permissions
            else None
        )
        self._checkpointer = (
            runtime.get("checkpointer")
            if "makers.checkpointer" in self.permissions
            else None
        )
        self._model = (
            runtime.get("model")
            if "makers.model" in self.permissions
            else None
        )
        self._tracer = (
            runtime.get("tracer")
            if "makers.trace" in self.permissions
            else None
        )
        self._browser_location = (
            dict(runtime.get("browser_location") or {})
            if "browser.location" in self.permissions
            else {}
        )

    @property
    def state_store(self):
        self.require("makers.state")
        return self._state_store

    @property
    def checkpointer(self):
        self.require("makers.checkpointer")
        return self._checkpointer

    @property
    def model(self):
        self.require("makers.model")
        return self._model

    @property
    def tracer(self):
        self.require("makers.trace")
        return self._tracer

    @property
    def browser_location(self) -> dict[str, Any]:
        self.require("browser.location")
        return dict(self._browser_location)

    def blob_store(self, name: str, *, consistency: str = "strong"):
        """Return an EdgeOne Makers Blob store only when explicitly declared."""
        self.require("makers.blob")
        from pages_blob import get_store

        clean_name = str(name or "").strip()
        if not clean_name:
            raise ValueError("Makers Blob store name is required")
        return get_store(clean_name, consistency=consistency)

    def trace(self, name: str, attributes: Mapping[str, Any] | None = None) -> None:
        self.require("makers.trace")
        event = getattr(self._tracer, "event", None)
        if callable(event):
            event(
                f"skill.{self.skill_id}.{str(name or 'event')[:80]}",
                dict(attributes or {}),
            )

    def require(self, permission: str) -> None:
        if permission not in self.permissions:
            raise PermissionError(
                f"Skill {self.skill_id} did not declare permission {permission}"
            )


def _string_tuple(value: Any) -> tuple[str, ...]:
    return tuple(dict.fromkeys(
        str(item or "").strip()
        for item in (value or [])
        if str(item or "").strip()
    ))


def _localized(value: Any, fallback: str) -> Mapping[str, str]:
    raw = value if isinstance(value, Mapping) else {}
    english = str(raw.get("en") or raw.get("zh-CN") or fallback).strip()
    simplified = str(raw.get("zh-CN") or english).strip()
    return MappingProxyType({
        "zh-CN": simplified,
        "zh-TW": str(raw.get("zh-TW") or simplified).strip(),
        "en": english,
    })


def _parse_manifest(raw: Mapping[str, Any], source: str) -> SkillManifest:
    if int(raw.get("schema_version") or 0) != SKILL_MANIFEST_SCHEMA_VERSION:
        raise ValueError(f"{source}: unsupported Skill manifest schema")
    skill_id = str(raw.get("id") or "").strip()
    if not _SKILL_ID.fullmatch(skill_id):
        raise ValueError(f"{source}: invalid Skill id {skill_id!r}")
    capabilities = _string_tuple(raw.get("capabilities"))
    if any(not _CAPABILITY_ID.fullmatch(item) for item in capabilities):
        raise ValueError(f"{source}: invalid capability id")
    plan_flags = _string_tuple(raw.get("plan_flags"))
    if any(not item.startswith("needs_") for item in plan_flags):
        raise ValueError(f"{source}: plan flags must start with needs_")
    tool_bindings: list[SkillToolBinding] = []
    for item in raw.get("tools") or []:
        if not isinstance(item, Mapping):
            raise ValueError(f"{source}: each tool must be an object")
        name = str(item.get("name") or "").strip()
        capability = str(item.get("capability") or "").strip()
        if not _TOOL_ID.fullmatch(name):
            raise ValueError(f"{source}: invalid tool name {name!r}")
        if capability not in capabilities:
            raise ValueError(
                f"{source}: tool {name} references undeclared capability {capability}"
            )
        tool_bindings.append(SkillToolBinding(
            name=name,
            capability=capability,
            required=bool(item.get("required", True)),
        ))
    action_kinds = _string_tuple(raw.get("action_kinds"))
    if any(not _ACTION_ID.fullmatch(item) for item in action_kinds):
        raise ValueError(f"{source}: invalid action kind")
    permissions = frozenset(_string_tuple(raw.get("permissions")))
    unknown_permissions = permissions - _PERMISSIONS
    if unknown_permissions:
        raise ValueError(
            f"{source}: unknown Makers permissions {sorted(unknown_permissions)}"
        )
    ui = raw.get("ui") if isinstance(raw.get("ui"), Mapping) else {}
    planner = (
        raw.get("planner")
        if isinstance(raw.get("planner"), Mapping)
        else {}
    )
    credential = (
        raw.get("credential")
        if isinstance(raw.get("credential"), Mapping)
        else {}
    )
    credential_kind = str(credential.get("kind") or "").strip()
    credential_env_key = str(credential.get("env_key") or "").strip()
    credential_ttl = int(credential.get("ttl_seconds") or 0)
    if credential_kind and credential_kind != "token":
        raise ValueError(f"{source}: unsupported credential kind")
    if credential_kind and (
        credential_env_key not in _string_tuple(raw.get("env_keys"))
        or credential_env_key not in _string_tuple(raw.get("provider_env"))
    ):
        raise ValueError(
            f"{source}: credential env_key must be declared in env_keys and provider_env"
        )
    if credential_kind and not 300 <= credential_ttl <= 31 * 24 * 60 * 60:
        raise ValueError(f"{source}: credential ttl_seconds is out of range")
    public_credential = {
        "kind": credential_kind,
        "env_key": credential_env_key,
        "ttl_seconds": credential_ttl,
        "help_url": str(credential.get("help_url") or "").strip(),
        "instructions": dict(_localized(credential.get("instructions"), "")),
    } if credential_kind else {}
    recovery_tools = _string_tuple(planner.get("recovery_tools"))
    if any(not _TOOL_ID.fullmatch(item) for item in recovery_tools):
        raise ValueError(f"{source}: invalid planner recovery tool")
    return SkillManifest(
        id=skill_id,
        order=max(-10_000, min(10_000, int(raw.get("order") or 0))),
        default_enabled=bool(raw.get("default_enabled", True)),
        locked=bool(raw.get("locked", False)),
        capabilities=capabilities,
        plan_flags=plan_flags,
        tools=tuple(tool_bindings),
        action_kinds=action_kinds,
        requires=_string_tuple(raw.get("requires")),
        recommends=_string_tuple(raw.get("recommends")),
        degrade_when_capabilities=_string_tuple(
            raw.get("degrade_when_capabilities")
        ),
        permissions=permissions,
        env_keys=_string_tuple(raw.get("env_keys")),
        adapter=str(raw.get("adapter") or "").strip(),
        preference_hook=str(raw.get("preference_hook") or "").strip(),
        external=bool(raw.get("external", False)),
        provider_env=_string_tuple(raw.get("provider_env")),
        connect_url=str(raw.get("connect_url") or "").strip(),
        credential=MappingProxyType(public_credential),
        icon=str(ui.get("icon") or "◇").strip()[:8],
        names=_localized(ui.get("name"), skill_id),
        descriptions=_localized(ui.get("description"), ""),
        planner_summary=str(planner.get("summary") or "").strip()[:600],
        prompt_topic=str(planner.get("topic") or "").strip()[:64],
        prompt_instructions=str(planner.get("instructions") or "").strip()[:4000],
        prompt_recovery_tools=recovery_tools,
    )


def _validate_registry(manifests: Iterable[SkillManifest]) -> tuple[SkillManifest, ...]:
    ordered = tuple(manifests)
    by_id: dict[str, SkillManifest] = {}
    capability_owner: dict[str, str] = {}
    tool_owner: dict[str, str] = {}
    action_owner: dict[str, str] = {}
    for manifest in ordered:
        if manifest.id in by_id:
            raise ValueError(f"duplicate Skill id: {manifest.id}")
        by_id[manifest.id] = manifest
        for capability in manifest.capabilities:
            previous = capability_owner.setdefault(capability, manifest.id)
            if previous != manifest.id:
                raise ValueError(
                    f"capability {capability} owned by both {previous} and {manifest.id}"
                )
        for binding in manifest.tools:
            previous = tool_owner.setdefault(binding.name, manifest.id)
            if previous != manifest.id:
                raise ValueError(
                    f"tool {binding.name} owned by both {previous} and {manifest.id}"
                )
        for action_kind in manifest.action_kinds:
            previous = action_owner.setdefault(action_kind, manifest.id)
            if previous != manifest.id:
                raise ValueError(
                    f"action {action_kind} owned by both {previous} and {manifest.id}"
                )
    for manifest in ordered:
        missing = (set(manifest.requires) | set(manifest.recommends)) - set(by_id)
        if missing:
            raise ValueError(
                f"Skill {manifest.id} references missing dependencies {sorted(missing)}"
            )
        missing_capabilities = (
            set(manifest.degrade_when_capabilities) - set(capability_owner)
        )
        if missing_capabilities:
            raise ValueError(
                f"Skill {manifest.id} references missing degradation "
                f"capabilities {sorted(missing_capabilities)}"
            )

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(skill_id: str) -> None:
        if skill_id in visiting:
            raise ValueError(f"cyclic required Skill dependency at {skill_id}")
        if skill_id in visited:
            return
        visiting.add(skill_id)
        for dependency in by_id[skill_id].requires:
            visit(dependency)
        visiting.remove(skill_id)
        visited.add(skill_id)

    for skill_id in by_id:
        visit(skill_id)
    return tuple(sorted(ordered, key=lambda item: (item.order, item.id)))


def parse_skill_manifests(
    values: Iterable[Mapping[str, Any]],
    *,
    source: str = "runtime",
) -> tuple[SkillManifest, ...]:
    """Public validator used by contract tests and custom registry tooling."""
    return _validate_registry(
        _parse_manifest(value, f"{source}[{index}]")
        for index, value in enumerate(values)
    )


@lru_cache(maxsize=1)
def skill_manifests() -> tuple[SkillManifest, ...]:
    package = importlib.import_module(f"{_runtime_root_package()}.skills")
    discovered: list[SkillManifest] = []
    prefix = f"{package.__name__}."
    for module_info in sorted(
        pkgutil.iter_modules(package.__path__, prefix),
        key=lambda item: item.name,
    ):
        if not module_info.ispkg:
            continue
        manifest_module_name = f"{module_info.name}.manifest"
        try:
            module = importlib.import_module(manifest_module_name)
        except ModuleNotFoundError as exc:
            if exc.name == manifest_module_name:
                continue
            raise
        raw = getattr(module, "MANIFEST", None)
        if not isinstance(raw, Mapping):
            raise ValueError(f"{manifest_module_name}: MANIFEST must be a mapping")
        discovered.append(_parse_manifest(raw, manifest_module_name))
    if not discovered:
        raise RuntimeError("No Skill manifests were discovered")
    return _validate_registry(discovered)


def skill_manifest(skill_id: str) -> SkillManifest | None:
    clean_id = str(skill_id or "").strip()
    return next(
        (manifest for manifest in skill_manifests() if manifest.id == clean_id),
        None,
    )


def known_skill_ids() -> frozenset[str]:
    return frozenset(manifest.id for manifest in skill_manifests())


def default_skill_preferences() -> dict[str, bool]:
    return {
        manifest.id: True if manifest.locked else manifest.default_enabled
        for manifest in skill_manifests()
    }


def locked_skill_ids() -> frozenset[str]:
    return frozenset(
        manifest.id for manifest in skill_manifests() if manifest.locked
    )


def resolve_enabled_skills(values: Iterable[str]) -> frozenset[str]:
    """Remove Skills whose required dependencies are not enabled."""
    active = {
        str(value or "").strip()
        for value in values
        if str(value or "").strip() in known_skill_ids()
    }
    manifests = {manifest.id: manifest for manifest in skill_manifests()}
    changed = True
    while changed:
        changed = False
        for skill_id in tuple(active):
            if any(dependency not in active for dependency in manifests[skill_id].requires):
                active.discard(skill_id)
                changed = True
    return frozenset(active)


def enabled_skills_from_preferences(
    preferences: Mapping[str, Any] | None,
) -> frozenset[str]:
    supplied = preferences or {}
    enabled = {
        manifest.id
        for manifest in skill_manifests()
        if manifest.locked
        or bool(supplied.get(manifest.id, manifest.default_enabled))
    }
    return resolve_enabled_skills(enabled)


def capability_is_enabled(
    capability: str,
    preferences: Mapping[str, Any] | None,
) -> bool:
    owner = capability_skill_map().get(str(capability or "").strip())
    return bool(owner and owner in enabled_skills_from_preferences(preferences))


def capability_skill_map() -> dict[str, str]:
    return {
        capability: manifest.id
        for manifest in skill_manifests()
        for capability in manifest.capabilities
    }


def skill_plan_flags() -> dict[str, tuple[str, ...]]:
    return {
        manifest.id: manifest.plan_flags
        for manifest in skill_manifests()
        if manifest.plan_flags
    }


def skill_degradation_capabilities() -> dict[str, tuple[str, ...]]:
    return {
        manifest.id: manifest.degrade_when_capabilities
        for manifest in skill_manifests()
        if manifest.degrade_when_capabilities
    }


def tool_skill_map() -> dict[str, str]:
    return {
        binding.name: manifest.id
        for manifest in skill_manifests()
        for binding in manifest.tools
    }


def action_skill_map() -> dict[str, str]:
    return {
        action_kind: manifest.id
        for manifest in skill_manifests()
        for action_kind in manifest.action_kinds
    }


def unavailable_skills_for_action(
    action_kind: str,
    preferences: Mapping[str, Any],
) -> tuple[str, ...]:
    """Return disabled owner/dependencies for an Action kind."""
    owner = action_skill_map().get(str(action_kind or "").strip())
    if not owner:
        return ()
    effective = enabled_skills_from_preferences(preferences)
    manifest = skill_manifest(owner)
    required = [owner, *(manifest.requires if manifest else ())]
    return tuple(skill_id for skill_id in required if skill_id not in effective)


def capability_tools_map() -> dict[str, tuple[str, ...]]:
    result: dict[str, list[str]] = {}
    for manifest in skill_manifests():
        for binding in manifest.tools:
            if binding.required:
                result.setdefault(binding.capability, []).append(binding.name)
    return {
        capability: tuple(dict.fromkeys(names))
        for capability, names in result.items()
    }


def public_skill_catalog(env: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    return [manifest.public_dict(env) for manifest in skill_manifests()]


def skill_is_configured(
    skill_id: str,
    env: Mapping[str, Any] | None = None,
) -> bool:
    manifest = skill_manifest(skill_id)
    if manifest is None:
        return False
    runtime_env = env or {}
    return all(
        bool(str(runtime_env.get(key) or "").strip())
        for key in manifest.provider_env
    )


def planner_skill_index() -> str:
    lines = []
    for manifest in skill_manifests():
        if not manifest.capabilities or not manifest.planner_summary:
            continue
        lines.append(
            f"- {manifest.id}: {manifest.planner_summary} "
            f"[capabilities: {', '.join(manifest.capabilities)}]"
        )
    return "\n".join(lines)


def planner_topic_summaries() -> dict[str, str]:
    """Return manifest-owned semantic retrieval topics."""
    summaries: dict[str, list[str]] = {}
    for manifest in skill_manifests():
        if manifest.prompt_topic and manifest.planner_summary:
            summaries.setdefault(manifest.prompt_topic, []).append(
                manifest.planner_summary
            )
    return {
        topic: " ".join(dict.fromkeys(values))
        for topic, values in summaries.items()
    }


def planner_topic_instructions() -> dict[str, str]:
    """Return optional plug-in prompt fragments keyed by semantic topic."""
    details: dict[str, list[str]] = {}
    for manifest in skill_manifests():
        if manifest.prompt_topic and manifest.prompt_instructions:
            details.setdefault(manifest.prompt_topic, []).append(
                manifest.prompt_instructions
            )
    return {
        topic: "\n".join(dict.fromkeys(values))
        for topic, values in details.items()
    }


def planner_topic_tools() -> dict[str, tuple[str, ...]]:
    """Return the bounded recovery tool surface for each manifest topic."""
    result: dict[str, list[str]] = {}
    for manifest in skill_manifests():
        if not manifest.prompt_topic:
            continue
        recovery_tools = manifest.prompt_recovery_tools or tuple(
            binding.name for binding in manifest.tools if binding.required
        )
        result.setdefault(manifest.prompt_topic, []).extend(recovery_tools)
    return {
        topic: tuple(dict.fromkeys(names))
        for topic, names in result.items()
    }


def build_adapter_tools(
    runtime: Mapping[str, Any],
    enabled_skills: Iterable[str],
) -> list[Any]:
    """Discover and build tools supplied by plug-in adapters.

    Adapters are ordinary repository-owned Python callables declared as
    ``package.module:function``. They receive only SkillRuntimeContext handles
    allowed by their manifest and must return tools whose names the manifest
    owns.
    """
    enabled = set(enabled_skills)
    built: list[Any] = []
    for manifest in skill_manifests():
        if not manifest.adapter or manifest.id not in enabled:
            continue
        if any(dependency not in enabled for dependency in manifest.requires):
            continue
        if not all(
            bool(str((runtime.get("env") or {}).get(key) or "").strip())
            for key in manifest.provider_env
        ):
            continue
        module_name, separator, attribute = manifest.adapter.partition(":")
        if not separator or not module_name or not attribute:
            raise ValueError(
                f"Skill {manifest.id} adapter must be package.module:function"
            )
        builder = getattr(
            importlib.import_module(_runtime_module_name(module_name)),
            attribute,
        )
        if not callable(builder):
            raise TypeError(f"Skill {manifest.id} adapter is not callable")
        context = SkillRuntimeContext(manifest, runtime)
        result = builder(context)
        if inspect.isawaitable(result):
            raise TypeError(f"Skill {manifest.id} adapter builder must be synchronous")
        tools = list(result or [])
        declared = {binding.name for binding in manifest.tools}
        returned = {str(getattr(tool, "name", "") or "") for tool in tools}
        if not returned.issubset(declared):
            raise ValueError(
                f"Skill {manifest.id} adapter returned undeclared tools "
                f"{sorted(returned - declared)}"
            )
        built.extend(tools)
    return built


async def run_preference_hooks(
    runtime: Mapping[str, Any],
    previous: Mapping[str, Any],
    current: Mapping[str, Any],
) -> None:
    """Notify only Skills whose effective user preference changed."""
    for manifest in skill_manifests():
        if not manifest.preference_hook:
            continue
        before = bool(previous.get(manifest.id, manifest.default_enabled))
        after = bool(current.get(manifest.id, manifest.default_enabled))
        if before == after:
            continue
        module_name, separator, attribute = manifest.preference_hook.partition(":")
        if not separator or not module_name or not attribute:
            raise ValueError(
                f"Skill {manifest.id} preference_hook must be package.module:function"
            )
        hook = getattr(
            importlib.import_module(_runtime_module_name(module_name)),
            attribute,
        )
        if not callable(hook):
            raise TypeError(f"Skill {manifest.id} preference hook is not callable")
        result = hook(SkillRuntimeContext(manifest, runtime), after)
        if inspect.isawaitable(result):
            await result
