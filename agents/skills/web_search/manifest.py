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
            "strict_today_only=true。以用户的理解收益判断配图：当真实图片能更快展示报道主体、"
            "事件现场、人物、产品或地点时，即使用户没有主动要求图片，也设 needs_images=true "
            "并填写具体 image_query；纯抽象推理、简单计算或图片没有信息增益时保持 false。"
            "普通新闻、行业动态和当前进展由 web_search 完成；不要因为报道涉及科研或 AI 就附带执行论文检索。"
        ),
        "recovery_tools": ["rich_search"],
    },
}
