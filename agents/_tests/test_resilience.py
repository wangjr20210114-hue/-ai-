from __future__ import annotations

import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from urllib.error import URLError

from agents.chat._history import recoverable_history
from agents._shared.rich_search import _json_request, rich_search
from agents._shared.tencent_location import search_schedule_places, search_verified_places


class _Response:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode('utf-8')

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, _limit):
        return self.payload


class ResilienceTests(unittest.IsolatedAsyncioTestCase):
    def test_rich_search_request_retries_transient_network_failure(self):
        with patch('agents._shared.rich_search.time.sleep'), patch(
            'urllib.request.urlopen',
            side_effect=[URLError('network unreachable'), _Response({'Pages': []})],
        ) as request:
            result = _json_request('https://search.example/SearchPro', {'Query': '景山公园'}, {}, 1)
        self.assertEqual(result, {'Pages': []})
        self.assertEqual(request.call_count, 2)

    async def test_rich_search_degrades_without_leaking_urlopen_error(self):
        with patch(
            'agents._shared.rich_search._json_request',
            side_effect=URLError('network unreachable'),
        ):
            result = await rich_search({'WSA_API_KEY': 'test'}, '景山公园附近晚餐')
        self.assertEqual(result['results'], [])
        self.assertEqual(result['search_errors'], ['network_unavailable'])
        self.assertNotIn('urlopen', json.dumps(result))

    async def test_place_search_returns_empty_result_when_all_providers_are_unreachable(self):
        with patch(
            'agents._shared.tencent_location.search_places',
            new=AsyncMock(side_effect=RuntimeError('unreachable')),
        ), patch(
            'agents._shared.tencent_location.search_osm_places',
            new=AsyncMock(side_effect=RuntimeError('unreachable')),
        ):
            result = await search_verified_places('map-key', '查干湖')
        self.assertEqual(result, [])

    async def test_schedule_place_search_prefers_relevant_osm_result(self):
        osm_place = {
            'place_id': 'osm:node:1', 'provider': 'openstreetmap',
            'name': '景山公园', 'address': '北京市西城区景山西街',
            'latitude': 39.925, 'longitude': 116.396,
        }
        with patch(
            'agents._shared.tencent_location.search_osm_places',
            new=AsyncMock(return_value=[osm_place]),
        ) as osm, patch(
            'agents._shared.tencent_location._search_tencent_response',
            new=AsyncMock(return_value=([], [])),
        ) as tencent:
            result = await search_schedule_places('map-key', '景山公园', city='北京')
        self.assertEqual(result, [osm_place])
        osm.assert_awaited_once()
        tencent.assert_not_awaited()

    async def test_schedule_place_search_uses_tencent_only_after_osm_misses(self):
        tencent_place = {
            'place_id': 'tencent:1', 'provider': 'tencent',
            'name': '景山公园', 'address': '北京市西城区景山西街44号',
            'latitude': 39.925, 'longitude': 116.396,
        }
        with patch(
            'agents._shared.tencent_location.search_osm_places',
            new=AsyncMock(return_value=[]),
        ) as osm, patch(
            'agents._shared.tencent_location._search_tencent_response',
            new=AsyncMock(return_value=([tencent_place], [])),
        ) as tencent:
            result = await search_schedule_places('map-key', '景山公园', city='北京')
        self.assertEqual(result, [tencent_place])
        osm.assert_awaited_once()
        tencent.assert_awaited_once()
        self.assertEqual(tencent.await_args.kwargs['retries'], 1)
        self.assertEqual(tencent.await_args.kwargs['timeout'], 8)

    def test_failed_tool_turn_is_removed_but_completed_turn_is_preserved(self):
        failed = [
            SimpleNamespace(type='human', content='第一次提问'),
            SimpleNamespace(type='ai', tool_calls=[{'id': 'call-1'}], content=''),
            SimpleNamespace(type='human', content='第二次提问'),
        ]
        recovered = recoverable_history(failed)
        self.assertEqual([item.content for item in recovered], ['第一次提问', '第二次提问'])

        completed = [
            SimpleNamespace(type='human', content='搜索天气'),
            SimpleNamespace(type='ai', tool_calls=[{'id': 'call-2'}], content=''),
            SimpleNamespace(type='tool', content='结果'),
            SimpleNamespace(type='ai', tool_calls=[], content='天气结果'),
        ]
        self.assertEqual(len(recoverable_history(completed)), 4)


if __name__ == '__main__':
    unittest.main()
