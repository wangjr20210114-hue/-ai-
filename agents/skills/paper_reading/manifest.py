MANIFEST = {
    "schema_version": 1,
    "id": "paper-reading",
    "order": 70,
    "default_enabled": True,
    "capabilities": ["paper_assistant"],
    "plan_flags": [],
    "tools": [],
    "recommends": ["web-search"],
    "permissions": [
        "makers.state",
        "makers.blob",
        "makers.model",
        "makers.trace",
        "conversation.read",
        "user.read",
    ],
    "ui": {
        "icon": "▤",
        "name": {"zh-CN": "论文检索与助读", "zh-TW": "論文檢索與助讀", "en": "Paper search and assistant"},
        "description": {
            "zh-CN": "为基础论文搜索增加论文卡片、PDF 保存和结构化助读器。",
            "zh-TW": "為基礎論文搜尋增加論文卡片、PDF 儲存和結構化助讀器。",
            "en": "Add paper cards, PDF saving, and a structured reader to basic paper search.",
        },
    },
}
