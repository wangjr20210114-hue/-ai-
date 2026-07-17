"""Loopback-only setup endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from security.local_auth import is_loopback_host, origin_is_allowed

router = APIRouter(prefix="/api/setup", tags=["setup"])


@router.get("/access-token")
async def get_local_access_token(request: Request) -> dict:
    client_host = request.client.host if request.client else None
    if not is_loopback_host(client_host):
        raise HTTPException(status_code=403, detail="setup endpoint is loopback-only")
    if not origin_is_allowed(request.headers.get("origin")):
        raise HTTPException(status_code=403, detail="origin is not allowed")
    service = request.app.state.local_access_token_service
    return {
        "token": service.token,
        "header": "X-Agent-Token",
        "websocket_protocol_prefix": "agent-token.",
    }
