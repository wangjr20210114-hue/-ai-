"""Configurable multimodal provider adapter chain for Makers agents.

Hunyuan remains the primary provider.  The remaining adapters are deliberately
thin HTTP clients so the application keeps only business routing while each
provider performs the actual multimodal inference.
"""

from __future__ import annotations

import asyncio
import json
import time
import urllib.request
from dataclasses import dataclass
from typing import Any

from ..._application.i18n import normalize_language, text as copy_text


@dataclass(frozen=True)
class VisionProvider:
    name: str
    endpoint: str
    api_key: str
    model: str


def _ordered_names(value: Any, defaults: list[str]) -> list[str]:
    requested = [
        item.strip().lower()
        for item in str(value or "").split(",")
        if item.strip().lower() in defaults
    ]
    return list(dict.fromkeys([*requested, *defaults]))


def _openai_endpoint(base_url: str) -> str:
    base = str(base_url or "").rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    if base.endswith("/v1") or base.endswith("/openai"):
        return f"{base}/chat/completions"
    return f"{base}/v1/chat/completions"


def vision_providers(env: dict[str, Any]) -> list[VisionProvider]:
    """Return configured providers in failover order without hidden defaults."""
    providers: list[VisionProvider] = []
    hunyuan_key = str(
        env.get("HUNYUAN_VISION_API_KEY") or env.get("HUNYUAN_IMAGE_API_KEY") or ""
    ).strip()
    if hunyuan_key:
        providers.append(VisionProvider(
            "hunyuan",
            _openai_endpoint(str(
                env.get("HUNYUAN_VISION_BASE_URL")
                or env.get("HUNYUAN_IMAGE_BASE_URL")
                or "https://tokenhub.tencentmaas.com"
            )),
            hunyuan_key,
            str(env.get("HUNYUAN_VISION_MODEL") or "hy-vision-2.0-instruct"),
        ))

    cloudflare_account = str(env.get("CLOUDFLARE_ACCOUNT_ID") or "").strip()
    cloudflare_token = str(
        env.get("CLOUDFLARE_WORKERS_AI_TOKEN") or env.get("CLOUDFLARE_API_TOKEN") or ""
    ).strip()
    if cloudflare_account and cloudflare_token:
        cloudflare_model = str(
            env.get("CLOUDFLARE_VISION_MODEL")
            or "@cf/meta/llama-3.2-11b-vision-instruct"
        )
        providers.append(VisionProvider(
            "cloudflare",
            f"https://api.cloudflare.com/client/v4/accounts/{cloudflare_account}/ai/run/{cloudflare_model}",
            cloudflare_token,
            cloudflare_model,
        ))

    dashscope_key = str(env.get("DASHSCOPE_API_KEY") or "").strip()
    if dashscope_key:
        providers.append(VisionProvider(
            "dashscope",
            _openai_endpoint(str(
                env.get("DASHSCOPE_BASE_URL")
                or "https://dashscope.aliyuncs.com/compatible-mode"
            )),
            dashscope_key,
            str(env.get("DASHSCOPE_VISION_MODEL") or "qwen3-vl-flash"),
        ))

    gemini_key = str(env.get("GEMINI_API_KEY") or "").strip()
    if gemini_key:
        providers.append(VisionProvider(
            "gemini",
            _openai_endpoint(str(
                env.get("GEMINI_OPENAI_BASE_URL")
                or "https://generativelanguage.googleapis.com/v1beta/openai"
            )),
            gemini_key,
            str(env.get("GEMINI_VISION_MODEL") or "gemini-2.5-flash-lite"),
        ))
    order = _ordered_names(
        env.get("VISION_PROVIDER_ORDER"),
        [provider.name for provider in providers],
    )
    rank = {name: index for index, name in enumerate(order)}
    return sorted(providers, key=lambda provider: rank[provider.name])


def _post_completion_with_usage(
    provider: VisionProvider,
    content: list[dict[str, Any]],
    max_tokens: int,
    timeout: float,
) -> tuple[str, dict[str, int]]:
    if provider.name == "cloudflare":
        # Workers AI's documented Llama Vision REST schema is not the
        # OpenAI multi-part content schema.  It accepts text messages plus one
        # top-level image (a data URI or HTTPS URL) at /ai/run/<model>.
        text_parts: list[str] = []
        image = ""
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "text" and item.get("text"):
                text_parts.append(str(item["text"]))
            elif item.get("type") == "image_url" and not image:
                value = item.get("image_url") or {}
                image = str(value.get("url") if isinstance(value, dict) else value or "")
        payload: dict[str, Any] = {
            "messages": [{"role": "user", "content": "\n".join(text_parts)}],
            "max_tokens": max(64, min(1600, int(max_tokens))),
            "temperature": 0.1,
            "stream": False,
        }
        if image.startswith(("https://", "data:image/")):
            payload["image"] = image
    else:
        payload = {
            "model": provider.model,
            "messages": [{"role": "user", "content": content}],
            "max_tokens": max(64, min(1600, int(max_tokens))),
            "temperature": 0.1,
            "stream": False,
        }
    request = urllib.request.Request(
        provider.endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {provider.api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=max(1.0, timeout)) as response:
        data = json.loads(response.read(4 * 1024 * 1024).decode("utf-8"))
    if provider.name == "cloudflare":
        result = data.get("result") if isinstance(data.get("result"), dict) else data
        usage = result.get("usage") if isinstance(result.get("usage"), dict) else data.get("usage")
        return str(result.get("response") or "").strip(), _usage_fields(usage)
    return str(data["choices"][0]["message"]["content"]).strip(), _usage_fields(data.get("usage"))


def _usage_fields(value: Any) -> dict[str, int]:
    usage = value if isinstance(value, dict) else {}
    try:
        input_tokens = max(0, int(
            usage.get("prompt_tokens")
            or usage.get("input_tokens")
            or 0
        ))
        output_tokens = max(0, int(
            usage.get("completion_tokens")
            or usage.get("output_tokens")
            or 0
        ))
        total_tokens = max(0, int(usage.get("total_tokens") or input_tokens + output_tokens))
    except (TypeError, ValueError):
        return {}
    if total_tokens <= 0:
        return {}
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }


def _post_completion(
    provider: VisionProvider,
    content: list[dict[str, Any]],
    max_tokens: int,
    timeout: float,
) -> str:
    """Compatibility wrapper retained for the provider adapter unit tests."""
    return _post_completion_with_usage(provider, content, max_tokens, timeout)[0]


async def vision_completion(
    env: dict[str, Any],
    content: list[dict[str, Any]],
    *,
    max_tokens: int = 800,
    timeout: float = 8.0,
) -> tuple[str, dict[str, Any]]:
    """Run the configured provider chain inside one shared latency budget."""
    providers = vision_providers(env)
    if not providers:
        return "", {"provider": "", "error": "missing_api_key", "attempted": 0}
    deadline = time.monotonic() + max(1.0, float(timeout))
    failures: list[str] = []
    for provider in providers:
        remaining = deadline - time.monotonic()
        if remaining <= 0.25:
            break
        try:
            text, usage = await asyncio.wait_for(
                asyncio.to_thread(
                    _post_completion_with_usage,
                    provider,
                    content,
                    max_tokens,
                    min(remaining, 7.0),
                ),
                timeout=remaining,
            )
            if text:
                return text, {
                    "provider": provider.name,
                    "model": provider.model,
                    "attempted": len(failures) + 1,
                    "failures": failures,
                    **usage,
                }
            failures.append(f"{provider.name}:empty")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            failures.append(f"{provider.name}:{type(exc).__name__}")
    return "", {
        "provider": "",
        "error": "providers_failed" if failures else "timeout",
        "attempted": len(failures),
        "failures": failures,
    }


async def describe_reference_images(
    env: dict[str, Any],
    images: list[str],
    user_request: str,
    *,
    timeout: float = 8.0,
    response_language: object = "zh-CN",
) -> tuple[str, dict[str, Any]]:
    """Describe user attachments once so text-only orchestration can reason over them."""
    selected = [
        str(image).strip() for image in images
        if str(image).startswith(("https://", "data:image/"))
    ][:3]
    if not selected:
        return "", {"provider": "", "attempted": 0}
    language = normalize_language(response_language)
    prompt = copy_text(
        "model.vision.reference_description", language,
        user_request=str(user_request or "")[:500],
    )

    async def describe(index: int, image: str) -> tuple[int, str, dict[str, Any]]:
        text, diagnostics = await vision_completion(
            env,
            [
                {"type": "image_url", "image_url": {"url": image}},
                {"type": "text", "text": prompt},
            ],
            max_tokens=700,
            timeout=timeout,
        )
        return index, text, diagnostics

    results = await asyncio.gather(*(describe(index, image) for index, image in enumerate(selected, 1)))
    successful = [(index, text, diagnostics) for index, text, diagnostics in results if text]
    if not successful:
        failures = [item for _index, _text, item in results]
        return "", {"provider": "", "error": "providers_failed", "attempted": len(failures), "failures": failures}
    if len(selected) == 1:
        _index, text, diagnostics = successful[0]
        return text, diagnostics
    providers = [str(item.get("provider") or "") for _index, _text, item in successful]
    input_tokens = sum(int(item.get("input_tokens") or 0) for _index, _text, item in successful)
    output_tokens = sum(int(item.get("output_tokens") or 0) for _index, _text, item in successful)
    total_tokens = sum(int(item.get("total_tokens") or 0) for _index, _text, item in successful)
    return "\n".join(
        copy_text("model.vision.reference_item", language, index=index, description=description)
        for index, description, _item in successful
    ), {
        "provider": providers[0] if len(set(providers)) == 1 else "mixed",
        "providers": providers,
        "attempted": len(results),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }
