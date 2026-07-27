MANIFEST = {
    "schema_version": 1,
    "id": "proactive-agent",
    "order": 60,
    "default_enabled": True,
    "capabilities": ["workflow_action"],
    "plan_flags": ["needs_workflow_action"],
    "tools": [{"name": "propose_workflow", "capability": "workflow_action"}],
    "preference_hook": "agents.skills.proactive_agent.lifecycle:on_preference_changed",
    "recommends": ["calendar", "maps"],
    "permissions": [
        "makers.state",
        "makers.trace",
        "conversation.read",
        "user.read",
    ],
    "ui": {
        "icon": "✦",
        "name": {"zh-CN": "主动式 Agent", "zh-TW": "主動式 Agent", "en": "Proactive Agent"},
        "description": {
            "zh-CN": "根据日程、天气、路线与工作流主动发现机会并提醒。",
            "zh-TW": "根據日程、天氣、路線與工作流主動發現機會並提醒。",
            "en": "Discover opportunities and remind based on schedules, routes, and workflows.",
        },
    },
    "planner": {
        "topic": "proactive",
        "summary": "Recurring, scheduled or multi-step workflows and proactive follow-up.",
        "instructions": (
            "【主动服务】跨时间、多步骤、持续推进或定时主动触达用 needs_workflow_action；"
            "单次提醒仍是 calendar_action。只有回答完成后确实可能产生有价值的主动下一步，"
            "才设 needs_opportunity_review。"
        ),
        "recovery_tools": ["propose_workflow"],
    },
}
