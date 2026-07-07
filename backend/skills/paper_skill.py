"""科研论文助读技能。

流程：
1. 用户说"帮我找Transformer的论文" → LLM 生成推荐列表（标题/摘要/arXiv ID）
2. 返回 suggest 卡片 + 论文列表
3. 用户点某篇 → 前端调 /api/paper/download?id=xxx 下载 PDF
4. 下载完成 → 自动打开 PaperReader 阅读器
"""
from __future__ import annotations

from typing import Any

from skills.base_skill import BaseSkill, SkillResult


class PaperSkill(BaseSkill):
    """科研论文助读：搜索 → 推荐 → 下载 → 阅读。"""

    @property
    def name(self) -> str:
        return "paper"

    @property
    def description(self) -> str:
        return (
            "科研论文搜索与助读。用户想找论文、读论文、搜索某领域文献时触发。"
            "支持推荐论文、自动下载、选词翻译、段落总结、全文分析、术语提取、论文问答"
        )

    @property
    def trigger_keywords(self) -> list[str]:
        return ["论文", "文献", "arXiv", "arxiv", "学术", "paper", "读懂", "论文阅读", "找论文", "最新研究"]

    @property
    def icon(self) -> str:
        return "📄"

    @property
    def action_label(self) -> str:
        return "搜索论文"

    @property
    def mode(self) -> str:
        return "auto"

    async def suggest(self, message: str, params: dict[str, Any]) -> SkillResult:
        topic = params.get("topic", "")

        if not topic:
            # 从消息中提取主题（去掉"论文""帮我找""我想看"等无用词）
            import re
            topic = re.sub(r'(帮我|我想|我想看|我想读|帮我找|搜索|查一下|看看|读一下|这篇|一些|相关|的|关于|请问)', '', message).strip()
            if not topic:
                topic = message

        prompt = f"我来帮你找关于「{topic}」的论文 📄\n\n正在搜索相关论文..."

        return SkillResult(
            intent=self.name,
            mode=self.mode,
            content=prompt,
            icon=self.icon,
            action_label=self.action_label,
            params={**params, "topic": topic, "message": message},
            data={"topic": topic},
        )
