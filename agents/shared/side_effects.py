"""Side-effect providers used after an explicit workspace confirmation."""

from __future__ import annotations

import asyncio
import base64
import json
import shutil
import urllib.parse
import urllib.request
import uuid
from typing import Any


def _meeting_result(data: dict[str, Any], subject: str, start_iso: str) -> dict[str, Any]:
    nested = data.get("result") if isinstance(data.get("result"), dict) else data
    if not bool(nested.get("ok", data.get("ok", False))):
        return {"ok": False, "error": str(nested.get("error") or data.get("error") or "会议桥创建失败")}
    return {
        "ok": True,
        "meeting_id": nested.get("meeting_id") or nested.get("meetingId") or "",
        "meeting_code": nested.get("meeting_code") or nested.get("meetingCode") or "",
        "join_url": nested.get("join_url") or nested.get("joinUrl") or "",
        "subject": subject,
        "start_time": start_iso,
    }


def _post_meeting_bridge(url: str, token: str, subject: str, start_iso: str, end_iso: str) -> dict[str, Any]:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" and parsed.hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("MEETING_BRIDGE_URL 必须使用 HTTPS")
    request = urllib.request.Request(
        url,
        data=json.dumps({"subject": subject, "start_time": start_iso, "end_time": end_iso}).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        body = response.read(1024 * 1024)
    return _meeting_result(json.loads(body.decode("utf-8")), subject, start_iso)


async def create_tencent_meeting(env: dict[str, Any], subject: str, start_iso: str, end_iso: str) -> dict[str, Any]:
    """Create a meeting with the same tmeet CLI flow as the legacy FastAPI app.

    The runtime never installs packages and never starts an interactive login.
    It only consumes an existing tmeet executable and its existing local login.
    """
    bridge_url = str(env.get("MEETING_BRIDGE_URL") or "").strip()
    bridge_token = str(env.get("MEETING_BRIDGE_TOKEN") or "").strip()
    if bridge_url:
        if not bridge_token:
            return {"ok": False, "error": "已配置会议桥地址，但缺少 MEETING_BRIDGE_TOKEN"}
        try:
            return await asyncio.to_thread(
                _post_meeting_bridge, bridge_url, bridge_token, subject, start_iso, end_iso,
            )
        except Exception as exc:
            return {"ok": False, "error": f"腾讯会议桥调用失败：{exc}"}

    executable = shutil.which("tmeet")
    if not executable:
        return {
            "ok": False,
            "error": "EdgeOne 无持久系统 Keychain，不能直接运行已登录的 tmeet；请配置 MEETING_BRIDGE_URL 和 MEETING_BRIDGE_TOKEN",
        }
    command = [
        executable, "meeting", "create", "--subject", subject,
        "--start", start_iso, "--end", end_iso, "--format", "json",
    ]
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=20)
    except asyncio.TimeoutError:
        return {"ok": False, "error": "tmeet 创建会议超时，外部状态未知，请勿立即重复创建"}
    except Exception as exc:
        return {"ok": False, "error": f"无法运行 tmeet：{exc}"}
    output = stdout.decode("utf-8", errors="replace").strip()
    error = stderr.decode("utf-8", errors="replace").strip()
    if process.returncode != 0:
        combined = f"{output} {error}".lower()
        if "login" in combined or "auth" in combined or "not logged" in combined:
            return {"ok": False, "error": "tmeet 当前没有可用登录态，请先在部署环境完成 tmeet 登录"}
        return {"ok": False, "error": f"创建会议失败：{error or output or '未知错误'}"}
    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        return {"ok": False, "error": "无法解析 tmeet 返回结果"}
    return _meeting_result({"ok": True, **data}, subject, start_iso)


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
