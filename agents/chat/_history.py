"""Bounded chat-history helpers with no runtime-framework dependency."""


def bounded_history(messages, limit: int = 32):
    """Keep a complete recent turn window without splitting tool-call pairs."""
    if len(messages) <= limit:
        return list(messages)
    start = max(0, len(messages) - limit)
    while start < len(messages) - 1:
        kind = getattr(messages[start], "type", "")
        if kind in {"human", "user"}:
            break
        start += 1
    return list(messages[start:])


def recoverable_history(messages):
    """Drop only incomplete tool turns left by a failed provider call.

    A failed request can checkpoint a human message plus an AI tool-call without
    its matching tool result/final answer. Feeding that orphan back into the next
    turn makes some gateways repeat the same failure forever. Completed turns are
    preserved byte-for-byte.
    """
    output = []
    segment = []

    def flush(items):
        if not items:
            return
        has_tool_call = any(
            getattr(item, "type", "") == "ai" and getattr(item, "tool_calls", None)
            for item in items
        )
        if not has_tool_call:
            output.extend(items)
            return
        tool_indexes = [index for index, item in enumerate(items) if getattr(item, "type", "") == "tool"]
        final_ai = any(
            getattr(item, "type", "") == "ai" and not getattr(item, "tool_calls", None)
            for item in items[(tool_indexes[-1] + 1) if tool_indexes else 0:]
        )
        output.extend(items if tool_indexes and final_ai else [items[0]])

    for item in messages:
        if getattr(item, "type", "") in {"human", "user"} and segment:
            flush(segment)
            segment = []
        segment.append(item)
    flush(segment)
    return output
