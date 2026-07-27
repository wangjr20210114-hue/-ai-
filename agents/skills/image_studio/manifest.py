MANIFEST = {
    "schema_version": 1,
    "id": "image-studio",
    "order": 30,
    "default_enabled": True,
    "capabilities": ["image_generation"],
    "plan_flags": ["needs_image_generation"],
    "tools": [{"name": "propose_image", "capability": "image_generation"}],
    "action_kinds": ["image_generate"],
    "recommends": ["vision", "web-search"],
    "permissions": ["makers.blob", "makers.state", "makers.trace", "conversation.read", "user.read"],
    "env_keys": [
        "HUNYUAN_IMAGE_API_KEY",
        "HUNYUAN_IMAGE_BASE_URL",
        "HUNYUAN_IMAGE_MODEL",
    ],
    "ui": {
        "icon": "◈",
        "name": {"zh-CN": "图片工坊", "zh-TW": "圖片工坊", "en": "Image studio"},
        "description": {
            "zh-CN": "混元文生图、参考图生图和连续修改。",
            "zh-TW": "混元文字生圖、參考圖生圖和連續修改。",
            "en": "Hunyuan text-to-image, reference generation, and iterative editing.",
        },
    },
    "planner": {
        "topic": "image",
        "summary": "Generate or edit an image from text or visual references.",
    },
}
