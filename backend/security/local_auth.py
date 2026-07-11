"""Persistent local access token and FastAPI authentication boundary."""
from __future__ import annotations

import hmac
import ipaddress
import os
import secrets
from pathlib import Path

from fastapi import Request, WebSocket
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from config import settings

TOKEN_HEADER = "X-Agent-Token"
WEBSOCKET_PROTOCOL_PREFIX = "agent-token."


class LocalAccessTokenService:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path or settings.local_token_path).expanduser().resolve()
        self._token = ""

    def initialize(self) -> str:
        configured = settings.local_access_token.strip()
        if configured:
            self._token = configured
            return self._token
        if self.path.is_file():
            token = self.path.read_text(encoding="utf-8").strip()
            if len(token) >= 32:
                self._token = token
                return token
        self.path.parent.mkdir(parents=True, exist_ok=True)
        token = secrets.token_urlsafe(32)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(token, encoding="utf-8")
        try:
            os.chmod(temporary, 0o600)
        except OSError:
            pass
        temporary.replace(self.path)
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass
        self._token = token
        return token

    @property
    def token(self) -> str:
        if not self._token:
            return self.initialize()
        return self._token

    def verify(self, candidate: str | None) -> bool:
        return bool(candidate) and hmac.compare_digest(candidate, self.token)


def is_loopback_host(host: str | None) -> bool:
    if not host:
        return False
    normalized = host.split("%", 1)[0]
    if normalized in {"localhost", "testclient"}:
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


def origin_is_allowed(origin: str | None) -> bool:
    if not origin:
        return True  # local CLI/native client
    return origin.rstrip("/") in {item.rstrip("/") for item in settings.cors_origin_list}


class LocalTokenMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not settings.local_auth_enabled:
            return await call_next(request)
        path = request.url.path
        if not path.startswith("/api/") or path == "/api/setup/access-token":
            return await call_next(request)
        service: LocalAccessTokenService | None = getattr(
            request.app.state, "local_access_token_service", None
        )
        if service is None or not service.verify(request.headers.get(TOKEN_HEADER)):
            return JSONResponse(
                status_code=401,
                content={"detail": "local access token required"},
                headers={"WWW-Authenticate": "AgentToken"},
            )
        return await call_next(request)


async def require_websocket_token(websocket: WebSocket) -> str | None:
    """Authorize a browser WebSocket and return the subprotocol to echo.

    Browsers cannot set arbitrary handshake headers, so the preferred transport is
    ``Sec-WebSocket-Protocol: agent-token.<token>``. The legacy query parameter is
    accepted for compatibility but the frontend no longer places secrets in URLs.
    """
    if not settings.local_auth_enabled:
        return ""
    service: LocalAccessTokenService | None = getattr(
        websocket.app.state, "local_access_token_service", None
    )
    selected_protocol = ""
    candidate = websocket.headers.get(TOKEN_HEADER) or websocket.query_params.get("token")
    raw_protocols = websocket.headers.get("sec-websocket-protocol", "")
    for protocol in (item.strip() for item in raw_protocols.split(",")):
        if protocol.startswith(WEBSOCKET_PROTOCOL_PREFIX):
            candidate = protocol[len(WEBSOCKET_PROTOCOL_PREFIX):]
            selected_protocol = protocol
            break
    if service is None or not service.verify(candidate):
        await websocket.close(code=1008, reason="local access token required")
        return None
    return selected_protocol
