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
