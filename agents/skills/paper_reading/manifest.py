MANIFEST = {
    "schema_version": 1,
    "id": "paper-reading",
    "order": 70,
    "default_enabled": True,
    "capabilities": ["papers"],
    "plan_flags": ["needs_papers"],
    "tools": [{"name": "search_arxiv", "capability": "papers"}],
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
            "zh-CN": "查找并核验论文、保存 PDF，并提供结构化助读。",
            "zh-TW": "查找並核驗論文、保存 PDF，並提供結構化助讀。",
            "en": "Find and verify papers, save PDFs, and provide structured reading help.",
        },
    },
    "planner": {
        "topic": "paper",
        "summary": "Verifiable paper discovery, author and institution filtering, and arXiv results.",
    },
}
