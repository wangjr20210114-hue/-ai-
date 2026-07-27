MANIFEST = {
    "schema_version": 1,
    "id": "vision",
    "order": 20,
    "default_enabled": True,
    "capabilities": ["vision_analysis"],
    "plan_flags": ["needs_images"],
    "tools": [
        {"name": "analyze_images_parallel", "capability": "vision_analysis", "required": False},
    ],
    "permissions": ["makers.model", "makers.trace", "conversation.read", "user.read"],
    "ui": {
        "icon": "◉",
        "name": {"zh-CN": "视觉理解", "zh-TW": "視覺理解", "en": "Vision understanding"},
        "description": {
            "zh-CN": "理解上传图片，并核验搜索图片与问题的相关性。",
            "zh-TW": "理解上傳圖片，並核驗搜尋圖片與問題的相關性。",
            "en": "Understand uploaded images and verify searched-image relevance.",
        },
    },
    "planner": {
        "topic": "image",
        "summary": "Understand attached images or review public image evidence.",
    },
}
