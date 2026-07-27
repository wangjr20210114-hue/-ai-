MANIFEST = {
    "schema_version": 1,
    "id": "web-search",
    "order": 10,
    "default_enabled": True,
    "capabilities": ["web_search"],
    "plan_flags": ["needs_web_search"],
    "tools": [
        {"name": "rich_search", "capability": "web_search"},
        {"name": "collect_page_images", "capability": "web_search", "required": False},
    ],
    "permissions": ["makers.state", "makers.trace", "conversation.read", "user.read"],
    "ui": {
        "icon": "◎",
        "name": {"zh-CN": "实时搜索", "zh-TW": "即時搜尋", "en": "Live search"},
        "description": {
            "zh-CN": "检索时效信息、核验来源并提供真实图片素材。",
            "zh-TW": "檢索即時資訊、核驗來源並提供真實圖片素材。",
            "en": "Find timely information, verify sources, and provide real image material.",
        },
    },
    "planner": {
        "topic": "web",
        "summary": "Current external facts, verification, sources, news, prices and public web media.",
        "instructions": (
            "【联网搜索】时效事实、用户要求查证或来源时 needs_web_search=true；"
            "search_query 合并为一次简洁事实查询。只有明确要求今天发布的内容才设 "
            "strict_today_only=true。图片确实帮助理解时再设 needs_images 并填写 image_query。"
        ),
        "recovery_tools": ["rich_search"],
    },
}
