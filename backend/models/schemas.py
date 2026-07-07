"""Pydantic 数据模型。"""
from __future__ import annotations

import time
import uuid
from typing import Any

from pydantic import BaseModel, Field

from scenarios.scenario_type import ScenarioType


def _uid() -> str:
    return uuid.uuid4().hex[:12]


def _now() -> float:
    return time.time()


# ============ WebSocket 消息 ============
class WSMessage(BaseModel):
    type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    ts: float = Field(default_factory=_now)


# ============ Token 成本追踪 ============
class CostRecord(BaseModel):
    session_id: str
    scenario: ScenarioType
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_yuan: float = 0.0
    ts: float = Field(default_factory=_now)


# ============ 旅游计划 ============
class TravelPlan(BaseModel):
    id: str = Field(default_factory=_uid)
    session_id: str
    title: str = ""
    departure: str = ""
    destination: str = ""
    days: int = 3
    travel_style: str = ""
    scenery_preference: str = ""
    budget: str = ""
    extra_notes: str = ""
    markdown_content: str = ""
    baike_info: dict[str, Any] = Field(default_factory=dict)
    created_at: float = Field(default_factory=_now)
    updated_at: float = Field(default_factory=_now)


class GeneratePlanRequest(BaseModel):
    session_id: str
    departure: str
    destination: str
    days: int = 0
    start_date: str = ""
    end_date: str = ""
    travel_style: str = "深度游"
    scenery_preference: str = "人文景观"
    budget: str = ""
    extra_notes: str = ""


class SavePlanRequest(BaseModel):
    session_id: str
    plan: dict[str, Any]


# ============ 通用日程 ============
SCHEDULE_CATEGORIES = {
    "travel": "旅游",
    "meeting": "会议",
    "dining": "聚餐",
    "remind": "提醒",
    "task": "任务",
    "other": "其他",
}


class ScheduleItem(BaseModel):
    id: str = Field(default_factory=_uid)
    session_id: str
    title: str = ""
    category: str = "other"
    start_time: float = 0
    duration_minutes: int = 0
    duration_days: int = 0
    location: str = ""
    description: str = ""
    markdown_content: str = ""
    extra: dict[str, Any] = Field(default_factory=dict)
    done: bool = False
    created_at: float = Field(default_factory=_now)
    updated_at: float = Field(default_factory=_now)


class SaveScheduleRequest(BaseModel):
    session_id: str
    schedule: dict[str, Any]


# ============ 会议 ============
class MeetingCreateRequest(BaseModel):
    session_id: str
    message: str  # 用户原始消息，如"明天下午2点开个需求评审会"
