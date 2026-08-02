"""Versioned component contracts available to reviewed Skill adapters."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping


COMPONENT_API_VERSION = "2026-08-02"

# Trusted adapters can use every action below, but the marketplace documentation
# is deliberately smaller: it only describes components that a Skill author can
# render for a user. Session recovery, storage and orchestration remain platform
# capabilities instead of becoming a second public infrastructure API.
PUBLIC_COMPONENT_ACTIONS = frozenset({
    "search.evidence.publish",
    "search.media.publish",
    "maps.place.select",
    "calendar.change.propose",
    "image.result.publish",
})

_COMPONENT_ACTIONS: dict[str, dict[str, Any]] = {
    "chat.progress.publish": {
        "category": "chat",
        "name": {"zh-CN": "更新处理进度", "en": "Publish progress"},
        "permission": "components.chat",
        "description": "Publish a trusted structured progress stage; raw model reasoning is forbidden.",
        "description_i18n": {"zh-CN": "向当前回答发布结构化处理进度，不接收或展示模型的原始推理。", "en": "Publish a structured progress stage without exposing model reasoning."},
        "input": {
            "stage": "planning|retrieval|verification|synthesis|finalizing|complete",
            "activity": "registered-activity-enum",
            "status": "active|completed|skipped",
        },
        "required": ["stage", "status"],
    },
    "search.evidence.publish": {
        "category": "search",
        "name": {"zh-CN": "发布搜索证据", "en": "Publish search evidence"},
        "permission": "components.search",
        "description": "Attach verified evidence and source citations to the current answer.",
        "description_i18n": {"zh-CN": "把已核验的来源与引用附加到当前回答。", "en": "Attach verified evidence and source citations to the current answer."},
        "input": {"source_id": "string", "title": "string", "url": "https-url"},
        "required": ["source_id", "title", "url"],
    },
    "search.media.publish": {
        "category": "search",
        "name": {"zh-CN": "发布来源媒体", "en": "Publish source media"},
        "permission": "components.search",
        "description": "Attach reviewed media to an exact source_id; free-form model placement is not allowed.",
        "description_i18n": {"zh-CN": "将审核后的图片绑定到确定的 source_id，避免来源错配。", "en": "Bind reviewed media to an exact source_id."},
        "input": {"source_id": "string", "media": "reviewed-media[]"},
        "required": ["source_id", "media"],
    },
    "workspace.action.propose": {
        "category": "workspace",
        "name": {"zh-CN": "提交工作区操作", "en": "Propose workspace action"},
        "permission": "components.workspace",
        "description": "Create a typed, user-visible proposal that still requires the platform confirmation policy.",
        "description_i18n": {"zh-CN": "创建用户可见的结构化操作提案，执行前仍遵循确认策略。", "en": "Create a typed proposal that remains subject to confirmation policy."},
        "input": {"kind": "registered-action-kind", "payload": "object"},
        "required": ["kind", "payload"],
    },
    "workspace.state.read": {
        "category": "workspace",
        "name": {"zh-CN": "读取工作区状态", "en": "Read workspace state"},
        "permission": "components.workspace",
        "description": "Read the authenticated user's scoped workspace projection.",
        "description_i18n": {"zh-CN": "读取当前登录用户有权访问的工作区状态。", "en": "Read the authenticated user's scoped workspace state."},
        "input": {"fields": "string[]"},
        "required": ["fields"],
    },
    "files.scoped.read": {
        "category": "files",
        "name": {"zh-CN": "读取用户文件", "en": "Read scoped file"},
        "permission": "components.files",
        "description": "Read a file only through the authenticated tenant/user Blob prefix.",
        "description_i18n": {"zh-CN": "按当前身份与租户边界读取指定文件。", "en": "Read a file within the authenticated user and tenant scope."},
        "input": {"storage_key": "tenant-scoped-key"},
        "required": ["storage_key"],
    },
    "files.scoped.upload": {
        "category": "files",
        "name": {"zh-CN": "创建文件上传", "en": "Create scoped upload"},
        "permission": "components.files",
        "description": "Request a tenant-scoped Makers Blob upload URL.",
        "description_i18n": {"zh-CN": "为当前用户创建受范围限制的文件上传地址。", "en": "Create a tenant-scoped upload URL for the current user."},
        "input": {"name": "string", "content_type": "string", "size": "integer"},
        "required": ["name", "content_type", "size"],
    },
    "maps.place.select": {
        "category": "maps",
        "name": {"zh-CN": "展示地点与路线", "en": "Show places and routes"},
        "permission": "components.maps",
        "description": "Render provider-verified places or a verified route in the map component.",
        "description_i18n": {"zh-CN": "在地图组件中展示服务商已核验的地点或路线。", "en": "Render provider-verified places or routes in the map component."},
        "input": {"places": "verified-place[]", "route": "verified-route?"},
        "required": ["places"],
    },
    "calendar.change.propose": {
        "category": "calendar",
        "name": {"zh-CN": "提交日程变更", "en": "Propose calendar changes"},
        "permission": "components.calendar",
        "description": "Render a versioned calendar change proposal without applying it automatically.",
        "description_i18n": {"zh-CN": "展示带版本的日程变更提案，不会自动写入。", "en": "Render a versioned calendar proposal without applying it automatically."},
        "input": {"changes": "calendar-change[]", "warnings": "string[]"},
        "required": ["changes"],
    },
    "image.result.publish": {
        "category": "image",
        "name": {"zh-CN": "发布生成图片", "en": "Publish generated image"},
        "permission": "components.image",
        "description": "Publish a generated image already persisted under the user's Makers Blob prefix.",
        "description_i18n": {"zh-CN": "发布已经安全保存到当前用户空间的生成图片。", "en": "Publish a generated image already saved in the current user's scope."},
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
            if action in PUBLIC_COMPONENT_ACTIONS
        ],
        "security": {
            "identity_source": "signed_session",
            "model_is_authorization_boundary": False,
            "tenant_prefix_required": True,
            "raw_chain_of_thought_allowed": False,
        },
    }
