MANIFEST = {
    "schema_version": 1,
    "id": "core",
    "order": 0,
    "default_enabled": True,
    "locked": True,
    "capabilities": ["papers"],
    "plan_flags": ["needs_papers"],
    "tools": [{"name": "search_arxiv", "capability": "papers"}],
    "permissions": [
        "makers.state",
        "makers.model",
        "makers.trace",
        "conversation.read",
        "user.read",
    ],
    "ui": {
        "icon": "◆",
        "name": {"zh-CN": "通用问答与创作", "zh-TW": "通用問答與創作", "en": "General chat and creation"},
        "description": {
            "zh-CN": "问答、写作、翻译、总结与自然对话。核心能力始终开启。",
            "zh-TW": "問答、寫作、翻譯、總結與自然對話。核心能力始終開啟。",
            "en": "Chat, writing, translation, summarization, and natural conversation.",
        },
    },
    "planner": {
        "topic": "paper",
        "summary": "Verifiable academic paper discovery with author, institution, topic and date filtering.",
        "instructions": (
            "【论文检索】检索论文、文献或 arXiv 用 needs_papers；paper_topic 只写用户明确指定的研究主题，"
            "只有作者、单位、年份、数量而没有主题时必须留空，不能复制整句请求；"
            "作者、年份、数量分别写入 paper_author、paper_year/paper_year_from/paper_year_to、paper_limit。"
            "中文作者名要在 paper_author 中给出最可能的英文论文署名；用户用单位限定作者时，"
            "把规范英文单位名写入 paper_institution。近 N 年按当前北京时间换算为包含首尾的年份范围。"
            "基础论文检索属于始终可用的核心问答；论文卡片、PDF 保存和助读器由独立 Skill 决定。"
        ),
        "recovery_tools": ["search_arxiv"],
    },
}
