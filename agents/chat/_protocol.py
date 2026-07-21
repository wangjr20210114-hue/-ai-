"""User-visible protocol guards with no LangGraph/runtime dependencies."""

from __future__ import annotations

import re
import json
import uuid
from html import unescape
from typing import Any


_WIRE_PATTERN = re.compile(r"DSML|<[^>]*(?:tool_calls|invoke|parameter)[^>]*>", re.I)
_PROVIDER_ERROR = re.compile(r"provider|model id|invalid_request|api[_ -]?key|gateway|status code:\s*[45]\d\d|error code:\s*[45]\d\d", re.I)
_INTERNAL_ERROR = re.compile(r"\brole\b|keyerror|traceback|stack|agent_run_error|internal server error", re.I)
_QUOTA_ERROR = re.compile(r"quota|rate[_ -]?limit|too many requests|\b429\b", re.I)


def public_content(content: str) -> str:
    """Remove provider/tool wire syntax from user-visible assistant content."""
    text = str(content or "")
    if _WIRE_PATTERN.search(text):
        return ""
    return text


def public_error(error: Any) -> str:
    """Map provider/runtime details to a stable, actionable user message."""
    text = str(error or "").strip()
    if _QUOTA_ERROR.search(text):
        return "模型服务当前繁忙或配额不足，请稍后重试。"
    if _PROVIDER_ERROR.search(text):
        return "模型服务配置异常，本次失败不会保存为 AI 回答；请检查 Preview 的模型配置后重试。"
    if not text or _INTERNAL_ERROR.search(text):
        return "消息服务暂时异常，本次失败不会保存为 AI 回答，请稍后重试。"
    return text if len(text) <= 180 else f"{text[:180]}…"


def action_fallback_content(actions: list[dict[str, Any]]) -> str:
    """Keep a durable UI action visible when a provider returns no final prose."""
    kinds = {
        str(((item.get("action") if isinstance(item.get("action"), dict) else item) or {}).get("kind") or "")
        for item in actions
        if isinstance(item, dict)
    }
    if "map_recommendation" in kinds:
        return "地点已经过真实地点服务核实。请点击下方按钮显示地点；未核实的地点不会进入地图。"
    if "meeting_create" in kinds:
        return "腾讯会议确认卡已准备好，请在卡片中补齐并核对条件后继续。"
    if "calendar_changes" in kinds:
        return "日程变更确认卡已准备好，请核对后再确认。"
    if "image_generate" in kinds:
        return "图片任务已准备好，可在下方图片工坊查看结果。"
    return "操作卡已准备好，请核对下方内容后继续。"


class PublicStreamFilter:
    """Quarantine a short suffix while streaming and suppress provider wire text.

    Tool-call responses occasionally start with a short prose preamble before
    emitting DSML. Holding a bounded suffix prevents that common case from ever
    reaching the UI; ``reset_required`` lets the transport retract an earlier
    safe prefix if a late protocol marker still appears.
    """

    def __init__(self, hold_chars: int = 48) -> None:
        self.hold_chars = max(16, int(hold_chars))
        self.buffer = ""
        self.blocked = False
        self.emitted = False

    def push(self, chunk: str) -> tuple[str, bool]:
        if self.blocked or not chunk:
            return "", False
        self.buffer += str(chunk)
        if _WIRE_PATTERN.search(self.buffer):
            self.blocked = True
            self.buffer = ""
            return "", self.emitted
        safe_length = len(self.buffer) - self.hold_chars
        if safe_length <= 0:
            return "", False
        output = self.buffer[:safe_length]
        self.buffer = self.buffer[safe_length:]
        self.emitted = self.emitted or bool(output)
        return output, False

    def finish(self) -> tuple[str, bool]:
        if self.blocked or not self.buffer:
            return "", self.emitted and self.blocked
        output = public_content(self.buffer)
        if not output:
            self.blocked = True
            self.buffer = ""
            return "", self.emitted
        self.buffer = ""
        self.emitted = self.emitted or bool(output)
        return output, False

    def reset(self) -> bool:
        reset_required = self.emitted
        self.buffer = ""
        self.blocked = False
        self.emitted = False
        return reset_required


def _argument_value(raw: str) -> Any:
    value = unescape(re.sub(r"<[^>]+>", "", raw)).strip()
    if not value:
        return ""
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    if value.lower() == "null":
        return None
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    if re.fullmatch(r"-?\d+\.\d+", value):
        return float(value)
    if value[:1] in {'[', '{', '"'}:
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            pass
    return value


def dsml_tool_calls(content: str, allowed_names: set[str] | None = None) -> list[dict[str, Any]]:
    """Normalize Tencent/DeepSeek DSML content into LangChain tool calls.

    Some gateway/model combinations return the provider's tool wire format in
    `content` instead of the OpenAI `tool_calls` field. Treat it as transport,
    never as assistant prose.
    """
    text = str(content or "")
    if "DSML" not in text:
        return []
    calls = []
    invoke_pattern = re.compile(
        r'<[^>]*invoke\s+name="([^"]+)"[^>]*>([\s\S]*?)</[^>]*invoke\s*>',
        re.I,
    )
    parameter_pattern = re.compile(
        r'<[^>]*parameter\s+name="([^"]+)"[^>]*>([\s\S]*?)</[^>]*parameter\s*>',
        re.I,
    )
    for match in invoke_pattern.finditer(text):
        name = match.group(1).strip()
        if allowed_names is not None and name not in allowed_names:
            continue
        args = {key: _argument_value(value) for key, value in parameter_pattern.findall(match.group(2))}
        calls.append({"name": name, "args": args, "id": f"dsml-{uuid.uuid4().hex}", "type": "tool_call"})
    return calls
