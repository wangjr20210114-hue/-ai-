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
        "instructions": (
            "【论文】检索论文、文献或 arXiv 用 needs_papers；paper_topic 只写用户明确指定的研究主题，"
            "只有作者、单位、年份、数量而没有主题时必须留空，不能复制整句请求；"
            "只有还要求普通网页、新闻或跨来源综述时才同时 web_search。作者、年份、数量分别"
            "写入 paper_author、paper_year/paper_year_from/paper_year_to、paper_limit。"
            "中文作者名要在 paper_author 中给出最可能的英文论文署名；用户用单位限定作者时，"
            "把规范英文单位名写入 paper_institution。近 N 年按当前北京时间换算为包含首尾的年份范围。"
        ),
        "recovery_tools": ["rich_search", "search_arxiv"],
    },
}
