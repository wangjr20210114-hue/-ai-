"""Trusted image and visual-analysis operations for system Skill adapters."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any, Awaitable, Callable
from urllib.parse import urlparse

from ..._application.workspace.service import (
    begin_action_execution,
    finish_provider_call,
    get_action,
    image_versions,
    new_action,
    put_action,
    seal_action_snapshot,
    start_provider_call,
)
from .route_resolution import _message_text
from .visual_context import TurnVisualContext
from ..._application.i18n import text


AsyncOperation = Callable[..., Awaitable[Any]]
OperationProvider = Callable[[], AsyncOperation]
StateLoader = Callable[[], Awaitable[dict[str, Any]]]
StateSaver = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


def build_image_operations(
    *,
    model: Any,
    store: Any,
    user_id: str,
    runtime_env: dict[str, Any],
    load_state: StateLoader,
    save_state: StateSaver,
    visual_context: TurnVisualContext,
    generate_image_provider: OperationProvider,
    resolve_image_reference_provider: OperationProvider,
    collect_page_images_provider: OperationProvider,
    record_provider_usage_provider: OperationProvider,
    response_language: object = "zh-CN",
) -> dict[str, AsyncOperation]:
    """Build image operations with explicit provider and Maker dependencies."""

    async def propose_image(
        prompt: str,
        parent_action_id: str = "",
        reference_image_urls: list[str] | None = None,
    ) -> str:
        """Generate an image immediately, optionally editing one prior generated version."""
        clean_prompt = str(prompt or "").strip()[:2000]
        if not clean_prompt:
            raise ValueError(text("image.prompt_required", response_language))
        state = await load_state()
        parent = state.get("actions", {}).get(str(parent_action_id or ""))
        references: list[str] = []
        group_id = ""
        if isinstance(parent, dict) and parent.get("kind") == "image_generate":
            parent_payload = parent.get("payload") or {}
            parent_result = parent.get("result") or {}
            reference_url = await resolve_image_reference_provider()(parent_result)
            if reference_url.startswith(("https://", "data:image/")):
                references.append(reference_url)
            group_id = str(parent_payload.get("group_id") or parent.get("id") or "")
        elif visual_context.image_group_id:
            group_id = visual_context.image_group_id
        for raw_url in reference_image_urls or []:
            url = str(raw_url or "").strip()
            if url.startswith(("https://", "data:image/")) and url not in references:
                references.append(url)
            if len(references) >= 3:
                break
        if not group_id and not references:
            references.extend(visual_context.references[:3])
        action = new_action(
            "image_generate",
            {
                "prompt": clean_prompt,
                "parent_action_id": str(parent_action_id or ""),
                "group_id": group_id,
                "reference_image_urls": references,
            },
            requires_confirmation=False,
        )
        action["payload"]["group_id"] = group_id or action["id"]
        seal_action_snapshot(action)
        if not visual_context.image_group_id:
            visual_context.image_group_id = str(action["payload"]["group_id"])
        now = int(datetime.now().timestamp())
        begin_action_execution(action, owner=f"chat:{action['id']}", now=now)
        put_action(state, action)
        start_provider_call(state, action, now)
        await save_state(state)
        result = await generate_image_provider()(
            runtime_env,
            clean_prompt,
            references,
            user_id=user_id,
        )
        if result.get("ok"):
            await record_provider_usage_provider()(
                store,
                user_id,
                str(result.get("provider") or "image_provider"),
                "images",
                1,
                model=str(result.get("model") or ""),
                source="chat_image",
            )
        state = await load_state()
        current = get_action(state, action["id"])
        finish_provider_call(state, current, result, int(datetime.now().timestamp()))
        if result.get("ok"):
            current["result"]["versions"] = image_versions(
                state,
                str(current["payload"]["group_id"]),
            )
        state = await save_state(state)
        action = state["actions"][action["id"]]
        return json.dumps(
            {"ui_action": "side_effect_action", "action": action},
            ensure_ascii=False,
        )

    async def collect_page_images(page_url: str, max_images: int = 30) -> str:
        """Collect up to 30 real image candidates from one public HTML page."""
        images = await collect_page_images_provider()(page_url, max_images)
        return json.dumps(
            {"page_url": page_url, "images": images, "count": len(images)},
            ensure_ascii=False,
        )

    async def analyze_images_parallel(image_urls: list[str], goal: str) -> str:
        """Evaluate up to 30 images in small isolated concurrent batches."""
        image_urls = list(dict.fromkeys(str(url) for url in image_urls))[:30]
        if not image_urls:
            raise ValueError(text("image.url_required", response_language))
        for url in image_urls:
            if urlparse(url).scheme not in {"http", "https"}:
                raise ValueError(text("image.url_protocol", response_language))
        semaphore = asyncio.Semaphore(4)

        async def inspect(index: int, image_url: str) -> dict[str, Any]:
            async with semaphore:
                try:
                    response = await asyncio.wait_for(
                        model.ainvoke([{"role": "user", "content": [
                            {
                                "type": "text",
                                "text": text(
                                    "model.vision.goal_review", response_language,
                                    goal=goal,
                                ),
                            },
                            {
                                "type": "image_url",
                                "image_url": {"url": image_url},
                            },
                        ]}]),
                        timeout=45,
                    )
                    return {
                        "index": index,
                        "url": image_url,
                        "analysis": _message_text(
                            getattr(response, "content", ""),
                        )[:1200],
                        "ok": True,
                    }
                except Exception as exc:
                    return {
                        "index": index,
                        "url": image_url,
                        "analysis": "",
                        "ok": False,
                        "error": str(exc)[:200],
                    }

        results = await asyncio.gather(*(
            inspect(index, url)
            for index, url in enumerate(image_urls)
        ))
        return json.dumps(
            {"ui_action": "image_analysis", "analyses": results},
            ensure_ascii=False,
        )

    return {
        "propose_image": propose_image,
        "collect_page_images": collect_page_images,
        "analyze_images_parallel": analyze_images_parallel,
    }


__all__ = ("build_image_operations",)
