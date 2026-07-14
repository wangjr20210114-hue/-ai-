import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch


_MODULE_PATH = Path(__file__).resolve().parents[1] / "agents" / "chat" / "_travel.py"
_SPEC = importlib.util.spec_from_file_location("edgeone_travel", _MODULE_PATH)
assert _SPEC and _SPEC.loader
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)


class _Item:
    def __init__(self, key, value):
        self.key = key
        self.value = value


class _FakeStore:
    def __init__(self):
        self.values = {}

    async def aget(self, namespace, key):
        value = self.values.get((tuple(namespace), key))
        return _Item(key, value) if value is not None else None

    async def aput(self, namespace, key, value):
        self.values[(tuple(namespace), key)] = value

    async def adelete(self, namespace, key):
        self.values.pop((tuple(namespace), key), None)

    async def asearch(self, namespace, limit=100):
        prefix = tuple(namespace)
        return [
            _Item(key, value)
            for (item_namespace, key), value in self.values.items()
            if item_namespace == prefix
        ][:limit]


class _CheckpointTuple:
    def __init__(self, messages):
        self.checkpoint = {"channel_values": {"messages": messages}}


class _Message:
    def __init__(self, role, content):
        self.type = role
        self.content = content


class _FakeCheckpointer:
    async def aget_tuple(self, _config):
        return _CheckpointTuple([
            _Message("human", "我喜欢慢节奏和江南园林"),
            _Message("ai", "记住了。"),
        ])


class _FalseItineraryModel:
    async def ainvoke(self, _messages, config=None):
        return _Message(
            "ai",
            '{"travel_related":true,"city":"杭州","query":"历史文化 景点",'
            '"category":"attraction","count":6,"wants_itinerary":false,'
            '"days":1,"start_date":"","memory_updates":{}}',
        )


class _WrongTomorrowModel:
    async def ainvoke(self, _messages, config=None):
        return _Message(
            "ai",
            '{"travel_related":true,"city":"北京","query":"故宫","category":"attraction",'
            '"count":1,"wants_itinerary":true,"days":1,"start_date":"2026-07-16",'
            '"memory_updates":{}}',
        )


class _GenericLandmarkModel:
    async def ainvoke(self, _messages, config=None):
        return _Message(
            "ai",
            '{"travel_related":true,"city":"北京","query":"北京景点",'
            '"category":"attraction","count":6,"wants_itinerary":true,"days":1,'
            '"start_date":"2026-07-15","memory_updates":{}}',
        )


class _StaleBeijingModel:
    async def ainvoke(self, _messages, config=None):
        return _Message(
            "ai",
            '{"travel_related":true,"city":"北京","query":"历史文化 景点",'
            '"category":"attraction","count":6,"wants_itinerary":true,'
            '"days":1,"start_date":"2026-07-16","memory_updates":{}}',
        )


class EdgeOneTravelAgentTests(unittest.IsolatedAsyncioTestCase):
    def test_fallback_understands_restaurant_count_and_city(self):
        result = _MODULE._fallback_analysis("请给我推荐3家北京不错的餐馆")
        self.assertEqual(result["city"], "北京")
        self.assertEqual(result["category"], "restaurant")
        self.assertEqual(result["count"], 3)
        self.assertFalse(result["wants_itinerary"])

    def test_fallback_proactively_plans_fun_request_but_respects_opt_out(self):
        self.assertTrue(_MODULE._fallback_analysis("杭州有啥好玩的")["wants_itinerary"])
        self.assertFalse(_MODULE._fallback_analysis("杭州有啥好玩的，只推荐不要排行程")["wants_itinerary"])

    def test_short_dated_landmark_request_is_a_deterministic_itinerary(self):
        fixed_now = _MODULE.datetime(2026, 7, 14, 9, 0, tzinfo=_MODULE.SHANGHAI_TZ)
        with patch.object(_MODULE, "_now_shanghai", return_value=fixed_now):
            result = _MODULE._fallback_analysis("明天去故宫")
        self.assertTrue(_MODULE.looks_like_travel("明天去故宫"))
        self.assertTrue(result["wants_itinerary"])
        self.assertEqual(result["city"], "北京")
        self.assertEqual(result["query"], "故宫")
        self.assertEqual(result["start_date"], "2026-07-15")

    def test_dated_city_day_trip_enters_the_travel_pipeline(self):
        fixed_now = _MODULE.datetime(2026, 7, 14, 9, 0, tzinfo=_MODULE.SHANGHAI_TZ)
        with patch.object(_MODULE, "_now_shanghai", return_value=fixed_now):
            result = _MODULE._fallback_analysis("后天我想去杭州一日游")

        self.assertTrue(_MODULE.looks_like_travel("后天我想去杭州一日游"))
        self.assertTrue(result["wants_itinerary"])
        self.assertEqual(result["city"], "杭州")
        self.assertEqual(result["start_date"], "2026-07-16")

    async def test_model_cannot_suppress_explicit_proactive_plan_intent(self):
        result = await _MODULE.analyze_travel_request(
            _FalseItineraryModel(), "杭州有啥好玩的", {},
        )
        self.assertTrue(result["wants_itinerary"])

    async def test_explicit_landmark_overrides_model_city_wide_query(self):
        result = await _MODULE.analyze_travel_request(
            _GenericLandmarkModel(),
            "我想去天安门玩，能给我规划一个明天的行程吗",
            {},
        )
        self.assertEqual(result["city"], "北京")
        self.assertEqual(result["query"], "天安门")
        self.assertEqual(result["category"], "attraction")

    async def test_explicit_city_overrides_stale_conversation_city(self):
        result = await _MODULE.analyze_travel_request(
            _StaleBeijingModel(),
            "后天我想去杭州一日游",
            {"fields": {"home_city": {"value": "北京"}}},
            recent_context="用户：明天去故宫",
        )
        self.assertEqual(result["city"], "杭州")

    async def test_tiananmen_search_returns_only_the_curated_neighborhood(self):
        with patch.object(
            _MODULE,
            "_search_private_places",
            side_effect=AssertionError("curated landmark search must not broaden to city-wide POIs"),
        ), patch.object(
            _MODULE,
            "_search_tencent_places",
            side_effect=AssertionError("curated landmark search must not broaden to city-wide POIs"),
        ):
            places = await _MODULE.search_places(
                {}, city="北京", query="天安门", category="attraction", limit=6,
            )

        self.assertEqual(
            [place["name"] for place in places],
            ["天安门广场", "中国国家博物馆", "毛主席纪念堂", "前门大街"],
        )
        self.assertNotIn("居庸关云台", [place["name"] for place in places])

    async def test_tiananmen_itinerary_and_map_share_schedule_places(self):
        places = await _MODULE.search_places(
            {}, city="北京", query="天安门", category="attraction", limit=6,
        )
        itinerary = _MODULE.build_itinerary(
            "user-a",
            {"city": "北京", "days": 1, "start_date": "2026-07-15", "wants_itinerary": True},
            places,
            {},
        )
        self.assertEqual(
            [item["title"] for item in itinerary["schedules"]],
            ["天安门广场", "中国国家博物馆", "毛主席纪念堂"],
        )
        self.assertTrue(all(item["extra"]["lat"] for item in itinerary["schedules"]))

    async def test_relative_date_uses_shanghai_clock_and_overrides_model_date(self):
        fixed_now = _MODULE.datetime(2026, 7, 14, 16, 30, tzinfo=_MODULE.SHANGHAI_TZ)
        with patch.object(_MODULE, "_now_shanghai", return_value=fixed_now):
            result = await _MODULE.analyze_travel_request(
                _WrongTomorrowModel(), "我想去故宫玩，能给我规划一个明天的行程吗", {},
            )
        self.assertEqual(result["start_date"], "2026-07-15")

    def test_relative_date_parser_prefers_longer_phrase(self):
        fixed_now = _MODULE.datetime(2026, 7, 14, 9, 0, tzinfo=_MODULE.SHANGHAI_TZ)
        with patch.object(_MODULE, "_now_shanghai", return_value=fixed_now):
            self.assertEqual(_MODULE._start_date_from_message("大后天去故宫"), "2026-07-17")
            self.assertEqual(_MODULE._start_date_from_message("后天去故宫"), "2026-07-16")
            self.assertEqual(_MODULE._start_date_from_message("明天去故宫"), "2026-07-15")

    async def test_profile_is_namespaced_and_filters_unknown_fields(self):
        store = _FakeStore()
        profile = await _MODULE.merge_profile(
            store,
            "user-a",
            {
                "pace": {"value": "休闲", "confidence": 0.8},
                "password": {"value": "must-not-store", "confidence": 1},
            },
            source_conversation_id="conversation-a",
        )
        self.assertEqual(profile["fields"]["pace"]["value"], "休闲")
        self.assertNotIn("password", profile["fields"])
        self.assertEqual((await _MODULE.load_profile(store, "user-a"))["fields"]["pace"]["value"], "休闲")
        self.assertEqual(await _MODULE.load_profile(store, "user-b"), {})

    async def test_recent_langgraph_context_is_available_to_travel_analysis(self):
        context = await _MODULE.load_recent_conversation(_FakeCheckpointer(), "conversation-a")
        self.assertIn("慢节奏", context)
        self.assertIn("用户：", context)

    async def test_itinerary_is_persisted_as_editable_schedules(self):
        store = _FakeStore()
        analysis = {
            "city": "杭州", "days": 1, "start_date": "2026-08-01", "wants_itinerary": True,
        }
        places = [
            {"id": f"p{i}", "name": name, "address": f"地址{i}", "category": "attraction",
             "lat": 30.2 + i / 100, "lng": 120.1 + i / 100, "source": "private_place_db"}
            for i, name in enumerate(("西湖", "灵隐寺", "西溪湿地"))
        ]
        itinerary = _MODULE.build_itinerary("user-a", analysis, places, {})
        confirmed = await _MODULE.save_itinerary(store, "user-a", itinerary)
        schedules = await _MODULE.list_schedules(store, "user-a")
        self.assertEqual([item["title"] for item in schedules], ["西湖", "灵隐寺", "西溪湿地"])
        self.assertEqual(confirmed, schedules)
        self.assertTrue(all(item["extra"]["lat"] for item in schedules))
        self.assertFalse(itinerary["tentative_date"])

    async def test_hangzhou_day_trip_is_read_back_on_july_16(self):
        store = _FakeStore()
        fixed_now = _MODULE.datetime(2026, 7, 14, 9, 0, tzinfo=_MODULE.SHANGHAI_TZ)
        with patch.object(_MODULE, "_now_shanghai", return_value=fixed_now):
            analysis = _MODULE._fallback_analysis("后天我想去杭州一日游")
        places = [
            {"id": f"p{i}", "name": name, "address": f"杭州地址{i}", "category": "attraction",
             "lat": 30.2 + i / 100, "lng": 120.1 + i / 100, "source": "private_place_db"}
            for i, name in enumerate(("西湖", "灵隐寺", "西溪湿地"))
        ]

        itinerary = _MODULE.build_itinerary("user-a", analysis, places, {})
        confirmed = await _MODULE.save_itinerary(store, "user-a", itinerary)

        self.assertEqual(analysis["start_date"], "2026-07-16")
        self.assertEqual(len(confirmed), 3)
        self.assertTrue(all(
            _MODULE.datetime.fromtimestamp(item["start_time"], _MODULE.SHANGHAI_TZ).date().isoformat()
            == "2026-07-16"
            for item in await _MODULE.list_schedules(store, "user-a")
        ))

    async def test_itinerary_uses_pace_and_adds_meal_slots_without_duplicates(self):
        store = _FakeStore()
        profile = {"fields": {"pace": {"value": "休闲慢节奏"}}}
        analysis = {"city": "杭州", "days": 1, "start_date": "2026-08-01", "wants_itinerary": True}
        places = [
            {"id": "a", "name": "西湖", "address": "西湖区", "category": "attraction",
             "lat": 30.25, "lng": 120.15, "source": "private_place_db"},
            {"id": "b", "name": "灵隐寺", "address": "灵隐路", "category": "attraction",
             "lat": 30.24, "lng": 120.10, "source": "private_place_db"},
            {"id": "c", "name": "西溪湿地", "address": "天目山路", "category": "attraction",
             "lat": 30.27, "lng": 120.05, "source": "private_place_db"},
            {"id": "r1", "name": "杭帮菜馆", "address": "北山街", "category": "restaurant",
             "lat": 30.26, "lng": 120.14, "source": "tencent_map"},
        ]
        itinerary = _MODULE.build_itinerary("user-a", analysis, places, profile)
        titles = [item["title"] for item in itinerary["schedules"]]
        self.assertEqual(titles, ["西湖", "杭帮菜馆", "灵隐寺"])
        self.assertNotIn("西溪湿地", titles)
        await _MODULE.save_itinerary(store, "user-a", itinerary)
        await _MODULE.save_itinerary(store, "user-a", _MODULE.build_itinerary("user-a", analysis, places, profile))
        self.assertEqual(len(await _MODULE.list_schedules(store, "user-a")), 3)

    async def test_route_has_geometric_fallback_without_server_key(self):
        result = await _MODULE.plan_daily_route({}, "北京", [
            {"id": "a", "keyword": "故宫", "name": "故宫", "lat": 39.916, "lng": 116.397},
            {"id": "b", "keyword": "景山", "name": "景山", "lat": 39.925, "lng": 116.397},
        ])
        self.assertEqual(result["route_source"], "geometric_fallback")
        self.assertGreater(result["total_distance"], 0)
        self.assertEqual(len(result["polyline"]), 4)

    def test_tencent_polyline_is_forward_difference_decoded(self):
        decoded = _MODULE.decode_tencent_polyline([
            39.9, 116.3,
            1000, -2000,
            2000, 3000,
        ])
        self.assertEqual(len(decoded), 6)
        self.assertAlmostEqual(decoded[2], 39.901)
        self.assertAlmostEqual(decoded[3], 116.298)
        self.assertAlmostEqual(decoded[4], 39.903)
        self.assertAlmostEqual(decoded[5], 116.301)

    def test_route_alternative_matches_frontend_contract(self):
        value = _MODULE._route_alternative({
            "id": "p1", "name": "故宫博物院", "address": "东城区", "lat": 39.9, "lng": 116.4,
        })
        self.assertEqual(value["title"], "故宫博物院")

    def test_place_merge_preserves_source_priority_and_deduplicates(self):
        tencent = [
            {"name": "西湖", "address": "杭州市西湖区", "source": "tencent_map"},
            {"name": "灵隐寺", "address": "灵隐路", "source": "tencent_map"},
        ]
        private = [
            {"name": "西 湖", "address": "杭州市 西湖区", "source": "private_place_db"},
            {"name": "西溪湿地", "address": "天目山路", "source": "private_place_db"},
        ]
        merged = _MODULE._merge_places(tencent, private, limit=3)
        self.assertEqual([item["name"] for item in merged], ["西湖", "灵隐寺", "西溪湿地"])
        self.assertEqual(merged[0]["source"], "tencent_map")

    def test_place_query_variants_relax_model_phrase(self):
        variants = _MODULE._place_query_variants("杭州", "杭州 历史文化 景点", "attraction")
        self.assertEqual(variants, ["杭州 历史文化 景点", "历史文化 景点", "博物馆", "景点"])

    def test_internal_tool_protocol_uses_verified_place_fallback(self):
        self.assertTrue(_MODULE.contains_internal_tool_protocol(
            "<tool_calls:abc>\n<tool_call:abc>web_search",
        ))
        answer = _MODULE.deterministic_places_answer(
            {"city": "北京", "category": "attraction", "count": 2, "days": 1},
            [
                {"name": "故宫博物院", "address": "东城区", "category": "attraction"},
                {"name": "颐和园", "address": "海淀区", "category": "attraction"},
                {"name": "测试餐厅", "address": "北京市", "category": "restaurant"},
            ],
            {
                "start_date": "2026-07-15",
                "days": 1,
                "schedules": [{
                    "title": "故宫博物院",
                    "location": "北京市东城区景山前街4号",
                    "start_time": _MODULE.datetime(
                        2026, 7, 15, 9, 0, tzinfo=_MODULE.SHANGHAI_TZ,
                    ).timestamp(),
                }],
            },
        )
        self.assertIn("故宫博物院", answer)
        self.assertIn("09:00", answer)
        self.assertNotIn("颐和园", answer)
        self.assertNotIn("测试餐厅", answer)
        self.assertIn("已写入右侧日历", answer)
        self.assertNotIn("后续问题", answer)

    def test_itinerary_answer_uses_only_persisted_schedule_places(self):
        answer = _MODULE.deterministic_places_answer(
            {"city": "杭州", "category": "attraction", "days": 1},
            [{"name": "模型想写但未落库的地点", "category": "attraction"}],
            {
                "city": "杭州",
                "start_date": "2026-07-16",
                "days": 1,
                "schedules": [
                    {"title": "钱王祠", "location": "钱王祠", "start_time": 1784154000},
                    {"title": "雷峰塔", "location": "雷峰塔", "start_time": 1784173800},
                ],
            },
        )

        self.assertIn("钱王祠", answer)
        self.assertIn("雷峰塔", answer)
        self.assertNotIn("模型想写但未落库的地点", answer)

    def test_one_day_answer_date_is_grounded_to_persisted_itinerary(self):
        answer = (
            "明天（2026-07-16）去故宫。\n"
            "## 2026-07-16 故宫一日游\n"
            "行程已写入右侧日历（2026-07-16）。"
        )
        grounded = _MODULE.ground_itinerary_answer_date(
            answer,
            {"start_date": "2026-07-15", "days": 1},
        )
        self.assertNotIn("2026-07-16", grounded)
        self.assertEqual(grounded.count("2026-07-15"), 3)

    def test_expressive_itinerary_answer_is_preserved_when_complete(self):
        itinerary = {
            "city": "苏州",
            "start_date": "2026-07-29",
            "days": 1,
            "schedules": [
                {
                    "title": "开元寺无梁殿",
                    "location": "开元寺无梁殿",
                    "start_time": _MODULE.datetime(
                        2026, 7, 29, 9, 0, tzinfo=_MODULE.SHANGHAI_TZ,
                    ).timestamp(),
                },
                {
                    "title": "柴园·苏州教育博物馆",
                    "location": "柴园",
                    "start_time": _MODULE.datetime(
                        2026, 7, 29, 14, 30, tzinfo=_MODULE.SHANGHAI_TZ,
                    ).timestamp(),
                },
            ],
        }
        model_answer = (
            "这条线很适合慢慢逛：2026-07-29 09:00 从开元寺无梁殿开始，"
            "14:30 再去柴园·苏州教育博物馆。中间别急着赶路，留点时间喝茶。"
            "正式安排已经写入右侧日历。"
        )
        answer = _MODULE.ensure_itinerary_in_answer(
            model_answer, {"city": "苏州"}, [], itinerary,
        )
        self.assertEqual(answer, model_answer)
        self.assertNotIn("| 时间 | 安排 | 地点 |", answer)

    def test_missing_itinerary_facts_are_appended_without_replacing_model_prose(self):
        itinerary = {
            "city": "苏州",
            "start_date": "2026-07-29",
            "days": 1,
            "schedules": [{
                "title": "瑞光塔",
                "location": "盘门景区",
                "start_time": _MODULE.datetime(
                    2026, 7, 29, 16, 30, tzinfo=_MODULE.SHANGHAI_TZ,
                ).timestamp(),
            }],
        }
        answer = _MODULE.ensure_itinerary_in_answer(
            "苏州适合放慢脚步，沿途多看看街巷。",
            {"city": "苏州"},
            [],
            itinerary,
        )
        self.assertTrue(answer.startswith("苏州适合放慢脚步"))
        self.assertIn("2026-07-29", answer)
        self.assertIn("16:30", answer)
        self.assertIn("瑞光塔", answer)
        self.assertIn("已经写入右侧日历", answer)

    def test_private_place_origin_has_production_default(self):
        self.assertEqual(
            _MODULE._env_value({}, "PLACE_API_BASE_URL", _MODULE.DEFAULT_PLACE_API_BASE_URL),
            "https://94-16-110-28.sslip.io",
        )

    async def test_place_search_falls_back_to_generic_category_query(self):
        private_queries = []
        tencent_queries = []

        async def fake_private(_env, *, city, query, category, limit):
            private_queries.append(query)
            if query != "景点":
                return []
            return [
                {"id": f"p{i}", "name": name, "address": "杭州", "category": category,
                 "lat": 30.2 + i / 100, "lng": 120.1, "source": "private_place_db"}
                for i, name in enumerate(("西湖", "灵隐寺", "浙江省博物馆"))
            ][:limit]

        async def fake_tencent(_env, *, city, query, limit):
            tencent_queries.append(query)
            return []

        with patch.object(_MODULE, "_search_private_places", side_effect=fake_private), patch.object(
            _MODULE, "_search_tencent_places", side_effect=fake_tencent,
        ):
            result = await _MODULE.search_places(
                {}, city="杭州", query="杭州 历史文化 景点", category="attraction", limit=3,
            )

        self.assertEqual([item["name"] for item in result], ["西湖", "灵隐寺", "浙江省博物馆"])
        self.assertEqual(private_queries[-1], "景点")
        self.assertIn("历史文化 景点", tencent_queries)

    async def test_hangzhou_has_stable_route_fallback_when_live_sources_are_empty(self):
        async def empty_search(*_args, **_kwargs):
            return []

        with patch.object(_MODULE, "_search_private_places", side_effect=empty_search), patch.object(
            _MODULE, "_search_tencent_places", side_effect=empty_search,
        ):
            result = await _MODULE.search_places(
                {}, city="杭州", query="杭州景点", category="attraction", limit=6,
            )

        self.assertEqual(
            [item["name"] for item in result],
            ["西湖风景名胜区", "灵隐寺", "西溪国家湿地公园"],
        )
        self.assertTrue(all(item["lat"] and item["lng"] for item in result))
        self.assertTrue(all(item["source"] == "curated_city_fallback" for item in result))

    async def test_dynamic_place_search_never_uses_stale_private_commercial_rows(self):
        async def fake_private(*_args, **_kwargs):
            raise AssertionError("dynamic categories must not query the private stable index")

        async def fake_tencent(*_args, **_kwargs):
            return []

        with patch.object(_MODULE, "_search_private_places", side_effect=fake_private), patch.object(
            _MODULE, "_search_tencent_places", side_effect=fake_tencent,
        ):
            result = await _MODULE.search_places(
                {}, city="杭州", query="餐厅", category="restaurant", limit=4,
            )
        self.assertEqual(result, [])


if __name__ == "__main__":
    unittest.main()
