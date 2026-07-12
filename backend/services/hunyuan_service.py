"""大模型 API 统一封装（OpenAI 兼容接口）。

分工：
- 混元：对话回答（_handle_chat 的流式输出），以及文生图（TokenHub）
- DeepSeek：意图推断、翻译、论文介绍/总结/分析、搜索总结、旅游/会议信息提取

hunyuan_service 中的 chat_json/chat_text/chat_markdown 方法已切换为 DeepSeek，
因为它们用于结构化任务（旅游规划、会议提取），不属于对话回答。
文生图 text_to_image 仍使用混元 TokenHub。
未配置 API 时抛出明确提示，不返回任何模拟数据。
"""
from __future__ import annotations

import asyncio
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


class QuotaExhaustedError(RuntimeError):
    """API 额度用尽异常。触发后应立即终止相关操作并通知前端。"""

    def __init__(self, provider: str, detail: str = ""):
        self.provider = provider
        self.detail = detail
        msg = f"{provider} API 额度已用尽" + (f"：{detail}" if detail else "")
        super().__init__(msg)


def _check_quota_error(status_code: int, body: str, provider: str) -> None:
    """检测 HTTP 响应是否为额度/限流错误，是则抛出 QuotaExhaustedError。"""
    if status_code in (429, 402):
        raise QuotaExhaustedError(provider, f"HTTP {status_code}")
    if status_code in (401, 403):
        # 401/403 可能是 key 失效，也视为额度/授权问题
        # 尝试从 body 提取错误信息
        snippet = body[:200] if body else ""
        raise QuotaExhaustedError(provider, f"HTTP {status_code} {snippet}")
    # 检查 body 中的额度关键词
    if body:
        lower = body.lower()
        keywords = ["quota", "rate limit", "exceeded", "insufficient", "balance",
                     "额度", "余额不足", "限流", "超出限制", "exhausted"]
        if any(kw in lower for kw in keywords):
            raise QuotaExhaustedError(provider, body[:200])


class HunyuanService:
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(timeout=60.0)

    async def close(self) -> None:
        await self._client.aclose()

    # ===== 结构化任务（旅游/会议提取）使用 DeepSeek =====
    # 混元只负责 _handle_chat 的对话回答，其余附加功能交给 DeepSeek

    async def chat_json(
        self, messages: list[dict], session_id: str, scenario: ScenarioType, max_tokens: int = 400
    ) -> tuple[dict[str, Any], CostRecord]:
        """调用 DeepSeek 并解析为 JSON，同时返回成本记录。"""
        if not settings.deepseek_ready:
            raise ApiNotConfiguredError("系统需要配置 DeepSeek API，暂未接入")

        resp = await self._client.post(
            f"{settings.deepseek_base_url}/chat/completions",
            headers={"Authorization": f"Bearer {settings.deepseek_api_key}"},
            json={
                "model": settings.deepseek_model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": 0.6,
            },
        )
        _check_quota_error(resp.status_code, resp.text, "DeepSeek")
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        pt, ct = usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
        tt = usage.get("total_tokens", pt + ct)
        cost = CostRecord(
            session_id=session_id, scenario=scenario,
            prompt_tokens=pt, completion_tokens=ct, total_tokens=tt,
            cost_yuan=round(tt / 1000 * 0.002, 4),
        )
        return _extract_json(content), cost

    async def chat_text(
        self, messages: list[dict], session_id: str, scenario: ScenarioType, max_tokens: int = 700
    ) -> tuple[str, CostRecord]:
        """普通对话补全（DeepSeek），返回纯文本回复与成本记录。"""
        if not settings.deepseek_ready:
            raise ApiNotConfiguredError("系统需要配置 DeepSeek API，暂未接入")

        resp = await self._client.post(
            f"{settings.deepseek_base_url}/chat/completions",
            headers={"Authorization": f"Bearer {settings.deepseek_api_key}"},
            json={
                "model": settings.deepseek_model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": 0.7,
            },
        )
        _check_quota_error(resp.status_code, resp.text, "DeepSeek")
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        pt, ct = usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
        tt = usage.get("total_tokens", pt + ct)
        cost = CostRecord(
            session_id=session_id, scenario=scenario,
            prompt_tokens=pt, completion_tokens=ct, total_tokens=tt,
            cost_yuan=round(tt / 1000 * 0.002, 4),
        )
        return content.strip(), cost

    async def chat_markdown(
        self, messages: list[dict], session_id: str, scenario: ScenarioType, max_tokens: int = 3000
    ) -> tuple[str, CostRecord]:
        """对话补全（DeepSeek），返回纯 Markdown 文本，用于旅游行程等长文本输出。"""
        if not settings.deepseek_ready:
            raise ApiNotConfiguredError("系统需要配置 DeepSeek API，暂未接入")

        resp = await self._client.post(
            f"{settings.deepseek_base_url}/chat/completions",
            headers={"Authorization": f"Bearer {settings.deepseek_api_key}"},
            json={
                "model": settings.deepseek_model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": 0.7,
            },
        )
        _check_quota_error(resp.status_code, resp.text, "DeepSeek")
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        pt, ct = usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
        tt = usage.get("total_tokens", pt + ct)
        cost = CostRecord(
            session_id=session_id, scenario=scenario,
            prompt_tokens=pt, completion_tokens=ct, total_tokens=tt,
            cost_yuan=round(tt / 1000 * 0.002, 4),
        )
        return content.strip(), cost

    @property
    def image_capable(self) -> bool:
        """是否支持文生图。"""
        return bool(settings.hunyuan_image_api_key)

    @property
    def vision_capable(self) -> bool:
        """是否支持视觉理解（多模态）。"""
        return bool(settings.hunyuan_api_key) and not settings.hunyuan_api_key.startswith("sk-your")

    async def describe_image(self, image_url: str, context: str = "") -> str:
        """用视觉模型描述图片内容并判断与查询的相关性。

        返回 JSON 字符串: {"description": "...", "relevant": true/false}
        如果图片与用户查询无关（广告、装饰、UI元素等），relevant=false。
        失败返回空字符串。
        """
        if not self.vision_capable:
            return ""

        try:
            vision_model = settings.hunyuan_vision_model
            if vision_model == "hunyuan-vision":
                vision_model = settings.llm_model

            prompt = (
                '请分析这张图片，返回 JSON：\n'
                '{"description": "用一句话15字以内描述图片内容", '
                '"relevant": true或false}\n\n'
                'relevant 判断规则：\n'
                '- true：图片内容与用户查询相关，能帮助理解或展示相关事物\n'
                '- false：图片是广告、logo、图标、装饰、UI元素、二维码、截图、'
                '占位图、与查询完全无关的图片\n'
            )
            if context:
                prompt += f'用户查询：{context[:80]}'

            resp = await self._client.post(
                f"{settings.hunyuan_base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.hunyuan_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": vision_model,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {"type": "image_url", "image_url": {"url": image_url}},
                            ],
                        }
                    ],
                    "max_tokens": 100,
                    "temperature": 0.2,
                },
                timeout=15,
            )
            if resp.status_code != 200:
                print(f"[vision] describe_image failed: HTTP {resp.status_code}")
                return ""
            data = resp.json()
            content = data["choices"][0]["message"]["content"].strip()
            if "没有看到" in content or "无法" in content or "看不到" in content:
                return ""
            return content
        except Exception as e:
            print(f"[vision] describe_image error: {e}")
            return ""

    async def describe_images(self, image_urls: list[str], context: str = "") -> list[dict[str, str]]:
        """批量并行描述多张图片并过滤无关图片。

        Returns:
            [{"url": "...", "description": "..."}, ...]（只有相关的图片）
        """
        if not image_urls:
            return []

        tasks = [self.describe_image(url, context) for url in image_urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        import json as _json
        output = []
        for url, raw in zip(image_urls, results):
            if not isinstance(raw, str) or not raw:
                continue
            try:
                cleaned = raw.strip().strip("`").strip()
                if cleaned.startswith("json"):
                    cleaned = cleaned[4:].strip()
                parsed = _json.loads(cleaned)
                desc = str(parsed.get("description", "")).strip()
                relevant = parsed.get("relevant", True)
                if desc and relevant:
                    output.append({"url": url, "description": desc})
            except (_json.JSONDecodeError, ValueError, TypeError):
                if raw.strip():
                    output.append({"url": url, "description": raw.strip()[:50]})
        return output

    async def text_to_image(self, prompt: str) -> str:
        """调用混元文生图（TokenHub 极速版），返回图片 URL。"""
        if not self.image_capable:
            raise ApiNotConfiguredError("文生图需要配置 TokenHub API Key（HUNYUAN_IMAGE_API_KEY）")

        resp = await self._client.post(
            f"{settings.hunyuan_image_base_url}/v1/api/image/lite",
            headers={
                "Authorization": f"Bearer {settings.hunyuan_image_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.hunyuan_image_model,
                "prompt": prompt,
                "rsp_img_type": "url",
            },
        )
        _check_quota_error(resp.status_code, resp.text, "混元生图")
        resp.raise_for_status()
        data = resp.json()
        return data["data"][0].get("url", "")


hunyuan_service = HunyuanService()
