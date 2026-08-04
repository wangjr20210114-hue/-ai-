"""Least-privilege execution runtime for trusted Skill adapters."""

from __future__ import annotations

import importlib
import inspect
from types import MappingProxyType
from typing import Any, Iterable, Mapping

from ..._domain.skills.manifest import SkillManifest
from . import registry as skill_registry
from .component_api import (
    component_envelope,
    component_permission,
    known_component_actions,
)
from .runtime_ports import SERVICE_PERMISSIONS, SkillServices


def _runtime_root_package() -> str:
    """Return ``agents`` locally and EdgeOne's ``pages_agents`` after bundling."""
    package = str(__package__ or "agents._application.skills")
    for marker in (
        "._application",
        "._infrastructure",
        "._domain",
        "._presenters",
        "._controllers",
    ):
        if marker in package:
            return package.split(marker, 1)[0]
    return package.split(".", 1)[0]

def _runtime_module_name(module_name: str) -> str:
    """Translate source entry points into the package name chosen by Makers."""
    clean_name = str(module_name or "").strip()
    if clean_name == "agents":
        return _runtime_root_package()
    if clean_name.startswith("agents."):
        return f"{_runtime_root_package()}{clean_name[len('agents'):]}"
    return clean_name

class SkillRuntimeContext:
    """Least-privilege Makers handles exposed to one plug-in adapter."""

    __slots__ = (
        "skill_id",
        "permissions",
        "conversation_id",
        "request_id",
        "tenant_id",
        "user_id",
        "response_language",
        "env",
        "_state_store",
        "_checkpointer",
        "_model",
        "_tracer",
        "_browser_location",
        "_components",
        "_component_actions",
        "_tool_component_actions",
        "_services",
    )

    def __init__(self, manifest: SkillManifest, runtime: Mapping[str, Any]):
        self.skill_id = manifest.id
        self.permissions = manifest.permissions
        self.conversation_id = (
            str(runtime.get("conversation_id") or "")
            if "conversation.read" in self.permissions
            else ""
        )
        raw_identity = (
            runtime.get("identity")
            if isinstance(runtime.get("identity"), Mapping)
            else {}
        )
        self.request_id = str(
            runtime.get("request_id")
            or raw_identity.get("request_id")
            or self.conversation_id
            or ""
        )
        self.tenant_id = (
            str(
                raw_identity.get("tenant_id")
                or runtime.get("tenant_id")
                or ""
            )
            if "user.read" in self.permissions
            else ""
        )
        self.user_id = (
            str(
                raw_identity.get("subject_id")
                or raw_identity.get("user_id")
                or runtime.get("user_id")
                or ""
            )
            if "user.read" in self.permissions
            else ""
        )
        self.response_language = str(
            runtime.get("response_language") or "zh-CN"
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
        self._components = (
            runtime.get("components")
            if isinstance(runtime.get("components"), Mapping)
            else {}
        )
        self._component_actions = frozenset(manifest.component_actions)
        self._tool_component_actions = MappingProxyType({
            binding.name: tuple(binding.publishes)
            for binding in manifest.tools
        })
        services = runtime.get("services")
        self._services = (
            services
            if isinstance(services, (Mapping, SkillServices))
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

    def component(self, action: str, *, publication_key: str = ""):
        """Return one host-provided typed component action after permission checks."""
        clean_action = str(action or "").strip()
        if clean_action not in known_component_actions():
            raise ValueError(f"Unknown Floris component action {clean_action!r}")
        if clean_action not in self._component_actions:
            raise PermissionError(
                f"Skill {self.skill_id} did not declare component action "
                f"{clean_action}"
            )
        permission = component_permission(clean_action)
        if permission not in self.permissions:
            raise PermissionError(
                f"Skill {self.skill_id} did not declare component permission {permission}"
            )
        handler = self._components.get(clean_action)
        if not callable(handler):
            raise RuntimeError(f"Component action {clean_action} is unavailable")
        def dispatch(payload: Mapping[str, Any]):
            envelope = component_envelope(
                clean_action,
                payload,
                request_id=self.request_id,
                tenant_id=self.tenant_id,
                user_id=self.user_id,
                publication_key=publication_key,
            )
            return handler(envelope)

        return dispatch

    def component_actions_for_tool(self, name: str) -> tuple[str, ...]:
        """Return the manifest-owned publications for one Adapter tool."""
        clean_name = str(name or "").strip()
        if clean_name not in self._tool_component_actions:
            raise PermissionError(
                f"Skill {self.skill_id} does not own tool {clean_name}"
            )
        return self._tool_component_actions[clean_name]

    def service(self, name: str):
        """Return only a declared, controller-supplied application service."""
        clean_name = str(name or "").strip()
        permission = SERVICE_PERMISSIONS.get(clean_name)
        if permission is None:
            raise ValueError(f"Unknown Skill service {clean_name!r}")
        if permission not in self.permissions:
            raise PermissionError(
                f"Skill {self.skill_id} did not declare service permission "
                f"{permission}"
            )
        value = (
            self._services.get(clean_name)
            if isinstance(self._services, Mapping)
            else self._services.get(clean_name)
        )
        if value is None:
            raise RuntimeError(f"Skill service {clean_name} is unavailable")
        return value

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
    enabled = set(skill_registry.resolve_enabled_skills(enabled_skills))
    raw_identity = (
        runtime.get("identity")
        if isinstance(runtime.get("identity"), Mapping)
        else {}
    )
    membership = str(
        raw_identity.get("membership")
        or runtime.get("membership")
        or "free"
    ).strip().lower()
    plan_rank = {"guest": 0, "free": 1, "plus": 2, "pro": 3}
    current_rank = plan_rank.get(membership, 1)
    built: list[Any] = []
    built_names: set[str] = set()
    for manifest in skill_registry.skill_manifests():
        if not manifest.adapter or manifest.id not in enabled:
            continue
        if any(dependency not in enabled for dependency in manifest.requires):
            continue
        if current_rank < plan_rank[manifest.required_plan]:
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
        if len(returned) != len(tools) or "" in returned:
            raise ValueError(
                f"Skill {manifest.id} adapter returned duplicate or unnamed tools"
            )
        if not returned.issubset(declared):
            raise ValueError(
                f"Skill {manifest.id} adapter returned undeclared tools "
                f"{sorted(returned - declared)}"
            )
        required = {
            binding.name
            for binding in manifest.tools
            if binding.required
        }
        missing_required = required - returned
        if missing_required:
            raise ValueError(
                f"Skill {manifest.id} adapter did not return required tools "
                f"{sorted(missing_required)}"
            )
        duplicate_global = built_names.intersection(returned)
        if duplicate_global:
            raise ValueError(
                "Skill adapter tool names must be globally unique: "
                f"{sorted(duplicate_global)}"
            )
        built_names.update(returned)
        built.extend(tools)
    return built

async def run_preference_hooks(
    runtime: Mapping[str, Any],
    previous: Mapping[str, Any],
    current: Mapping[str, Any],
) -> None:
    """Notify only Skills whose effective user preference changed."""
    for manifest in skill_registry.skill_manifests():
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
