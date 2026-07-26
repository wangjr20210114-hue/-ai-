"""User-visible protocol guards with no LangGraph/runtime dependencies."""

from __future__ import annotations

import re
import json
import uuid
from html import unescape
from typing import Any


_WIRE_PATTERN = re.compile(r"DSML|<[^>]*(?:tool_calls|invoke|parameter)[^>]*>", re.I)
_PROVIDER_ERROR = re.compile(r"provider|model id|api[_ -]?key|gateway", re.I)
_REQUEST_ERROR = re.compile(r"invalid_request|status code:\s*[45]\d\d|error code:\s*[45]\d\d", re.I)
_INTERNAL_ERROR = re.compile(r"\brole\b|keyerror|traceback|stack|agent_run_error|internal server error", re.I)
_QUOTA_ERROR = re.compile(r"quota|rate[_ -]?limit|too many requests|\b429\b", re.I)


def _strip_leading_observation(text: str) -> tuple[str, bool]:
    """Remove an echoed internal observation while retaining following prose.

    Completed tool results are intentionally flattened into a JSON observation
    for the next model call. A provider may occasionally repeat that object
    verbatim before its user-facing answer. The marker occurs within the stream
    quarantine window, so we can wait for the complete JSON object and remove
    only it without suppressing the actual answer that follows.
    """
    leading = str(text or "").lstrip()
    marker = '"floris_observation"'
    if not leading.startswith("{") or marker not in leading[:160]:
        return str(text or ""), False
    try:
        payload, end = json.JSONDecoder().raw_decode(leading)
    except json.JSONDecodeError:
        return "", True
    if not isinstance(payload, dict) or "floris_observation" not in payload:
        return str(text or ""), False
    return leading[end:].lstrip("\r\n "), False


def public_content(content: str) -> str:
    """Remove provider/tool wire syntax from user-visible assistant content."""
    text = str(content or "")
    text, incomplete_observation = _strip_leading_observation(text)
    if incomplete_observation:
        return ""
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
    if _REQUEST_ERROR.search(text):
        return "模型服务暂时未能处理本轮上下文，本次失败不会保存为 AI 回答；请点击重试。"
    if not text or _INTERNAL_ERROR.search(text):
        return "消息服务暂时异常，本次失败不会保存为 AI 回答，请稍后重试。"
    return text if len(text) <= 180 else f"{text[:180]}…"


def checkpoint_recovery_needed(
    emitted_parts: list[str],
    *,
    stream_finished: bool,
) -> bool:
    """Recover only after the public filter has flushed and emitted nothing.

    Raw model content is not evidence of a user-visible answer: a model may
    start prose, switch back to a tool call, and have that prefix retracted.
    Waiting until ``PublicStreamFilter.finish`` avoids duplicating legitimate
    short buffered answers while still recovering the graph's durable terminal
    fallback after such a reset.
    """
    return bool(stream_finished) and not emitted_parts


def action_fallback_content(actions: list[dict[str, Any]]) -> str:
    """Keep a durable UI action visible when a provider returns no final prose."""
    kinds = {
        str(((item.get("action") if isinstance(item.get("action"), dict) else item) or {}).get("kind") or "")
        for item in actions
        if isinstance(item, dict)
    }
    if "meeting_create" in kinds:
        return "腾讯会议确认卡已准备好，请在卡片中补齐并核对条件后继续。"
    if "calendar_changes" in kinds:
        return "日程变更确认卡已准备好，请核对后再确认。"
    if "map_recommendation" in kinds:
        return "地点已经过真实地点服务核实。请点击下方按钮显示地点；未核实的地点不会进入地图。"
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
        cleaned, incomplete_observation = _strip_leading_observation(self.buffer)
        if incomplete_observation:
            return "", False
        self.buffer = cleaned
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


class StreamDeltaNormalizer:
    """Turn provider deltas or cumulative messages into one monotonic stream."""

    def __init__(self) -> None:
        self.text = ""

    def push(self, chunk: str) -> str:
        value = str(chunk or "")
        if not value:
            return ""
        if self.text and value.startswith(self.text) and len(value) > len(self.text):
            delta = value[len(self.text):]
            self.text = value
            return delta
        if len(value) >= 16 and (value == self.text or self.text.endswith(value)):
            return ""
        self.text += value
        return value

    def reset(self) -> None:
        self.text = ""


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
