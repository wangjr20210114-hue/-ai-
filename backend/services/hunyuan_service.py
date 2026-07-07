"""大模型 API 统一封装（OpenAI 兼容接口）。

按 settings.llm_provider 自动切换混元 / DeepSeek。
封装：对话补全(ChatCompletions)、生图(TextToImage)。
未配置 API 时抛出明确提示，不返回任何模拟数据。
"""
from __future__ import annotations

import json
import re
from typing import Any

import httpx

from config import settings
from models.schemas import CostRecord
from scenarios.scenario_type import ScenarioType


def _extract_json(text: str) -> dict[str, Any]:
    """从 LLM 输出中稳健提取 JSON。"""
    text = text.strip()
    # 去除 ```json ``` 包裹
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
    return {"_raw": text}


class ApiNotConfiguredError(RuntimeError):
    """API 未接入异常，携带用户可见的提示信息。"""


class HunyuanService:
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(timeout=60.0)

    async def close(self) -> None:
        await self._client.aclose()

    async def chat_json(
        self, messages: list[dict], session_id: str, scenario: ScenarioType, max_tokens: int = 400
    ) -> tuple[dict[str, Any], CostRecord]:
        """调用对话接口并解析为 JSON，同时返回成本记录。"""
        if not settings.llm_ready:
            raise ApiNotConfiguredError("系统需要申请大模型 API，暂未接入")

        resp = await self._client.post(
            f"{settings.llm_base_url}/chat/completions",
            headers={"Authorization": f"Bearer {settings.llm_api_key}"},
            json={
                "model": settings.llm_model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": 0.6,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        pt, ct = usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
        tt = usage.get("total_tokens", pt + ct)
        cost = CostRecord(
            session_id=session_id, scenario=scenario,
            prompt_tokens=pt, completion_tokens=ct, total_tokens=tt,
            cost_yuan=round(tt / 1000 * settings.llm_price_per_1k, 4),
        )
        return _extract_json(content), cost

    async def chat_text(
        self, messages: list[dict], session_id: str, scenario: ScenarioType, max_tokens: int = 700
    ) -> tuple[str, CostRecord]:
        """普通对话补全，返回纯文本回复与成本记录。"""
        if not settings.llm_ready:
            raise ApiNotConfiguredError("系统需要申请大模型 API，暂未接入")

        resp = await self._client.post(
            f"{settings.llm_base_url}/chat/completions",
            headers={"Authorization": f"Bearer {settings.llm_api_key}"},
            json={
                "model": settings.llm_model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": 0.7,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        pt, ct = usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
        tt = usage.get("total_tokens", pt + ct)
        cost = CostRecord(
            session_id=session_id, scenario=scenario,
            prompt_tokens=pt, completion_tokens=ct, total_tokens=tt,
            cost_yuan=round(tt / 1000 * settings.llm_price_per_1k, 4),
        )
        return content.strip(), cost

    async def chat_markdown(
        self, messages: list[dict], session_id: str, scenario: ScenarioType, max_tokens: int = 3000
    ) -> tuple[str, CostRecord]:
        """对话补全，返回纯 Markdown 文本（不做 JSON 提取），用于旅游行程等长文本输出。"""
        if not settings.llm_ready:
            raise ApiNotConfiguredError("系统需要申请大模型 API，暂未接入")

        resp = await self._client.post(
            f"{settings.llm_base_url}/chat/completions",
            headers={"Authorization": f"Bearer {settings.llm_api_key}"},
            json={
                "model": settings.llm_model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": 0.7,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        pt, ct = usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
        tt = usage.get("total_tokens", pt + ct)
        cost = CostRecord(
            session_id=session_id, scenario=scenario,
            prompt_tokens=pt, completion_tokens=ct, total_tokens=tt,
            cost_yuan=round(tt / 1000 * settings.llm_price_per_1k, 4),
        )
        return content.strip(), cost


hunyuan_service = HunyuanService()
