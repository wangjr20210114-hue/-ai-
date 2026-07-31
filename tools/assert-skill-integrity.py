"""Repository gate for trusted system Skill manifests and adapters."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agents._infrastructure.skills import build_system_skill_tools  # noqa: E402
from agents._shared.skill_registry import (  # noqa: E402
    SYSTEM_ADAPTER_PREFIX,
    locked_skill_ids,
    skill_manifests,
    tool_skill_map,
)


def fail(message: str) -> None:
    raise SystemExit(f"Skill integrity failed: {message}")


def main() -> None:
    manifests = skill_manifests()
    if any(manifest.kind != "system" for manifest in manifests):
        fail("installed executable registry contains a non-system Skill")
    for manifest in manifests:
        if not manifest.adapter.startswith(SYSTEM_ADAPTER_PREFIX):
            fail(f"{manifest.id} has no trusted adapter")
        module_name, separator, function_name = manifest.adapter.partition(":")
        if separator != ":" or function_name != "build_tools":
            fail(f"{manifest.id} adapter entry point is invalid")
        if not callable(getattr(importlib.import_module(module_name), function_name)):
            fail(f"{manifest.id} adapter is not callable")

    owners = tool_skill_map()
    tools = build_system_skill_tools(
        object(),
        user_id="skill-integrity",
        env={"TENCENT_MEETING_TOKEN": "integrity-only"},
    )
    names = [tool.name for tool in tools]
    if len(names) != len(set(names)):
        fail("adapter tools are not globally unique")
    if set(names) != set(owners):
        fail(
            "manifest/tool mismatch "
            f"missing={sorted(set(owners) - set(names))} "
            f"undeclared={sorted(set(names) - set(owners))}"
        )

    guest_tools = build_system_skill_tools(
        object(),
        user_id="skill-integrity-guest",
        identity={
            "tenant_id": "skill-integrity",
            "user_id": "skill-integrity-guest",
            "membership": "guest",
        },
        env={"TENCENT_MEETING_TOKEN": "integrity-only"},
    )
    if {owners[tool.name] for tool in guest_tools} != locked_skill_ids():
        fail("Guest tool set is not restricted to locked core Skills")

    removed_module = ROOT / "agents" / "chat" / ("_ui" + "_tools.py")
    if removed_module.exists():
        fail("legacy central chat tool module still exists")
    print(
        "Skill integrity passed: "
        f"{len(manifests)} system Skills, {len(names)} unique tools, "
        f"{len(guest_tools)} Guest tools"
    )


if __name__ == "__main__":
    main()
