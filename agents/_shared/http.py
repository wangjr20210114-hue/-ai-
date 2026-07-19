"""HTTP response helpers for the EdgeOne Python Agent runtime."""

from __future__ import annotations

from typing import Any


def response(body: Any, status: int = 200, headers: dict[str, str] | None = None) -> dict[str, Any]:
    """Return the runtime's documented response envelope.

    Python tuples are ordinary JSON values to the Makers runtime and therefore
    become an HTTP 200 array.  Every non-default status must use this envelope.
    """

    value: dict[str, Any] = {"status_code": int(status), "body": body}
    if headers:
        value["headers"] = {str(key): str(item) for key, item in headers.items()}
    return value


def error(message: str, status: int = 400, *, code: str = "") -> dict[str, Any]:
    body = {"error": str(message or "请求失败")}
    if code:
        body["code"] = str(code)
    return response(body, status)
