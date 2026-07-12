"""Tencent Meeting CLI adapter.

Installation and authentication are explicit setup operations.  Normal Agent
execution never installs global packages or opens an interactive login flow.
"""
from __future__ import annotations

import asyncio
import json
import shutil
from typing import Any


class MeetingService:
    def _check_installed(self) -> bool:
        return shutil.which("tmeet") is not None

    async def install_cli(self) -> dict[str, Any]:
        """Explicit setup action used only by the Setup API/UI."""
        if self._check_installed():
            return {"ok": True, "installed": True}
        if not shutil.which("npm"):
            return {"ok": False, "error": "npm 未安装，请先安装 Node.js", "setup_required": True}
        result = await self._run(["npm", "i", "-g", "@tencentcloud/tmeet"], timeout=120)
        if result["returncode"] != 0:
            return {
                "ok": False,
                "error": f"tmeet 安装失败：{result['stderr'].strip() or '未知错误'}",
                "setup_required": True,
            }
        return {"ok": self._check_installed(), "installed": self._check_installed()}

    async def check_auth(self) -> dict[str, Any]:
        if not self._check_installed():
            return {
                "ok": False,
                "error": "tmeet 未安装，请在设置页显式安装",
                "setup_required": True,
            }
        result = await self._run(["tmeet", "auth", "status"], timeout=10)
        combined = (result["stdout"] + " " + result["stderr"]).strip().lower()
        if "not logged in" in combined or ("login" in combined and "logged_in" not in combined):
            return {
                "ok": False,
                "error": "tmeet 尚未授权，请在终端执行 tmeet auth login",
                "need_auth": True,
            }
        if result["returncode"] == 0:
            try:
                data = json.loads(result["stdout"])
                if data.get("logged_in") or data.get("status") == "logged_in":
                    return {"ok": True}
            except (json.JSONDecodeError, ValueError):
                pass
            if combined and "not logged" not in combined:
                return {"ok": True}
        return {"ok": False, "error": "无法确认 tmeet 授权状态", "need_auth": True}

    async def create_meeting(self, subject: str, start_iso: str, end_iso: str) -> dict[str, Any]:
        if not self._check_installed():
            return {
                "ok": False,
                "error": "tmeet 未安装，请先在设置页完成安装和授权",
                "setup_required": True,
            }
        result = await self._run(
            [
                "tmeet",
                "meeting",
                "create",
                "--subject",
                subject,
                "--start",
                start_iso,
                "--end",
                end_iso,
                "--format",
                "json",
            ],
            timeout=20,
        )
        if result["returncode"] != 0:
            combined = (result["stderr"] + " " + result["stdout"]).strip()
            lower = combined.lower()
            if "auth" in lower or "login" in lower or "not logged" in lower:
                return {"ok": False, "error": "tmeet 尚未授权，请执行 tmeet auth login", "need_auth": True}
            return {"ok": False, "error": f"创建会议失败：{combined[:500] or '未知错误'}"}
        try:
            data = json.loads(result["stdout"])
        except json.JSONDecodeError:
            return {"ok": False, "error": "无法解析 tmeet 输出"}
        return {
            "ok": True,
            "meeting_id": data.get("meeting_id") or data.get("meetingId") or "",
            "meeting_code": data.get("meeting_code") or data.get("meetingCode") or "",
            "join_url": data.get("join_url") or data.get("joinUrl") or "",
            "subject": subject,
            "start_time": start_iso,
            "end_time": end_iso,
        }

    async def update_meeting(
        self,
        meeting_id: str,
        *,
        subject: str | None = None,
        start_iso: str | None = None,
        end_iso: str | None = None,
    ) -> dict[str, Any]:
        """Update an existing meeting via tmeet CLI."""
        if not self._check_installed():
            return {"ok": False, "error": "tmeet 未安装", "setup_required": True}
        cmd = ["tmeet", "meeting", "update", "--meeting-id", meeting_id]
        if subject:
            cmd.extend(["--subject", subject])
        if start_iso:
            cmd.extend(["--start", start_iso])
        if end_iso:
            cmd.extend(["--end", end_iso])
        cmd.extend(["--format", "json"])
        result = await self._run(cmd, timeout=20)
        if result["returncode"] != 0:
            combined = (result["stderr"] + " " + result["stdout"]).strip()
            lower = combined.lower()
            if "auth" in lower or "login" in lower or "not logged" in lower:
                return {"ok": False, "error": "tmeet 尚未授权", "need_auth": True}
            return {"ok": False, "error": f"修改会议失败：{combined[:500] or '未知错误'}"}
        try:
            data = json.loads(result["stdout"])
        except json.JSONDecodeError:
            data = {}
        return {
            "ok": True,
            "meeting_id": meeting_id,
            "subject": subject or "",
            "start_time": start_iso or "",
            "end_time": end_iso or "",
            "data": data,
        }

    async def list_meetings(self) -> dict[str, Any]:
        """List pending/in-progress meetings for finding existing meetings to modify."""
        if not self._check_installed():
            return {"ok": False, "error": "tmeet 未安装", "setup_required": True}
        result = await self._run(
            ["tmeet", "meeting", "list", "--format", "json"],
            timeout=15,
        )
        if result["returncode"] != 0:
            return {"ok": False, "error": f"查询会议列表失败：{result['stderr'].strip()[:200]}"}
        try:
            data = json.loads(result["stdout"])
        except json.JSONDecodeError:
            data = []
        return {"ok": True, "meetings": data if isinstance(data, list) else [data]}

    async def _run(self, command: list[str], timeout: int = 10) -> dict[str, Any]:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
        except TimeoutError:
            process.kill()
            await process.communicate()
            return {"returncode": -1, "stdout": "", "stderr": "命令执行超时"}
        return {
            "returncode": process.returncode,
            "stdout": stdout.decode("utf-8", errors="replace"),
            "stderr": stderr.decode("utf-8", errors="replace"),
        }


meeting_service = MeetingService()
