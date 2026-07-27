MANIFEST = {
    "schema_version": 1,
    "id": "tencent-meeting",
    "order": 80,
    "default_enabled": True,
    "capabilities": ["meeting_action"],
    "plan_flags": ["needs_meeting_action"],
    "tools": [{"name": "propose_meeting", "capability": "meeting_action"}],
    "action_kinds": ["meeting_create"],
    "requires": ["calendar"],
    "permissions": [
        "makers.state",
        "makers.trace",
        "conversation.read",
        "user.read",
    ],
    "env_keys": ["TENCENT_MEETING_TOKEN", "TENCENT_MEETING_SKILL_VERSION"],
    "external": True,
    "provider_env": ["TENCENT_MEETING_TOKEN"],
    "connect_url": "https://meeting.tencent.com/ai-skill.html",
    "credential": {
        "kind": "token",
        "env_key": "TENCENT_MEETING_TOKEN",
        "ttl_seconds": 604800,
        "help_url": "https://meeting.tencent.com/support/topic/2233/index.html",
        "instructions": {
            "zh-CN": "打开腾讯会议 AI Skill 专区并登录个人账号，复制专属 Token 后粘贴到这里。Floris 只在服务端保存七天，之后需重新连接。",
            "zh-TW": "開啟騰訊會議 AI Skill 專區並登入個人帳號，複製專屬 Token 後貼到這裡。Floris 只在服務端保存七天，之後需重新連線。",
            "en": "Open Tencent Meeting AI Skill, sign in with a personal account, copy the personal token, and paste it here. Floris stores it server-side for seven days.",
        },
    },
    "ui": {
        "icon": "会",
        "name": {"zh-CN": "腾讯会议", "zh-TW": "騰訊會議", "en": "Tencent Meeting"},
        "description": {
            "zh-CN": "创建真实腾讯会议，并把会议号和链接写入日程。",
            "zh-TW": "建立真實騰訊會議，並把會議號和連結寫入日程。",
            "en": "Create real Tencent Meetings and write the number and link into the calendar.",
        },
    },
    "planner": {
        "topic": "meeting",
        "summary": "Prepare a Tencent Meeting proposal linked to a calendar item.",
        "instructions": (
            "【会议】创建腾讯会议用 needs_meeting_action；会议依赖日程 Skill。只创建普通"
            "日程而不需要会议链接时不要选择 meeting。"
        ),
        "recovery_tools": ["propose_meeting"],
    },
}
