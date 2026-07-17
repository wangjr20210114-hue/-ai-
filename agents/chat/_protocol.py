"""User-visible protocol guards with no LangGraph/runtime dependencies."""

from __future__ import annotations

import re
import json
import uuid
from html import unescape
from typing import Any


_WIRE_PATTERN = re.compile(r"DSML|<[^>]*(?:tool_calls|invoke|parameter)[^>]*>", re.I)


def public_content(content: str) -> str:
    """Remove provider/tool wire syntax from user-visible assistant content."""
    text = str(content or "")
    if _WIRE_PATTERN.search(text):
        return ""
    return text


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
