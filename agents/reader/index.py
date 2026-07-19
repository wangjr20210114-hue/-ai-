"""Focused AI operations for the Makers PDF/paper reader."""

from ..chat._llm import get_model
from .._shared.auth import require_user
from .._shared.http import error


PROMPTS = {
    "translate": "把以下学术文本准确翻译成中文。保留公式、术语和引用编号，不添加原文没有的内容。",
    "summarize": "用中文简洁总结以下学术文本的核心论点、方法和结论。",
    "explain": "用中文解释以下术语或文本，先给直观解释，再说明它在论文语境中的含义。",
    "formula": "解释以下公式或数学文本中各符号、关系、用途和直观含义；信息不足时明确说明。",
    "analyze": "阅读以下论文文本，按研究问题、方法、数据/实验、主要结论、创新点、局限性和可复现线索给出结构化中文助读。引用页码标记若原文包含页码。",
    "full-translate": "把以下论文文本翻译成中文，保持标题和段落结构，保留公式与引用。文本可能是分块内容，不要省略。",
    "terms": "提取以下论文最重要的术语，给出英文、中文译名和一句语境解释。",
    "qa": "仅依据给出的论文文本回答问题。结论必须可由文本支持；找不到时明确说论文片段未提供，并指出还需要哪部分。",
}


def _text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(str(item.get("text") or "") for item in content if isinstance(item, dict))
    return str(content or "")


async def handler(ctx):
    require_user(ctx)
    body = ctx.request.body or {}
    action = str(body.get("action") or "")
    text = str(body.get("text") or "").strip()
    question = str(body.get("question") or "").strip()
    if action not in PROMPTS:
        return error("不支持的助读操作")
    if not text:
        return error("缺少可分析的论文文本")
    limit = 120000 if action in {"analyze", "full-translate", "terms", "qa"} else 12000
    text = text[:limit]
    user = f"论文文本：\n{text}"
    if action == "qa":
        if not question:
            return error("问题不能为空")
        user += f"\n\n问题：{question[:2000]}"
    try:
        response = await get_model(ctx.env).ainvoke([
            {"role": "system", "content": PROMPTS[action]},
            {"role": "user", "content": user},
        ])
        return {"content": _text(getattr(response, "content", ""))}
    except Exception as exc:
        return error(f"助读失败：{exc}", 500)
