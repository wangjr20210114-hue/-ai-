"""Confirmed side-effect providers; not an Agent route."""

from __future__ import annotations

import asyncio
import base64
from datetime import datetime
import hashlib
import hmac
import json
import logging
import re
import secrets
import socket
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any


def _meeting_result(data: dict[str, Any], subject: str, start_iso: str) -> dict[str, Any]:
    meetings = data.get("meeting_info_list")
    meeting = meetings[0] if isinstance(meetings, list) and meetings and isinstance(meetings[0], dict) else None
    if not meeting:
        error = data.get("message") or data.get("error") or data.get("error_info") or "腾讯会议未返回会议信息"
        return {"ok": False, "error": str(error)}
    return {
        "ok": True,
        "meeting_id": str(meeting.get("meeting_id") or ""),
        "meeting_code": str(meeting.get("meeting_code") or ""),
        "join_url": str(meeting.get("join_url") or ""),
        "subject": str(meeting.get("subject") or subject),
        "start_time": start_iso,
    }


def _meeting_epoch(value: str) -> int:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("腾讯会议时间必须是带时区的 ISO 8601") from exc
    if parsed.tzinfo is None:
        raise ValueError("腾讯会议时间必须包含时区")
    return int(parsed.timestamp())


def _meeting_signature(secret_id: str, secret_key: str, nonce: str, timestamp: str, body: str) -> str:
    header = f"X-TC-Key={secret_id}&X-TC-Nonce={nonce}&X-TC-Timestamp={timestamp}"
    value = f"POST\n{header}\n/v1/meetings\n{body}"
    hex_digest = hmac.new(secret_key.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).hexdigest()
    return base64.b64encode(hex_digest.encode("ascii")).decode("ascii")


def _meeting_payload(env: dict[str, Any], subject: str, start_iso: str, end_iso: str) -> dict[str, Any]:
    start_time = _meeting_epoch(start_iso)
    end_time = _meeting_epoch(end_iso)
    if end_time <= start_time:
        raise ValueError("腾讯会议结束时间必须晚于开始时间")
    return {
        "userid": str(env.get("TENCENT_MEETING_USER_ID") or "").strip(),
        "instanceid": int(env.get("TENCENT_MEETING_INSTANCE_ID") or 1),
        "subject": str(subject).strip()[:240],
        "type": 0,
        "start_time": str(start_time),
        "end_time": str(end_time),
    }


class MeetingResultUnknown(RuntimeError):
    """The provider may have accepted the request but no response was observed."""


def _find_meeting_payload(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        if any(key in value for key in ("meeting_id", "meeting_code", "join_url")):
            return value
        for nested in value.values():
            found = _find_meeting_payload(nested)
            if found:
                return found
    elif isinstance(value, list):
        for nested in value:
            found = _find_meeting_payload(nested)
            if found:
                return found
    elif isinstance(value, str):
        try:
            return _find_meeting_payload(json.loads(value))
        except json.JSONDecodeError:
            return None
    return None


def _find_meeting_trace(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("X-Tc-Trace", "x-tc-trace", "rpcUuid", "rpc_uuid", "trace_id"):
            if value.get(key):
                return str(value[key])
        for nested in value.values():
            found = _find_meeting_trace(nested)
            if found:
                return found
    elif isinstance(value, list):
        for nested in value:
            found = _find_meeting_trace(nested)
            if found:
                return found
    return ""


def _post_tencent_meeting_mcp(env: dict[str, Any], subject: str, start_iso: str, end_iso: str) -> dict[str, Any]:
    """Call Tencent Meeting's official remote MCP using a personal Skill token."""
    token = str(env.get("TENCENT_MEETING_TOKEN") or "").strip()
    if not token:
        raise ValueError("腾讯会议 Skill 尚未安装")
    if _meeting_epoch(end_iso) <= _meeting_epoch(start_iso):
        raise ValueError("腾讯会议结束时间必须晚于开始时间")
    endpoint = str(
        env.get("TENCENT_MEETING_MCP_URL")
        or "https://mcp.meeting.tencent.com/mcp/wemeet-open/v1"
    ).strip()
    payload = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": "schedule_meeting",
            "arguments": {
                "subject": str(subject or "腾讯会议")[:240],
                "start_time": start_iso,
                "end_time": end_iso,
                "_client_info": {"os": "EdgeOne-Makers", "agent": "yuanbao", "model": "configured"},
            },
        },
        "id": uuid.uuid4().hex,
    }
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-Tencent-Meeting-Token": token,
            "X-Skill-Version": str(env.get("TENCENT_MEETING_SKILL_VERSION") or "v1.0.11"),
        },
        method="POST",
    )
    response_trace = ""
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            headers = getattr(response, "headers", None)
            if headers is not None:
                response_trace = str(headers.get("X-Tc-Trace") or headers.get("x-tc-trace") or "")
            data = json.loads(response.read(2 * 1024 * 1024).decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code >= 500:
            raise MeetingResultUnknown(f"腾讯会议 MCP 返回 {exc.code}，结果未知") from exc
        return {"ok": False, "error": f"腾讯会议授权失效或请求被拒绝（{exc.code}）"}
    except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
        raise MeetingResultUnknown("腾讯会议 MCP 请求中断，外部结果未知") from exc
    if isinstance(data.get("error"), dict):
        return {"ok": False, "error": str(data["error"].get("message") or "腾讯会议 MCP 调用失败")[:300]}
    result = data.get("result") if isinstance(data, dict) else None
    if isinstance(result, dict) and isinstance(result.get("error"), dict):
        return {"ok": False, "error": str(result["error"].get("message") or "腾讯会议 MCP 调用失败")[:300]}
    meeting = _find_meeting_payload(result)
    if not meeting:
        return {"ok": False, "error": "腾讯会议 MCP 未返回可识别的会议信息"}
    return {
        "ok": True,
        "meeting_id": str(meeting.get("meeting_id") or ""),
        "meeting_code": str(meeting.get("meeting_code") or ""),
        "join_url": str(meeting.get("join_url") or meeting.get("meeting_url") or ""),
        "subject": str(meeting.get("subject") or subject),
        "start_time": start_iso,
        "provider": "tencent-meeting-official-mcp",
        "trace_id": response_trace or _find_meeting_trace(data),
    }


def _post_tencent_meeting(env: dict[str, Any], subject: str, start_iso: str, end_iso: str) -> dict[str, Any]:
    secret_id = str(env.get("TENCENT_MEETING_SECRET_ID") or "").strip()
    secret_key = str(env.get("TENCENT_MEETING_SECRET_KEY") or "").strip()
    app_id = str(env.get("TENCENT_MEETING_APP_ID") or "").strip()
    sdk_id = str(env.get("TENCENT_MEETING_SDK_ID") or "").strip()
    payload = _meeting_payload(env, subject, start_iso, end_iso)
    if not all((secret_id, secret_key, app_id, sdk_id, payload["userid"])):
        raise ValueError("腾讯会议服务端 API 配置不完整")
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    timestamp = str(int(datetime.now().timestamp()))
    nonce = str(secrets.randbelow(2_000_000_000) + 1)
    request = urllib.request.Request(
        "https://api.meeting.qq.com/v1/meetings",
        data=body.encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-TC-Key": secret_id,
            "X-TC-Timestamp": timestamp,
            "X-TC-Nonce": nonce,
            "X-TC-Signature": _meeting_signature(secret_id, secret_key, nonce, timestamp, body),
            "X-TC-Registered": "1",
            "AppId": app_id,
            "SdkId": sdk_id,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            response_body = response.read(1024 * 1024)
    except urllib.error.HTTPError as exc:
        response_body = exc.read(1024 * 1024)
        detail = response_body.decode("utf-8", errors="replace")[:1000]
        if exc.code >= 500:
            raise MeetingResultUnknown(f"腾讯会议返回 {exc.code}，结果未知") from exc
        try:
            data = json.loads(detail)
            detail = str(data.get("message") or data.get("error_info") or data.get("error") or detail)
        except json.JSONDecodeError:
            pass
        return {"ok": False, "error": f"腾讯会议拒绝请求（{exc.code}）：{detail}"}
    except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
        raise MeetingResultUnknown("腾讯会议请求中断，外部结果未知") from exc
    try:
        data = json.loads(response_body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise MeetingResultUnknown("腾讯会议返回无法解析，外部结果未知") from exc
    return _meeting_result(data, subject, start_iso)


async def create_tencent_meeting(env: dict[str, Any], subject: str, start_iso: str, end_iso: str) -> dict[str, Any]:
    """Create through the personal official MCP, with the legacy server API as fallback."""
    try:
        provider = _post_tencent_meeting_mcp if str(env.get("TENCENT_MEETING_TOKEN") or "").strip() else _post_tencent_meeting
        return await asyncio.to_thread(provider, env, subject, start_iso, end_iso)
    except MeetingResultUnknown as exc:
        return {"ok": False, "error": str(exc), "reconciliation_required": True}
    except Exception as exc:
        return {"ok": False, "error": f"创建腾讯会议失败：{exc}"}


def _post_image(
    url: str,
    api_key: str,
    model: str,
    prompt: str,
    reference_images: list[str] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"model": model, "prompt": prompt}
    if "/v1/images/generations" in url:
        payload.update({"size": "1024:1024", "revise": 1})
        if reference_images:
            payload["images"] = reference_images[:3]
    else:
        payload["rsp_img_type"] = "url"
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        body = response.read(2 * 1024 * 1024)
    data = json.loads(body.decode("utf-8"))
    image_url = (((data.get("data") or [{}])[0]) or {}).get("url")
    if not image_url:
        raise RuntimeError("生图服务未返回图片地址")
    return {"ok": True, "image_url": image_url, "prompt": prompt, "model": model}


def _reference_bytes(value: str) -> tuple[bytes, str]:
    reference = str(value or "").strip()
    if reference.startswith("data:image/"):
        header, encoded = reference.split(",", 1)
        mime = header.split(";", 1)[0].split(":", 1)[1].lower()
        body = base64.b64decode(encoded, validate=True)
        if not body or len(body) > 8 * 1024 * 1024:
            raise ValueError("参考图片大小无效或超过 8MB")
        return body, mime
    return _download_image(reference)


def _post_cloudflare_image(
    account_id: str,
    api_token: str,
    model: str,
    prompt: str,
    reference_images: list[str] | None = None,
) -> tuple[bytes, str]:
    references = list(reference_images or [])
    payloads: list[dict[str, Any]] = []
    if references:
        body, _mime = _reference_bytes(references[0])
        common = {
            "prompt": prompt,
            "strength": 0.72,
            "num_steps": 12,
        }
        # Cloudflare's canonical img2img example sends the reference as an
        # integer byte array.  The raw REST schema also accepts image_b64, so
        # keep that as a bounded compatibility retry for older gateways.
        if len(body) <= 2 * 1024 * 1024:
            payloads.append({**common, "image": list(body)})
        payloads.append({**common, "image_b64": base64.b64encode(body).decode("ascii")})
    else:
        payloads.append({"prompt": prompt, "steps": 4})
    endpoint = (
        f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}"
    )
    response_body = b""
    content_type = ""
    for index, payload in enumerate(payloads):
        request = urllib.request.Request(
            endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                content_type = str(response.headers.get("Content-Type") or "").split(";", 1)[0].lower()
                response_body = response.read(16 * 1024 * 1024 + 1)
            break
        except urllib.error.HTTPError as exc:
            if index + 1 < len(payloads) and int(exc.code or 0) in {400, 404, 415, 422}:
                continue
            raise
    if not response_body or len(response_body) > 16 * 1024 * 1024:
        raise RuntimeError("Workers AI 返回图片大小无效")
    if content_type.startswith("image/"):
        return response_body, content_type
    data = json.loads(response_body.decode("utf-8"))
    result = data.get("result") if isinstance(data.get("result"), dict) else data
    encoded = str(result.get("image") or result.get("image_b64") or "")
    if encoded.startswith("data:image/"):
        return _reference_bytes(encoded)
    if not encoded:
        raise RuntimeError("Workers AI 未返回图片")
    return base64.b64decode(encoded), "image/jpeg"


def _cloudflare_image_prompt(
    account_id: str,
    api_token: str,
    model: str,
    prompt: str,
) -> str:
    """Translate CJK image instructions for image models that follow English best."""
    if not re.search(r"[\u3400-\u9fff]", prompt):
        return prompt
    endpoint = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}"
    payload = {
        "messages": [
            {
                "role": "system",
                "content": (
                    "Translate Chinese image-generation or image-editing instructions into one precise "
                    "English diffusion prompt. Preserve every subject, color, layout, background, exclusion, "
                    "and edit constraint. Output only the English prompt, without quotes or explanation."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "max_completion_tokens": 300,
        "temperature": 0,
    }
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.loads(response.read(1024 * 1024).decode("utf-8"))
    result = data.get("result") if isinstance(data, dict) else None
    translated = ""
    if isinstance(result, dict):
        translated = str(result.get("response") or "").strip()
        choices = result.get("choices")
        if not translated and isinstance(choices, list) and choices:
            choice = choices[0] if isinstance(choices[0], dict) else {}
            message = choice.get("message") if isinstance(choice.get("message"), dict) else {}
            translated = str(message.get("content") or choice.get("text") or "").strip()
    translated = translated.strip().strip("`").strip().strip('"').strip()
    if not translated or re.search(r"[\u3400-\u9fff]", translated):
        raise RuntimeError("Workers AI 未返回纯英文图片提示词")
    return translated[:2048]


def _download_image(url: str) -> tuple[bytes, str]:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        raise ValueError("生成图片地址必须使用 HTTPS")
    request = urllib.request.Request(url, headers={"User-Agent": "Yuanbao-Agent/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        content_type = str(response.headers.get("Content-Type") or "image/png").split(";", 1)[0].lower()
        if not content_type.startswith("image/"):
            raise ValueError("生图服务返回的不是图片")
        body = response.read(12 * 1024 * 1024 + 1)
    if not body or len(body) > 12 * 1024 * 1024:
        raise ValueError("生成图片大小无效或超过 12MB")
    return body, content_type


async def _persist_generated_image(image_url: str, storage_prefix: str = "") -> dict[str, str]:
    """Copy a provider URL into Makers Blob so image history does not expire."""
    try:
        from pages_blob import get_store

        body, content_type = await asyncio.to_thread(_download_image, image_url)
        suffix = {"image/jpeg": "jpg", "image/webp": "webp", "image/bmp": "bmp"}.get(content_type, "png")
        key = f"{storage_prefix}generated/{uuid.uuid4().hex}.{suffix}"
        store = get_store("yuanbao-files", consistency="strong")
        await store.set(key, body, cache_control="private, max-age=31536000")
        return {"storage_key": key, "image_url": f"/files?key={urllib.parse.quote(key)}"}
    except Exception:
        # A provider URL is still useful if Blob is temporarily unavailable.
        return {"storage_key": "", "image_url": image_url}


async def _persist_generated_bytes(
    body: bytes,
    content_type: str,
    storage_prefix: str = "",
) -> dict[str, str]:
    """Persist a provider's binary/base64 response directly in Makers Blob."""
    try:
        from pages_blob import get_store

        if not body or len(body) > 16 * 1024 * 1024:
            raise ValueError("生成图片大小无效或超过 16MB")
        mime = str(content_type or "image/png").split(";", 1)[0].lower()
        suffix = {"image/jpeg": "jpg", "image/webp": "webp", "image/bmp": "bmp"}.get(mime, "png")
        key = f"{storage_prefix}generated/{uuid.uuid4().hex}.{suffix}"
        store = get_store("yuanbao-files", consistency="strong")
        await store.set(key, body, cache_control="private, max-age=31536000")
        return {"storage_key": key, "image_url": f"/files?key={urllib.parse.quote(key)}"}
    except Exception:
        mime = str(content_type or "image/png").split(";", 1)[0].lower()
        return {
            "storage_key": "",
            "image_url": f"data:{mime};base64,{base64.b64encode(body).decode('ascii')}",
        }


async def resolve_image_reference(result: dict[str, Any], prefer_blob: bool = False) -> str:
    """Prefer the persistent Blob copy when editing an older image version."""
    provider_url = str(result.get("provider_image_url") or "")
    if not prefer_blob and provider_url.startswith("https://"):
        return provider_url
    key = str(result.get("storage_key") or "")
    if key.startswith("generated/"):
        try:
            from pages_blob import get_store
            body = await get_store("yuanbao-files", consistency="strong").get(key, type="bytes")
            if isinstance(body, bytes) and body:
                mime = "image/jpeg" if key.endswith(".jpg") else "image/webp" if key.endswith(".webp") else "image/png"
                return f"data:{mime};base64,{base64.b64encode(body).decode('ascii')}"
        except Exception:
            pass
    return provider_url or str(result.get("image_url") or "")


async def generate_image(
    env: dict[str, Any],
    prompt: str,
    reference_images: list[str] | None = None,
    user_id: str = "local-user",
) -> dict[str, Any]:
    api_key = str(env.get("HUNYUAN_IMAGE_API_KEY") or "").strip()
    base_url = str(env.get("HUNYUAN_IMAGE_BASE_URL") or "https://tokenhub.tencentmaas.com").rstrip("/")
    model = str(env.get("HUNYUAN_IMAGE_MODEL") or "hy-image-v3.0")
    storage_prefix = ""
    references = [str(url).strip() for url in (reference_images or []) if str(url).startswith(("https://", "data:image/"))][:3]
    failures: list[str] = []

    async def try_hunyuan() -> dict[str, Any] | None:
        if not api_key:
            return None
        try:
            endpoint = f"{base_url}/v1/images/generations" if model.lower() == "hy-image-v3.0" or references else f"{base_url}/v1/api/image/lite"
            result = await asyncio.to_thread(
                _post_image, endpoint, api_key, model, prompt, references,
            )
            provider_image_url = str(result["image_url"])
            persisted = await _persist_generated_image(provider_image_url, storage_prefix)
            return {
                **result,
                "provider": "hunyuan",
                "provider_image_url": provider_image_url,
                **persisted,
                "reference_images": references,
                "fallback": bool(failures),
            }
        except Exception as exc:
            failures.append(f"混元：{type(exc).__name__}")
            # Preserve legacy text-to-image availability when v3 is not enabled.
            if not references and model.lower() == "hy-image-v3.0":
                try:
                    result = await asyncio.to_thread(
                        _post_image, f"{base_url}/v1/api/image/lite", api_key, "hy-image-lite", prompt, [],
                    )
                    provider_image_url = str(result["image_url"])
                    persisted = await _persist_generated_image(provider_image_url, storage_prefix)
                    return {
                        **result,
                        "provider": "hunyuan",
                        "provider_image_url": provider_image_url,
                        **persisted,
                        "reference_images": [],
                        "fallback": True,
                    }
                except Exception as fallback_exc:
                    failures.append(f"混元 Lite：{type(fallback_exc).__name__}")
        return None

    cloudflare_account = str(env.get("CLOUDFLARE_ACCOUNT_ID") or "").strip()
    cloudflare_token = str(
        env.get("CLOUDFLARE_WORKERS_AI_TOKEN") or env.get("CLOUDFLARE_API_TOKEN") or ""
    ).strip()
    async def try_cloudflare() -> dict[str, Any] | None:
        if not cloudflare_account or not cloudflare_token:
            return None
        cloudflare_model = str(
            env.get("CLOUDFLARE_IMAGE_EDIT_MODEL")
            or "@cf/runwayml/stable-diffusion-v1-5-img2img"
        ) if references else str(
            env.get("CLOUDFLARE_IMAGE_MODEL")
            or "@cf/black-forest-labs/flux-1-schnell"
        )
        try:
            translation_model = str(
                env.get("CLOUDFLARE_PROMPT_TRANSLATION_MODEL")
                or "@cf/zai-org/glm-4.7-flash"
            )
            provider_prompt = await asyncio.to_thread(
                _cloudflare_image_prompt,
                cloudflare_account,
                cloudflare_token,
                translation_model,
                prompt,
            )
            body, content_type = await asyncio.to_thread(
                _post_cloudflare_image,
                cloudflare_account,
                cloudflare_token,
                cloudflare_model,
                provider_prompt,
                references,
            )
            persisted = await _persist_generated_bytes(body, content_type, storage_prefix)
            return {
                "ok": True,
                "provider": "cloudflare",
                "model": cloudflare_model,
                "prompt": prompt,
                "provider_image_url": "",
                **persisted,
                "reference_images": references[:1],
                "fallback": bool(failures),
                "prompt_translated": provider_prompt != prompt,
            }
        except Exception as exc:
            failures.append(f"Workers AI：{type(exc).__name__}")
            status = int(getattr(exc, "code", 0) or 0)
            diagnostic = (
                "image generation provider=cloudflare failed model=%s reference_count=%s error_type=%s http_status=%s"
                % (cloudflare_model, len(references), type(exc).__name__, status)
            )
            logging.warning(diagnostic)
            print(diagnostic, flush=True)
        return None

    requested_order = [
        item.strip().lower()
        for item in str(env.get("IMAGE_PROVIDER_ORDER") or "").split(",")
        if item.strip().lower() in {"hunyuan", "cloudflare"}
    ]
    provider_order = list(dict.fromkeys([*requested_order, "hunyuan", "cloudflare"]))
    for provider_name in provider_order:
        result = await (try_cloudflare() if provider_name == "cloudflare" else try_hunyuan())
        if result is not None:
            diagnostic = (
                "image generation provider=%s model=%s reference_count=%s fallback=%s prompt_translated=%s"
                % (
                    result.get("provider") or "none",
                    result.get("model") or "none",
                    len(references),
                    bool(result.get("fallback")),
                    bool(result.get("prompt_translated")),
                )
            )
            logging.info(diagnostic)
            print(diagnostic, flush=True)
            return result

    if not failures:
        return {
            "ok": False,
            "error": "未配置生图服务；请配置 HUNYUAN_IMAGE_API_KEY，或 Cloudflare Account ID 与 Workers AI Token",
        }
    return {"ok": False, "error": f"生成图片失败（{'；'.join(failures)}）"}
