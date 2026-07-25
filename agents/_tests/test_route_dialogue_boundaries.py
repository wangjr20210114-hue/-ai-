import json
import unittest
from unittest.mock import AsyncMock, patch

from agents._shared.route_cache import route_cache_key
from agents._shared.tencent_location import plan_verified_route, search_verified_places_bounded
from agents.chat._capability_plan import parse_capability_plan
from agents.chat._ui_tools import RoutePlanInput
from agents.chat.index import normalize_browser_current_location


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


class RouteDialogueBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def test_browser_location_is_fresh_bounded_and_not_model_text(self):
        current = normalize_browser_current_location({
            "latitude": 43.82,
            "longitude": 125.32,
            "accuracy_meters": 18,
            "captured_at": 1_000_000,
            "coordinate_type": "wgs84",
        }, now_ms=1_200_000)
        self.assertEqual(current["place_id"], "browser-current-location")
        self.assertEqual(current["coordinate_type"], "wgs84")
        self.assertIsNone(normalize_browser_current_location({
            "latitude": 43.82,
            "longitude": 125.32,
            "accuracy_meters": 18,
            "captured_at": 1,
            "coordinate_type": "wgs84",
        }, now_ms=1_200_000))

    def test_semantic_route_plan_preserves_mode_and_current_origin_decision(self):
        plan = parse_capability_plan(json.dumps({
            "needs_route": True,
            "route_stops": [{"query": "故宫博物院", "near_query": ""}],
            "route_city": "北京",
            "route_mode": "transit",
            "route_uses_current_location": True,
        }))
        self.assertEqual(plan["route_mode"], "transit")
        self.assertTrue(plan["route_uses_current_location"])
        self.assertEqual(plan["route_stops"][0]["query"], "故宫博物院")
        validated = RoutePlanInput(
            destination_query="故宫博物院",
            route_mode="transit",
            use_current_location_as_origin=True,
        )
        self.assertTrue(validated.use_current_location_as_origin)

    async def test_tencent_suggestion_is_evidence_for_high_confidence_typo(self):
        corrected = {**PLACE, "name": "天安门", "place_id": "poi-tiananmen"}
        with (
            patch(
                "agents._shared.tencent_location.search_places",
                AsyncMock(return_value=[]),
            ),
            patch(
                "agents._shared.tencent_location.search_place_suggestions",
                AsyncMock(return_value=[corrected]),
            ) as suggestions,
            patch(
                "agents._shared.tencent_location.search_osm_places",
                AsyncMock(return_value=[]),
            ) as osm,
        ):
            places = await search_verified_places_bounded(
                "key", "天安们", city="北京", limit=3, timeout_seconds=10,
            )
        self.assertEqual(places[0]["name"], "天安门")
        self.assertEqual(
            places[0]["query_correction"]["evidence"],
            "tencent_place_suggestion",
        )
        suggestions.assert_awaited_once()
        osm.assert_not_awaited()

    async def test_transit_contract_decodes_path_fare_and_walking_transfer(self):
        browser = {
            "place_id": "browser-current-location",
            "provider": "browser-wgs84",
            "name": "当前位置",
            "address": "",
            "latitude": 39.9,
            "longitude": 116.3,
            "coordinate_type": "wgs84",
        }

        async def provider(url, params):
            if url.endswith("/coord/v1/translate"):
                return {"status": 0, "locations": [{"lat": 39.901, "lng": 116.301}]}
            self.assertTrue(url.endswith("/direction/v1/transit/"))
            return {
                "status": 0,
                "result": {"routes": [{
                    "distance": 10_000,
                    "duration": 45,
                    "steps": [
                        {
                            "mode": "WALKING",
                            "distance": 500,
                            "polyline": [39.901, 116.301, 100, 100],
                        },
                        {
                            "mode": "TRANSIT",
                            "lines": [{
                                "vehicle": "SUBWAY",
                                "title": "地铁1号线",
                                "price": 300,
                                "station_count": 6,
                                "geton": {"title": "起点站"},
                                "getoff": {"title": "终点站"},
                                "polyline": [39.902, 116.302, 100, 100],
                            }],
                        },
                    ],
                }]},
            }

        with patch("agents._shared.tencent_location._get", side_effect=provider):
            route = await plan_verified_route(
                "key", [browser, PLACE], mode="transit",
            )
        self.assertEqual(route["mode"], "transit")
        self.assertEqual(route["duration_seconds"], 45 * 60)
        self.assertEqual(route["fare"]["transit"]["estimate"], 3)
        self.assertEqual(route["transit"]["walking_distance_meters"], 500)
        self.assertEqual(route["transit"]["lines"], ["地铁1号线"])
        self.assertEqual(route["places"][0]["coordinate_type"], "gcj02")
        self.assertGreaterEqual(len(route["path"]), 2)

    def test_cache_separates_each_travel_mode(self):
        places = [PLACE, {**PLACE, "place_id": "other", "latitude": 39.8}]
        self.assertNotEqual(
            route_cache_key(places, False, "driving"),
            route_cache_key(places, False, "walking"),
        )


if __name__ == "__main__":
    unittest.main()
