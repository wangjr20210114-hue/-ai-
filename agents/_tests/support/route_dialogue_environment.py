import asyncio
import json
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from agents._infrastructure.makers.route_repository import route_cache_key
from agents._application.intelligence.service import normalize_map_preferences
from agents._application.skills.registry import planner_topic_instructions
from agents._infrastructure.providers.tencent_location import plan_verified_route, search_verified_places_bounded
from agents.chat._capability_plan import (
    parse_capability_plan,
)
from agents._infrastructure.skills.builtin_operations import (
    RoutePlanInput,
    _learned_route_preference,
    _place_resolution,
    _place_resolution_with_provider_review,
    _prioritize_clarification_options_for_city,
    _prioritize_provider_candidates_for_city,
    _provider_city_consensus,
    _rank_verified_workspace_matches,
    build_system_skill_tools,
)
from agents.chat.index import (
    clarification_answer_value,
    location_clarification_copy,
    normalize_browser_current_location,
    normalize_browser_location_request,
    resume_capability_protocol,
)
from agents._controllers.workspace_controller import _learn_from_activated_route


TEST_USER_ID = "test:route-dialogue"


PLACE = {
    "schema_version": 1,
    "place_id": "poi-gugong",
    "provider": "tencent",
    "name": "故宫博物院",
    "address": "北京市东城区景山前街4号",
    "latitude": 39.9163,
    "longitude": 116.3972,
    "city": "北京市",
}


class FakeStore:
    def __init__(self):
        self.values = {}

    async def aget(self, namespace, key):
        value = self.values.get((namespace, key))
        return None if value is None else {"value": value}

    async def aput(self, namespace, key, value):
        self.values[(namespace, key)] = value

__all__ = [name for name in globals() if not name.startswith('__')]
