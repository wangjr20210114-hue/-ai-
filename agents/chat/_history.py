"""Bounded chat-history helpers with no runtime-framework dependency."""


def _message_type(message) -> str:
    if isinstance(message, dict):
        return str(message.get("type") or message.get("role") or "")
    return str(getattr(message, "type", "") or getattr(message, "role", "") or "")


def _tool_calls(message) -> list:
    if isinstance(message, dict):
        calls = message.get("tool_calls")
    else:
        calls = getattr(message, "tool_calls", None)
    return list(calls or [])


def _tool_call_id(call) -> str:
    if isinstance(call, dict):
        return str(call.get("id") or "")
    return str(getattr(call, "id", "") or "")


def _tool_result_id(message) -> str:
    if isinstance(message, dict):
        return str(message.get("tool_call_id") or "")
    return str(getattr(message, "tool_call_id", "") or "")


def valid_model_history(messages):
    """Remove incomplete tool-call groups left by an interrupted prior run.

    OpenAI-compatible gateways reject a history containing an orphan tool
    result or an assistant tool call that is not followed by every matching
    result. A stopped browser/network request can leave exactly that checkpoint
    shape. The incomplete group is internal transport state, so dropping it is
    safer than making the user's next deliberate message fail with HTTP 400.
    """
    output = []
    pending_ids: list[str] = []
    group_start = -1

    for message in messages:
        kind = _message_type(message)
        if pending_ids:
            if kind == "tool":
                result_id = _tool_result_id(message)
                if result_id and result_id in pending_ids:
                    output.append(message)
                    pending_ids.remove(result_id)
                    if not pending_ids:
                        group_start = -1
                    continue
            # A non-matching message means the prior tool-call group never
            # completed. Remove the call and any partial results, then process
            # the current message as ordinary history.
            del output[group_start:]
            pending_ids = []
            group_start = -1

        if kind == "tool":
            # A tool result without an immediately preceding pending call is
            # never valid provider input.
            continue

        calls = _tool_calls(message) if kind in {"ai", "assistant"} else []
        if calls:
            ids = [_tool_call_id(call) for call in calls]
            if not ids or any(not call_id for call_id in ids):
                continue
            group_start = len(output)
            pending_ids = ids
        output.append(message)

    if pending_ids and group_start >= 0:
        del output[group_start:]
    return output


def bounded_history(messages, limit: int = 32):
    """Keep a complete recent turn window without splitting tool-call pairs."""
    messages = valid_model_history(messages)
    if len(messages) <= limit:
        return list(messages)
    start = max(0, len(messages) - limit)
    while start < len(messages) - 1:
        kind = _message_type(messages[start])
        if kind in {"human", "user"}:
            break
        start += 1
    return list(messages[start:])
