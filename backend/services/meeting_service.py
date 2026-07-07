"""腾讯会议服务：通过 tencentmeeting-cli (tmeet) 创建会议。

前置条件：
  1. npm i -g @tencentcloud/tmeet（未安装时自动执行）
  2. tmeet auth login（浏览器扫码授权一次，凭证 AES-256 加密存储）
     ← 这步是交互式的，无法自动完成

Python 通过 subprocess 调用 tmeet 命令行，解析 JSON 输出。
"""
from __future__ import annotations

import asyncio
import json
import shutil
from typing import Any


class MeetingService:
    """封装 tmeet CLI 调用。"""

    def _check_installed(self) -> bool:
        return shutil.which("tmeet") is not None

    async def _ensure_installed(self) -> dict[str, Any] | None:
        """确保 tmeet 已安装。未安装时自动执行 npm i -g。

        Returns:
            None 表示已安装或安装成功；dict 表示安装失败的错误信息。
        """
        if self._check_installed():
            return None

        # 检查 npm 是否可用
        if not shutil.which("npm"):
            return {
                "ok": False,
                "error": "npm 未安装，请先安装 Node.js：https://nodejs.org/",
            }

        # 自动安装
        print("[meeting] tmeet 未安装，正在自动执行 npm i -g @tencentcloud/tmeet ...")
        result = await self._run(
            ["npm", "i", "-g", "@tencentcloud/tmeet"],
            timeout=120,
        )

        if result["returncode"] != 0:
            stderr = result["stderr"].strip()
            return {
                "ok": False,
                "error": f"tmeet 自动安装失败：{stderr or '未知错误'}。请手动运行: npm i -g @tencentcloud/tmeet",
            }

        # 安装后再次检查
        if not self._check_installed():
            # 可能 PATH 未刷新，尝试用 npx
            npx_check = await self._run(["npx", "tmeet", "--version"], timeout=15)
            if npx_check["returncode"] != 0:
                return {
                    "ok": False,
                    "error": "tmeet 安装完成但无法找到命令。请重新打开终端后重试，或手动运行: npm i -g @tencentcloud/tmeet",
                }

        print("[meeting] tmeet 安装成功")
        return None

    async def check_auth(self) -> dict[str, Any]:
        """检查 tmeet 是否已安装且已授权。"""
        # 1. 自动安装
        install_err = await self._ensure_installed()
        if install_err:
            return install_err

        # 2. 检查授权
        result = await self._run(["tmeet", "auth", "status"], timeout=10)
        stdout = result["stdout"].strip().lower()
        stderr = result["stderr"].strip().lower()

        # 合并 stdout + stderr 判断（有些版本输出在 stderr）
        combined = stdout + " " + stderr

        # 未登录的典型输出："Not logged in. Please use 'tmeet auth login'..."
        if "not logged in" in combined or "login" in combined and "logged_in" not in combined:
            return {
                "ok": False,
                "error": "tmeet 已安装，但尚未授权。请在终端运行一次: tmeet auth login（浏览器扫码授权）",
                "need_auth": True,
            }

        # 已登录的情况
        if result["returncode"] == 0:
            # 尝试解析 JSON（某些版本可能支持 --format json）
            try:
                data = json.loads(result["stdout"])
                if data.get("logged_in") or data.get("status") == "logged_in":
                    return {"ok": True}
            except (json.JSONDecodeError, ValueError):
                pass
            # 非 JSON 但没有 "not logged in" 字样，假设已授权
            if combined and "not logged" not in combined:
                return {"ok": True}

        return {
            "ok": False,
            "error": "tmeet 已安装，但尚未授权。请在终端运行一次: tmeet auth login（浏览器扫码授权）",
            "need_auth": True,
        }

    async def create_meeting(
        self, subject: str, start_iso: str, end_iso: str
    ) -> dict[str, Any]:
        """创建腾讯会议。

        Args:
            subject: 会议主题
            start_iso: 开始时间 ISO 8601（如 2026-07-10T14:00+08:00）
            end_iso: 结束时间 ISO 8601

        Returns:
            {"ok": True, "meeting_id": ..., "join_url": ...} 或 {"ok": False, "error": ...}
        """
        # 1. 自动安装
        install_err = await self._ensure_installed()
        if install_err:
            return install_err

        # 2. 创建会议
        cmd = [
            "tmeet", "meeting", "create",
            "--subject", subject,
            "--start", start_iso,
            "--end", end_iso,
            "--format", "json",
        ]
        result = await self._run(cmd, timeout=15)

        if result["returncode"] != 0:
            stderr = result["stderr"].strip()
            combined = (stderr + " " + result["stdout"].strip()).lower()
            if "auth" in combined or "login" in combined or "not logged" in combined:
                return {
                    "ok": False,
                    "error": "tmeet 已安装，但尚未授权。请在终端运行一次: tmeet auth login（浏览器扫码授权）",
                    "need_auth": True,
                }
            return {"ok": False, "error": f"创建会议失败: {stderr or '未知错误'}"}

        try:
            data = json.loads(result["stdout"])
        except json.JSONDecodeError:
            return {"ok": False, "error": "无法解析 tmeet 输出"}

        # tmeet 输出格式兼容
        meeting_id = data.get("meeting_id") or data.get("meetingId") or ""
        meeting_code = data.get("meeting_code") or data.get("meetingCode") or ""
        join_url = data.get("join_url") or data.get("joinUrl") or ""

        return {
            "ok": True,
            "meeting_id": meeting_id,
            "meeting_code": meeting_code,
            "join_url": join_url,
            "subject": subject,
            "start_time": start_iso,
        }

    async def _run(self, cmd: list[str], timeout: int = 10) -> dict[str, str]:
        """异步运行子进程。"""
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return {
            "returncode": proc.returncode,
            "stdout": stdout.decode("utf-8", errors="replace"),
            "stderr": stderr.decode("utf-8", errors="replace"),
        }


meeting_service = MeetingService()
