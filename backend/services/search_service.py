"""Build grounded search prompts and structured rich-answer metadata."""
from __future__ import annotations

from typing import Any

from config import settings
from services.model_gateway import ModelRequest
from services.rich_media_service import (
    MediaAsset,
    RichSearchMetadata,
    SourceReference,
    build_source_references,
)


def _source_context(source: SourceReference) -> str:
    extras = []
    if source.account_name:
        extras.append(f"账号：{source.account_name}")
    if source.date:
        extras.append(f"日期：{source.date}")
    extra_text = "\n".join(extras)
    return (
        f"[{source.id}] 来源类型：{source.source}\n"
        f"标题：{source.title}\n"
        f"摘要：{source.snippet}\n"
        f"链接：{source.url}"
        + (f"\n{extra_text}" if extra_text else "")
    )


def prepare_search_prompt(
    query: str,
    results: list[dict[str, Any]],
    images: list[str],
    sources_used: list[str],
    image_descriptions: list[dict[str, str]] | None = None,
    media: list[dict[str, Any]] | None = None,
    source_references: list[dict[str, Any]] | None = None,
) -> tuple[ModelRequest, dict[str, Any]]:
    """Return an LLM request plus the trusted metadata used by the UI."""
    del images
    sources = [SourceReference.model_validate(item) for item in (source_references or [])]
    if not sources:
        sources = build_source_references(results)
    assets = [MediaAsset.model_validate(item) for item in (media or [])]

    source_context = "\n\n".join(_source_context(source) for source in sources)
    if assets:
        media_context = "\n".join(
            f"- {asset.id}：{asset.caption}；对应来源 {asset.source_id or '未知'}"
            for asset in assets
        )
    else:
        media_context = "无可用图片。不要输出任何 image 标记。"

    system_prompt = """你是搜索助手。基于给定证据直接回答用户问题。

## 事实与引用
1. 只能使用提供的来源，不得编造来源、日期、数字或结论。
2. 事实性段落应在相关句子末尾加入 [[cite:source-id]]，source-id 必须来自证据列表。
3. 不要直接输出来源 URL；界面会根据 source-id 渲染安全链接。
4. 对互相冲突的来源要明确说明分歧，不要强行合并。

## 图文交错
1. 只有图片能帮助理解时才使用图片。
2. 在最相关段落后单独一行输出 [[image:media-id]]。
3. media-id 必须来自媒体列表；禁止输出图片 URL、Markdown 图片或不存在的 ID。
4. 图片不能代替事实证据。不要把所有图片堆在结尾。
5. 简单定义题通常不需要图片；地点、人物、产品、历史、教程和新闻可使用 1–3 张。

## 来源卡片
当确实值得用户打开原文阅读时，单独一行输出 [[card:source-id]]。不要把卡片放进表格。

## 表达
- 简单问题简短回答；复杂问题分段说明；对比问题可以使用 Markdown 表格。
- 不要暴露搜索过程，不要写“搜索结果显示”。
- 不要为了凑字数扩写，也不要在结尾追加营销式追问。
"""

    user_content = (
        f"用户问题：{query}\n\n"
        f"可引用来源：\n{source_context or '无'}\n\n"
        f"可引用媒体（只有 ID 和描述可用于输出）：\n{media_context}"
    )

    rich_metadata = RichSearchMetadata(
        query=query,
        results=sources,
        media=assets,
        sources_used=sources_used,
        total=len(sources),
    ).model_dump()
    rich_metadata["images"] = [asset.url for asset in assets]
    rich_metadata["image_descriptions"] = image_descriptions or []

    request = ModelRequest(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        provider="deepseek",
        model=settings.deepseek_model,
        max_tokens=3000,
        temperature=0.3,
        operation="search_summary",
    )
    return request, rich_metadata


async def build_search_prompt(
    query: str,
    results: list[dict[str, Any]],
    images: list[str],
    sources_used: list[str],
    image_descriptions: list[dict[str, str]] | None = None,
    media: list[dict[str, Any]] | None = None,
    source_references: list[dict[str, Any]] | None = None,
) -> tuple[ModelRequest, dict[str, Any]]:
    """Compatibility entry point used by the older SearchAgent wrapper."""
    return prepare_search_prompt(
        query,
        results,
        images,
        sources_used,
        image_descriptions,
        media,
        source_references,
    )
