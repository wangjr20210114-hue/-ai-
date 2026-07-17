"""Confirmed side-effect providers; not an Agent route."""

from __future__ import annotations

import asyncio
import base64
from datetime import datetime
import hashlib
import hmac
import json
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
    """Create a meeting directly through Tencent Meeting's official server API."""
    try:
        return await asyncio.to_thread(_post_tencent_meeting, env, subject, start_iso, end_iso)
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


async def resolve_image_reference(result: dict[str, Any], prefer_blob: bool = False) -> str:
    """Prefer the persistent Blob copy when editing an older image version."""
    provider_url = str(result.get("provider_image_url") or "")
    if not prefer_blob and provider_url.startswith("https://"):
        return provider_url
    key = str(result.get("storage_key") or "")
    if key.startswith("generated/") or (key.startswith("tenants/") and "/generated/" in key):
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
    if not api_key:
        return {"ok": False, "error": "未配置 HUNYUAN_IMAGE_API_KEY"}
    base_url = str(env.get("HUNYUAN_IMAGE_BASE_URL") or "https://tokenhub.tencentmaas.com").rstrip("/")
    model = str(env.get("HUNYUAN_IMAGE_MODEL") or "hy-image-v3.0")
    storage_prefix = f"tenants/{user_id}/" if str(env.get("AUTH_MODE") or "single_user") == "multi_user" else ""
    references = [str(url).strip() for url in (reference_images or []) if str(url).startswith(("https://", "data:image/"))][:3]
    try:
        endpoint = f"{base_url}/v1/images/generations" if model.lower() == "hy-image-v3.0" or references else f"{base_url}/v1/api/image/lite"
        result = await asyncio.to_thread(
            _post_image, endpoint, api_key, model, prompt, references,
        )
        provider_image_url = str(result["image_url"])
        persisted = await _persist_generated_image(provider_image_url, storage_prefix)
        return {**result, "provider_image_url": provider_image_url, **persisted, "reference_images": references}
    except Exception as exc:
        # Preserve legacy text-to-image availability when an account has not
        # enabled v3 yet. Reference-image edits cannot safely fall back to lite.
        if not references and model.lower() == "hy-image-v3.0":
            try:
                result = await asyncio.to_thread(
                    _post_image, f"{base_url}/v1/api/image/lite", api_key, "hy-image-lite", prompt, [],
                )
                provider_image_url = str(result["image_url"])
                persisted = await _persist_generated_image(provider_image_url, storage_prefix)
                return {**result, "provider_image_url": provider_image_url, **persisted, "reference_images": [], "fallback": True}
            except Exception as fallback_exc:
                return {"ok": False, "error": f"生成图片失败：{fallback_exc}"}
        return {"ok": False, "error": f"生成图片失败：{exc}"}
