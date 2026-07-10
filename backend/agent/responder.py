"""Transport response helpers for Agent output."""
from __future__ import annotations

from typing import Any

from models.schemas import WSMessage
from skills.base_skill import SkillResult


class AgentResponder:
    async def send_skill_result(self, websocket: Any, result: SkillResult, *, run_id: str = "") -> None:
        payload = {
            "intent": result.intent,
            "mode": result.mode,
            "content": result.content,
            "icon": result.icon,
            "action_label": result.action_label,
            "params": result.params,
            "data": {**result.data, **({"run_id": run_id} if run_id else {})},
            "follow_ups": result.data.get("follow_ups", []),
        }
        await websocket.send_text(WSMessage(type="suggestion", payload=payload).model_dump_json())

    async def send_error(self, websocket: Any, message: str, *, run_id: str = "") -> None:
        await websocket.send_text(
            WSMessage(
                type="error",
                payload={"message": message, "run_id": run_id},
            ).model_dump_json()
        )