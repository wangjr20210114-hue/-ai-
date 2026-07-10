"""搜索编排服务：连接搜索系统和 LLM 评估总结。

职责：
1. 调用搜索系统获取结果
2. 构建 prompt
3. 调用 LLM 流式生成回答
4. 返回元数据

不包含：底层 HTTP 搜索调用、SSE 解析（这些在各自的 service 中）
"""
from __future__ import annotations

import json
from typing import Any

from config import settings


async def build_search_prompt(
    query: str,
    results: list[dict[str, Any]],
    images: list[str],
    sources_used: list[str],
    image_descriptions: list[dict[str, str]] = None,
) -> tuple[Any, dict[str, Any]]:
    """根据搜索结果构建 prompt 并返回流式生成器 + 元数据。"""
    # 1. 构建搜索结果上下文
    context_parts = []
    for i, r in enumerate(results):
        idx = i + 1
        source = r.get("source", "web")
        title = r.get("title", "")
        snippet = r.get("snippet", "")
        url = r.get("url", r.get("article_url", ""))

        if source == "wechat":
            account = r.get("account_name", "")
            gh_id = r.get("gh_id", "")
            date = r.get("date", "")
            context_parts.append(
                f"[结果{idx}] 来源类型：微信公众号\n"
                f"标题：{title}\n"
                f"公众号：{account}（ID：{gh_id}）\n"
                f"日期：{date}\n"
                f"摘要：{snippet}\n"
                f"文章链接：{url}"
            )
        elif source == "zhihu":
            context_parts.append(
                f"[结果{idx}] 来源类型：知乎\n标题：{title}\n链接：{url}"
            )
        elif source == "baike":
            img = r.get("image", "")
            context_parts.append(
                f"[结果{idx}] 来源类型：百科\n标题：{title}\n摘要：{snippet}\n图片URL：{img}\n链接：{url}"
            )
        else:
            site = r.get("site", "")
            context_parts.append(
                f"[结果{idx}] 来源类型：网页\n标题：{title}\n站点：{site}\n摘要：{snippet}\n链接：{url}"
            )

    search_context = "\n\n".join(context_parts)
    # 图片 URL + 视觉描述（图文交错的关键：让 LLM 知道每张图拍的是什么）
    if image_descriptions:
        images_str = "以下是可用的图片及其视觉描述，请在回答中用 [[img:url]] 嵌入到相关内容旁边：\n"
        for item in image_descriptions:
            images_str += f"- {item['url']}（{item['description']}）\n"
    elif images:
        images_str = "以下是可用的图片URL，请在回答中用 [[img:url]] 嵌入：\n" + "\n".join(f"- {u}" for u in images[:8])
    else:
        images_str = "无可用图片"

    # 2. 提示词
    system_prompt = (
        "你是搜索助手。根据搜索结果回答用户问题。\n\n"
        "## 严格规则\n"
        "1. **绝对禁止暴露搜索过程**。不要说「搜索结果显示」「搜索结果未提供摘要」等话\n"
        "2. **绝对禁止编造日期**。只使用搜索结果中明确给出的日期，不要自己推断或编造\n"
        "3. **绝对禁止编造来源**。只能引用上面给出的搜索结果\n\n"
        "## 图片嵌入（图文交错）\n"
        "搜索结果中可能包含图片URL和视觉描述。根据图片描述判断图片内容，将其嵌入到最相关的正文段落旁边：\n"
        "  [[img:图片url]]\n"
        "  - 放在与图片描述最相关的段落旁边（如描述是'明朝皇宫建筑图'，放在介绍明朝建筑的段落旁）\n"
        "  - 只有当图片与正文内容相关时才嵌入，不相关的不要放\n"
        "  - 简单问题不需要图片，新闻/推荐/百科类适合用图片\n"
        "  - 不要用 Markdown 的 ![](url) 语法，只用 [[img:url]]\n"
        "  - 不要把所有图片堆在回答末尾，要穿插在正文中\n"
        "  - **绝对禁止**使用任何 mp.weixin.qq.com 或微信平台的头像图片URL\n\n"
        "## 答案长度自适应\n"
        "- 简单问题（XX是什么）：1-2句话\n"
        "- 推荐型问题（推荐什么）：一小段话 + 卡片\n"
        "- 对比型问题（A和B区别）：表格\n"
        "- 讨论型问题（怎么评价）：2-3段话\n"
        "- 绝对不要为了凑字数而展开，直击重点\n\n"
        "## 评估规则\n"
        "1. 仔细评估每条搜索结果的准确性和相关性\n"
        "2. 只选择最能解决用户问题的精华结果\n"
        "3. 明显错误、广告、不相关的信息直接忽略\n\n"
        "## 引用方式\n"
        "### 来源不穿插在正文中\n"
        "不要在正文句子后面标注来源。来源信息由系统自动展示在回答顶部。\n"
        "你只需要专注于把内容总结好，让用户直接读到答案。\n\n"
        "### 卡片：推荐用户去看的\n"
        "当搜索结果是值得用户去阅读/查看的（如知乎讨论、书单推荐、文章推荐），用卡片：\n"
        "  [[card:来源类型|标题|url|摘要]]\n"
        "  - 来源类型：公众号 / 知乎 / 网页 / 百科\n"
        "  - 标题：与上下文相关的主题概括\n"
        "  - 摘要：一句话概括（不超过30字），如果有日期请在摘要末尾标注\n"
        "  - 卡片只能用在正文段落中，不要放在表格内\n"
        "  - 百科和普通网页内容你自己总结即可，不要用卡片\n"
        "  - 知乎讨论、值得看的公众号文章用卡片\n"
        "  - 优先推荐日期最近的内容\n"
        "  - 尽量展示不同类型的来源，让回答更多元\n\n"
        "## 时效性规则\n"
        "- 优先引用日期最近的结果\n"
        "- 如果搜索结果中有明确日期，可以引用该日期\n"
        "- 如果搜索结果没有日期，不要编造日期\n\n"
        "## 其他\n"
        "1. 可以用 Markdown 表格整理对比信息\n"
        "2. 不要写「来源：XXX」这样的文字\n"
        "3. 不要在正文中插入 [来源](url) 链接\n"
        "4. 【绝对禁止】不要在结尾说『需要我帮你进一步整理』等引导语"
    )

    user_content = (
        f"搜索词：{query}\n\n"
        f"搜索结果（共 {len(results)} 条，来自 {', '.join(sources_used)}）：\n\n"
        f"{search_context}\n\n"
    )
    if image_descriptions:
        user_content += f"可用图片及视觉描述（用 [[img:url]] 嵌入到相关内容旁）：\n"
        for item in image_descriptions:
            user_content += f"- {item['url']}（{item['description']}）\n"
    elif images:
        user_content += f"可用图片URL（用 [[img:url]] 嵌入到相关内容旁）：\n" + "\n".join(f"- {u}" for u in images[:8])

    # 3. 元数据
    top_results = results[:8]
    search_meta = {
        "query": query,
        "results": [
            {
                "source": r.get("source", "web"),
                "title": r.get("title", ""),
                "snippet": r.get("snippet", "")[:80],
                "url": r.get("url", r.get("article_url", "")),
                "account_name": r.get("account_name", ""),
                "gh_id": r.get("gh_id", ""),
                "avatar": r.get("avatar", ""),
                "image": r.get("image", ""),
            }
            for r in top_results
        ],
        "images": images[:5],
        "image_descriptions": image_descriptions or [],
        "sources_used": sources_used,
        "total": len(results),
    }

    # 4. 流式调用 LLM（复用 hunyuan_service 的流式接口）
    async def stream():
        try:
            import httpx
            from services.hunyuan_service import _check_quota_error, QuotaExhaustedError

            async with httpx.AsyncClient(timeout=60) as client:
                async with client.stream(
                    "POST",
                    f"{settings.deepseek_base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {settings.deepseek_api_key}"},
                    json={
                        "model": settings.deepseek_model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_content},
                        ],
                        "max_tokens": 3000,
                        "temperature": 0.6,
                        "stream": True,
                    },
                ) as resp:
                    if resp.status_code != 200:
                        body = await resp.aread()
                        _check_quota_error(
                            resp.status_code,
                            body.decode("utf-8", errors="replace"),
                            "DeepSeek",
                        )
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        data = line[6:]
                        if data.strip() == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                            text = delta.get("content", "")
                            if text:
                                yield text
                        except (json.JSONDecodeError, IndexError):
                            continue
        except QuotaExhaustedError:
            raise
        except Exception as e:
            yield f"\n\n搜索总结失败：{e}"

    return stream(), search_meta
