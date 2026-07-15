"""Persistent HTTPS bridge for the official Tencent Meeting CLI.

Run this on the same durable machine where an administrator completed
`tmeet auth login`. Put it behind HTTPS and never copy ~/.tmeet or Keychain
credentials into EdgeOne or source control.
"""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import shutil

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Tencent Meeting tmeet Bridge", docs_url=None, redoc_url=None)


class MeetingRequest(BaseModel):
    subject: str
    start_time: str
    end_time: str


def require_token(authorization: str) -> None:
    expected = os.getenv("MEETING_BRIDGE_TOKEN", "")
    supplied = authorization.removeprefix("Bearer ").strip()
    if not expected or not secrets.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="unauthorized")


@app.get("/health")
async def health() -> dict:
    return {"ok": True, "tmeet_installed": bool(shutil.which("tmeet"))}


@app.post("/v1/meetings")
async def create_meeting(body: MeetingRequest, authorization: str = Header(default="")) -> dict:
    require_token(authorization)
    executable = shutil.which("tmeet")
    if not executable:
        return {"ok": False, "error": "会议桥未安装 tmeet"}
    process = await asyncio.create_subprocess_exec(
        executable, "meeting", "create",
        "--subject", body.subject,
        "--start", body.start_time,
        "--end", body.end_time,
        "--format", "json",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=25)
    except asyncio.TimeoutError:
        process.kill()
        return {"ok": False, "error": "tmeet 创建超时，外部状态未知，请勿立即重试"}
    output = stdout.decode("utf-8", errors="replace").strip()
    error = stderr.decode("utf-8", errors="replace").strip()
    if process.returncode != 0:
        return {"ok": False, "error": error or output or "tmeet 创建失败"}
    try:
        result = json.loads(output)
    except json.JSONDecodeError:
        return {"ok": False, "error": "无法解析 tmeet 返回结果"}
    return {"ok": True, **result}
