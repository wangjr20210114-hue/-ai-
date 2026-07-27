MANIFEST = {
    "schema_version": 1,
    "id": "calendar",
    "order": 50,
    "default_enabled": True,
    "capabilities": ["calendar_context", "calendar_action"],
    "plan_flags": ["needs_calendar_context", "needs_calendar_action"],
    "tools": [{"name": "propose_calendar_changes", "capability": "calendar_action"}],
    "action_kinds": ["calendar_changes"],
    "recommends": ["maps"],
    "permissions": [
        "makers.state",
        "makers.checkpointer",
        "makers.trace",
        "conversation.read",
        "user.read",
    ],
    "ui": {
        "icon": "▦",
        "name": {"zh-CN": "日程管理", "zh-TW": "日程管理", "en": "Calendar management"},
        "description": {
            "zh-CN": "通过对话新增、修改或删除日程，并用确认卡检查冲突。",
            "zh-TW": "透過對話新增、修改或刪除日程，並用確認卡檢查衝突。",
            "en": "Add, edit, or delete calendar items with confirmation and conflict checks.",
        },
    },
    "planner": {
        "topic": "calendar",
        "summary": "Read schedules or prepare confirmed calendar create, update and delete proposals.",
    },
}
