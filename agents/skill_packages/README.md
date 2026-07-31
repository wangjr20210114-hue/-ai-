# FLORIS standard Skill contract

The HTTP route lives at `agents/skill_marketplace/` and is exposed as
`/skill_marketplace`. EdgeOne reserves `agents/skills/` during Agent route
discovery, so no product route or package is placed there. Installable packages
are stored under `agents/skill_packages/<skill-id>/` and always contain:

- `SKILL.md`: open Agent Skills instructions with `name` and `description`
  frontmatter.
- `floris.json`: version, publisher, dependencies, plan requirement,
  least-privilege permissions, component actions, and optional trusted adapter.

The runtime registry reads only these two files. The retired Python
`manifest.py` format is not a second source of truth.

## Minimal package

```text
agents/skill_packages/weather-alerts/
├── SKILL.md
└── floris.json
```

`SKILL.md`:

```markdown
---
name: weather-alerts
description: Check verified weather evidence and prepare reviewable alerts.
---

# Weather alerts

Use verified provider observations. Never invent current weather.
```

`floris.json`:

```json
{
  "schema_version": 2,
  "id": "weather-alerts",
  "version": "1.0.0",
  "kind": "community",
  "publisher": {
    "id": "publisher-id",
    "name": "Publisher",
    "verified": false
  },
  "required_plan": "free",
  "order": 90,
  "default_enabled": false,
  "locked": false,
  "capabilities": ["weather_alert"],
  "tools": [
    {
      "name": "prepare_weather_alert",
      "capability": "weather_alert"
    }
  ],
  "permissions": [
    "makers.model",
    "makers.state",
    "makers.trace",
    "conversation.read",
    "user.read",
    "components.chat"
  ],
  "component_actions": ["chat.progress.publish"],
  "env_keys": ["WEATHER_API_KEY"],
  "provider_env": ["WEATHER_API_KEY"],
  "adapter": "agents._skill_adapters.weather_alerts:build_tools",
  "ui": {
    "icon": "☂",
    "name": {
      "zh-CN": "天气提醒",
      "zh-TW": "天氣提醒",
      "en": "Weather alerts"
    },
    "description": {
      "zh-CN": "查询天气并准备可审核提醒。",
      "zh-TW": "查詢天氣並準備可審核提醒。",
      "en": "Check weather and prepare a reviewable alert."
    }
  },
  "planner": {
    "topic": "weather",
    "summary": "Current weather and weather-triggered alerts."
  }
}
```

Trusted Python adapters live in `agents/_skill_adapters/`. The leading
underscore prevents EdgeOne from publishing adapter modules as HTTP routes. They receive
`SkillRuntimeContext`, not the raw request context. Undeclared Makers handles,
environment keys, and component actions are denied.

An uploaded user ZIP is stored in the authenticated Makers Blob namespace with
`pending_review` status. Upload never means install or execute. The review
backend is intentionally left unavailable until the future administration
surface is implemented.

Run the standard package validator before release:

```bash
find agents/skill_packages -mindepth 1 -maxdepth 1 -type d -print0 |
  while IFS= read -r -d '' package; do
    python /path/to/skill-creator/scripts/quick_validate.py "$package"
  done
```
