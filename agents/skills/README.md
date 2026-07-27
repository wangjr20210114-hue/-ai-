# FLORIS Skill plug-in contract

An installed Skill is one package under `agents/skills/`. The runtime discovers
its `manifest.py` at process start, validates the complete registry, exposes it
in the Skills marketplace, applies its dependencies before graph construction,
and registers its optional LangChain tools. Adding a Skill does not require
editing the central chat graph or a keyword router.

`agents/skills/index.py` is also a read-only catalog endpoint. Its main purpose
is to make EdgeOne Makers include the whole Skill tree when it converts the
source package from `agents` to `pages_agents`; the registry resolves either
runtime package name automatically.

Existing FLORIS Skills use manifests to claim their current business tools.
Provider calls, validation, confirmation Actions, persistence, and UI payloads
remain in their existing modules. The manifest is an integration boundary, not
a replacement for that business logic.

## Minimal Skill

Create `agents/skills/weather_alerts/__init__.py` and
`agents/skills/weather_alerts/manifest.py`:

```python
MANIFEST = {
    "schema_version": 1,
    "id": "weather-alerts",
    "order": 90,
    "default_enabled": True,
    "capabilities": ["weather_alert"],
    "tools": [
        {"name": "prepare_weather_alert", "capability": "weather_alert"},
    ],
    "action_kinds": ["weather_alert_create"],
    "adapter": "agents.skills.weather_alerts.adapter:build_tools",
    "preference_hook": (
        "agents.skills.weather_alerts.lifecycle:on_preference_changed"
    ),
    "permissions": [
        "makers.model",
        "makers.state",
        "makers.trace",
        "conversation.read",
        "user.read",
    ],
    "env_keys": ["WEATHER_API_KEY"],
    "provider_env": ["WEATHER_API_KEY"],
    "ui": {
        "icon": "☂",
        "name": {
            "zh-CN": "天气提醒",
            "zh-TW": "天氣提醒",
            "en": "Weather alerts",
        },
        "description": {
            "zh-CN": "查询天气并准备提醒。",
            "zh-TW": "查詢天氣並準備提醒。",
            "en": "Check weather and prepare an alert.",
        },
    },
    "planner": {
        "topic": "weather",
        "summary": "Current weather and weather-triggered alerts.",
        "instructions": (
            "Use weather_alert only when current weather or a weather-triggered "
            "alert is required. Never invent provider observations."
        ),
    },
}
```

Then implement a synchronous builder in `adapter.py`. The tools themselves may
be asynchronous:

```python
from langchain_core.tools import StructuredTool


def build_tools(context):
    async def prepare_weather_alert(city: str) -> str:
        # This reuses the Makers-backed model already selected by FLORIS.
        response = await context.model.ainvoke(
            [{"role": "user", "content": f"Normalize this city name: {city}"}]
        )
        context.trace("normalized_city", {"city": city})
        # context.state_store is also available because makers.state was declared.
        return str(response.content)

    return [
        StructuredTool.from_function(
            coroutine=prepare_weather_alert,
            name="prepare_weather_alert",
            description="Resolve a city, query verified weather, and prepare an alert.",
        )
    ]
```

After redeployment the Skill is present in the marketplace and can be selected
semantically by capability ID. No central `if skill_id == ...` registration is
required.

## Makers capabilities

Adapters receive `SkillRuntimeContext`, not the raw application context. Access
is denied unless the matching permission is declared:

- `makers.model`: the current Makers/LangChain model, usable through `ainvoke`,
  structured output, or tool calling.
- `makers.state`: the Makers LangGraph Store handle.
- `makers.checkpointer`: the Makers LangGraph checkpointer.
- `makers.blob`: `context.blob_store(name)` backed by EdgeOne Pages Blob.
- `makers.trace`: `context.trace(...)` and the trace handle.
- `conversation.read`, `user.read`: scoped identifiers.
- `browser.location`: the request-scoped fresh browser fix only.

`env_keys` also acts as an allow-list: an adapter cannot read undeclared
environment values through the runtime context. `provider_env` marks a Skill as
not configured until all listed keys are available. `requires` is a hard
dependency; `recommends` is only a marketplace hint.

`action_kinds` declares reviewable workspace Actions owned by the Skill. The
confirmation endpoint checks the owner and all hard dependencies from the
registry before committing. The Action's provider execution and validation
remain explicit business code; merely naming an Action does not grant a plug-in
an unrestricted commit path.

`preference_hook` is optional. It receives the same restricted runtime context
and the new enabled state when that Skill's stored preference changes. This is
the extension point for synchronizing Skill-owned Makers state; it avoids
adding Skill IDs to the settings endpoint.

Repository code remains trusted deployment code, so permissions are a runtime
contract and accidental-access guard, not an operating-system sandbox. A Skill
that performs a real side effect must still return a reviewable Action and use
the existing confirmation/commit boundary; it must not commit from an ordinary
planning tool.
