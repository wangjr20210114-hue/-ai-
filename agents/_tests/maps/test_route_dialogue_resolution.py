from agents._tests.support.route_dialogue_environment import *  # noqa: F401,F403
from agents._application.i18n import text
from agents._application.chat.turn_protocol import (
    explicit_activity_capability_protocol,
    has_resumable_capability_protocol,
)


class RouteDialogueResolutionTests(unittest.IsolatedAsyncioTestCase):
    def test_route_calendar_activity_uses_fixed_adapter_protocol(self):
        plan, arguments = explicit_activity_capability_protocol(
            {
                "activity": "route_calendar_offer_accepted",
                "route_plan_id": "routeplan-hangzhou",
            },
            "把刚规划好的路线添加到日程",
        )
        self.assertTrue(plan["needs_calendar_context"])
        self.assertTrue(plan["needs_calendar_action"])
        self.assertTrue(plan["reuse_latest_route"])
        self.assertEqual(
            arguments["propose_calendar_changes"],
            {
                "summary": "把刚规划好的路线添加到日程",
                "changes": [],
            },
        )

    def test_only_versioned_checkpoint_skips_duplicate_semantic_planning(self):
        self.assertTrue(has_resumable_capability_protocol({
            "version": 1,
            "required_tools": ["propose_calendar_changes"],
        }))
        self.assertFalse(has_resumable_capability_protocol({
            "version": 2,
            "required_tools": ["propose_calendar_changes"],
        }))

    def test_route_calendar_clarification_resumes_with_structured_timing(self):
        plan, arguments = resume_capability_protocol(
            {},
            {
                "version": "1",
                "required_tools": ["propose_calendar_changes"],
                "planned_tool_arguments": {
                    "propose_calendar_changes": {
                        "summary": "把路线排进日程",
                        "changes": [],
                    },
                },
            },
            [
                {"id": "route_calendar_start", "value": "2099-08-04T08:00"},
                {"id": "route_calendar_stop_minutes", "value": "60"},
            ],
        )
        self.assertTrue(plan["reuse_latest_route"])
        calendar = arguments["propose_calendar_changes"]
        self.assertEqual(calendar["route_start_time"], "2099-08-04T08:00")
        self.assertEqual(calendar["route_stop_minutes"], 60)
        self.assertEqual(calendar["changes"], [])

    def test_route_plan_decoder_never_rewrites_place_spelling(self):
        plan = parse_capability_plan({
            "needs_route": True,
            "route_stops": [
                {"query": "北京站", "near_query": ""},
                {"query": "天安们", "near_query": ""},
            ],
        })
        self.assertEqual(
            [item["query"] for item in plan["route_stops"]],
            ["北京站", "天安们"],
        )

    def test_capability_planner_searches_real_places_before_clarifying_ambiguity(self):
        source = (
            Path(__file__).parents[2] / "chat" / "_capability_plan.py"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "不得在调用地点服务之前设置 needs_clarification",
            text("model.planner.system", "zh-CN", today="2099-01-01", user_copy_instruction=""),
        )
        self.assertIn(
            '"model.planner.system"',
            source,
        )
        self.assertIn(
            "不得在规划器中纠错、改名或选择分店",
            planner_topic_instructions()["maps"],
        )
        self.assertNotIn("不得在调用地点服务之前", source)
        self.assertNotIn("Do not ask the user to pre-correct", source)

    def test_place_resolution_target_overrides_premature_generic_clarification(self):
        plan = parse_capability_plan(json.dumps({
            "needs_clarification": True,
            "place_resolution_target": "calendar",
        }))
        self.assertFalse(plan["needs_clarification"])
        self.assertTrue(plan["needs_places"])
        self.assertTrue(plan["needs_calendar_action"])
        self.assertEqual(plan["place_resolution_target"], "calendar")

        genuine_missing_parameter = parse_capability_plan(json.dumps({
            "needs_clarification": True,
            "place_resolution_target": "none",
        }))
        self.assertTrue(genuine_missing_parameter["needs_clarification"])

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
        self.assertTrue(current["ephemeral"])
        self.assertIsNone(normalize_browser_current_location({
            "latitude": 43.82,
            "longitude": 125.32,
            "accuracy_meters": 18,
            "captured_at": 1,
            "coordinate_type": "wgs84",
        }, now_ms=1_200_000))

    def test_browser_location_failure_reason_selects_recovery_card_copy(self):
        self.assertEqual(
            normalize_browser_location_request({"state": "denied"}),
            "denied",
        )
        denied_title, denied_prompt = location_clarification_copy(
            "current", "denied",
        )
        self.assertEqual(denied_title, "定位权限未开启")
        self.assertIn("直接填写", denied_prompt)
        timeout_title, timeout_prompt = location_clarification_copy(
            "nearby", "timed_out",
        )
        self.assertEqual(timeout_title, "定位暂时超时")
        self.assertIn("附近搜索的起点", timeout_prompt)

    def test_manual_location_card_answer_is_available_for_deterministic_resume(self):
        body = {
            "interaction_mode": "clarification",
            "clarification_response": {
                "id": "location-card",
                "answers": [{
                    "id": "manual_location",
                    "label": "你目前所在的位置或出发地",
                    "value": "北京市海淀区中关村",
                }],
            },
        }
        self.assertEqual(
            clarification_answer_value(body, "manual_location"),
            "北京市海淀区中关村",
        )

    def test_semantic_route_plan_preserves_mode_and_current_origin_decision(self):
        plan = parse_capability_plan(json.dumps({
            "needs_route": True,
            "route_stops": [{"query": "故宫博物院", "near_query": ""}],
            "route_city": "北京",
            "route_mode": "transit",
            "route_strategy": "least_cost",
            "route_uses_current_location": True,
        }))
        self.assertEqual(plan["route_mode"], "transit")
        self.assertEqual(plan["route_strategy"], "least_cost")
        self.assertTrue(plan["route_uses_current_location"])
        self.assertEqual(plan["route_stops"][0]["query"], "故宫博物院")
        validated = RoutePlanInput(
            destination_query="故宫博物院",
            route_mode="transit",
            route_strategy="least_cost",
            use_current_location_as_origin=True,
        )
        self.assertTrue(validated.use_current_location_as_origin)
        self.assertEqual(validated.route_strategy, "least_cost")

    def test_side_effect_place_resolution_is_auto_choose_or_fill(self):
        decision, selected, reason = _place_resolution("故宫博物院", [PLACE])
        self.assertEqual(decision, "auto_use")
        self.assertEqual(selected["place_id"], PLACE["place_id"])
        self.assertEqual(reason, "unique_verified_candidate")

        other = {
            **PLACE,
            "place_id": "poi-gugong-north",
            "name": "故宫博物院-北门",
            "address": "北门",
        }
        decision, selected, reason = _place_resolution(
            "故宫博物院", [PLACE, other],
        )
        self.assertEqual((decision, selected, reason), (
            "choose", None, "multiple_verified_candidates",
        ))
        self.assertEqual(
            _place_resolution("不存在的地点", []),
            ("fill", None, "no_verified_candidate"),
        )
        corrected_square = {
            **PLACE,
            "place_id": "poi-tiananmen-square",
            "name": "天安门广场",
            "latitude": 39.9032,
            "longitude": 116.3976,
            "query_correction": {
                "original_query": "天安们",
                "corrected_name": "天安门广场",
                "evidence": "tencent_place_suggestion",
            },
        }
        corrected_gate = {
            **PLACE,
            "place_id": "poi-tiananmen-gate",
            "name": "天安门",
            "latitude": 39.9087,
            "longitude": 116.3975,
            "query_correction": {
                "original_query": "天安们",
                "corrected_name": "天安门",
                "evidence": "tencent_place_suggestion",
            },
        }
        decision, selected, reason = _place_resolution(
            "天安们",
            [corrected_square, corrected_gate],
        )
        self.assertEqual(decision, "auto_use")
        self.assertEqual(selected["place_id"], "poi-tiananmen-square")
        self.assertEqual(
            reason,
            "tencent_provider_ranked_correction",
        )
        search_aliases = [
            {
                **corrected_square,
                "query_correction": {
                    **corrected_square["query_correction"],
                    "evidence": "tencent_place_search",
                },
            },
            {
                **corrected_gate,
                "query_correction": {
                    **corrected_gate["query_correction"],
                    "evidence": "tencent_place_search",
                },
            },
        ]
        self.assertEqual(
            _place_resolution("天安们", search_aliases),
            ("choose", None, "multiple_verified_candidates"),
        )

    async def test_fast_provider_review_selects_only_a_supplied_unique_place(self):
        candidates = [
            {
                **PLACE,
                "place_id": "poi-main",
                "name": "天安门",
                "query_correction": {
                    "original_query": "天安们",
                    "corrected_name": "天安门",
                    "evidence": "tencent_place_suggestion",
                },
            },
            {
                **PLACE,
                "place_id": "poi-access",
                "name": "天安门东[地铁站]",
                "query_correction": {
                    "original_query": "天安们",
                    "corrected_name": "天安门东[地铁站]",
                    "evidence": "tencent_place_suggestion",
                },
            },
        ]
        reviewer = AsyncMock()
        reviewer.ainvoke.return_value = {
            "parsed": {
                "unique_intent": True,
                "selected_place_id": "poi-main",
            },
        }
        model = MagicMock()
        model.with_structured_output.return_value = reviewer

        decision, selected, reason = await _place_resolution_with_provider_review(
            model,
            "天安们",
            candidates,
            context="第 2 站",
        )

        self.assertEqual(decision, "auto_use")
        self.assertEqual(selected["place_id"], "poi-main")
        self.assertEqual(reason, "fast_semantic_provider_review")
        reviewer.ainvoke.assert_awaited_once()

    async def test_fast_provider_review_keeps_distinct_branches_in_choice_card(self):
        candidates = [
            {
                **PLACE,
                "place_id": "poi-wanda-cbd",
                "name": "北京CBD万达广场",
                "query_correction": {
                    "original_query": "万达广场",
                    "corrected_name": "北京CBD万达广场",
                    "evidence": "tencent_place_suggestion",
                },
            },
            {
                **PLACE,
                "place_id": "poi-wanda-tongzhou",
                "name": "北京通州万达广场",
                "query_correction": {
                    "original_query": "万达广场",
                    "corrected_name": "北京通州万达广场",
                    "evidence": "tencent_place_suggestion",
                },
            },
        ]
        reviewer = AsyncMock()
        reviewer.ainvoke.return_value = {
            "parsed": {
                "unique_intent": False,
                "selected_place_id": "",
            },
        }
        model = MagicMock()
        model.with_structured_output.return_value = reviewer

        result = await _place_resolution_with_provider_review(
            model,
            "万达广场",
            candidates,
            context="第 4 站",
        )

        self.assertEqual(
            result,
            ("choose", None, "provider_review_requires_choice"),
        )

    def test_provider_candidates_keep_rank_but_prioritize_proven_city(self):
        zhuhai = {
            **PLACE,
            "place_id": "poi-zhuhai",
            "name": "景山公园索道",
            "city": "珠海市",
            "address": "广东省珠海市香洲区",
        }
        beijing_first = {
            **PLACE,
            "place_id": "poi-beijing-first",
            "name": "景山公园内环跑步路线",
            "city": "北京市",
            "address": "北京市西城区什刹海街道景山公园",
        }
        beijing_second = {
            **PLACE,
            "place_id": "poi-beijing-second",
            "name": "景山公园东门",
            "city": "北京市",
            "address": "北京市西城区",
        }
        ranked = _prioritize_provider_candidates_for_city(
            [zhuhai, beijing_first, beijing_second],
            "北京",
        )
        self.assertEqual(
            [place["place_id"] for place in ranked],
            ["poi-beijing-first", "poi-beijing-second", "poi-zhuhai"],
        )
        self.assertEqual(
            _prioritize_provider_candidates_for_city(
                [zhuhai, beijing_first],
                "全国",
            ),
            [zhuhai, beijing_first],
        )
        self.assertEqual(
            _provider_city_consensus([beijing_first, beijing_second]),
            "北京市",
        )
        self.assertEqual(
            _provider_city_consensus([beijing_first]),
            "北京市",
        )
        self.assertEqual(
            _provider_city_consensus([beijing_first, zhuhai]),
            "",
        )
        card = json.dumps({
            "ui_action": "clarification_action",
            "clarification": {
                "fields": [{
                    "type": "single",
                    "options": [
                        "景山公园索道｜广东省珠海市香洲区",
                        "景山公园内环跑步路线｜北京市西城区什刹海街道景山公园",
                    ],
                }],
            },
        }, ensure_ascii=False)
        ranked_card = json.loads(
            _prioritize_clarification_options_for_city(
                card,
                {
                    zhuhai["place_id"]: zhuhai,
                    beijing_first["place_id"]: beijing_first,
                },
                "北京市",
            )
        )
        self.assertTrue(
            ranked_card["clarification"]["fields"][0]["options"][0]
            .startswith("景山公园内环跑步路线")
        )

    def test_route_preferences_need_repeated_dominant_explicit_choices(self):
        self.assertEqual(
            _learned_route_preference(
                {"mode_counts": {"transit": 2}},
                "mode_counts",
                {"driving", "transit"},
            ),
            "",
        )
        self.assertEqual(
            _learned_route_preference(
                {"mode_counts": {"transit": 3, "driving": 1}},
                "mode_counts",
                {"driving", "transit"},
            ),
            "transit",
        )

    def test_route_learning_requires_activation_and_deduplicates_action(self):
        state = {}
        action = {
            "id": "map-action-1",
            "payload": {
                "preference_signal": {
                    "mode": "transit",
                    "strategy": "least_cost",
                },
            },
        }
        self.assertTrue(_learn_from_activated_route(state, action))
        self.assertFalse(_learn_from_activated_route(state, action))
        learning = state["route_preference_learning"]
        self.assertEqual(learning["mode_counts"], {"transit": 1})
        self.assertEqual(learning["strategy_counts"], {"least_cost": 1})

    def test_map_preferences_default_to_time_then_cost_and_bound_tolerance(self):
        defaults = normalize_map_preferences({})
        self.assertEqual(defaults["route_strategy"], "time_then_cost")
        self.assertEqual(defaults["near_time_tolerance_minutes"], 10)
        self.assertNotIn("semantic_colocation_radius_meters", defaults)
        bounded = normalize_map_preferences({
            "route_strategy": "least_cost",
            "near_time_tolerance_minutes": 99,
            "semantic_colocation_radius_meters": 99_999,
            "learn_route_preferences": False,
        })
        self.assertEqual(bounded["route_strategy"], "least_cost")
        self.assertEqual(bounded["near_time_tolerance_minutes"], 30)
        self.assertNotIn("semantic_colocation_radius_meters", bounded)
        self.assertFalse(bounded["learn_route_preferences"])

    async def test_tencent_suggestion_is_evidence_for_high_confidence_typo(self):
        corrected = {**PLACE, "name": "天安门", "place_id": "poi-tiananmen"}
        with (
            patch(
                "agents._infrastructure.providers.tencent_location.search_places",
                AsyncMock(return_value=[]),
            ),
            patch(
                "agents._infrastructure.providers.tencent_location.search_place_suggestions",
                AsyncMock(return_value=[corrected]),
            ) as suggestions,
            patch(
                "agents._infrastructure.providers.tencent_location.search_osm_places",
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

    async def test_distinguishing_character_does_not_collapse_train_stations(self):
        east_station = {**PLACE, "name": "北京站", "place_id": "poi-beijing-station"}
        west_station = {**PLACE, "name": "北京西站", "place_id": "poi-beijing-west"}
        with (
            patch(
                "agents._infrastructure.providers.tencent_location.search_places",
                AsyncMock(return_value=[east_station]),
            ),
            patch(
                "agents._infrastructure.providers.tencent_location.search_place_suggestions",
                AsyncMock(return_value=[west_station]),
            ) as suggestions,
            patch(
                "agents._infrastructure.providers.tencent_location.search_osm_places",
                AsyncMock(return_value=[]),
            ) as osm,
        ):
            places = await search_verified_places_bounded(
                "key", "北京西站", city="北京", limit=3, timeout_seconds=10,
            )
        self.assertEqual([item["place_id"] for item in places], ["poi-beijing-west"])
        self.assertNotIn("query_correction", places[0])
        suggestions.assert_awaited_once()
        osm.assert_not_awaited()

    async def test_distinguishing_character_is_not_treated_as_typo_without_evidence(self):
        east_station = {**PLACE, "name": "北京站", "place_id": "poi-beijing-station"}
        with (
            patch(
                "agents._infrastructure.providers.tencent_location.search_places",
                AsyncMock(return_value=[east_station]),
            ),
            patch(
                "agents._infrastructure.providers.tencent_location.search_place_suggestions",
                AsyncMock(return_value=[]),
            ),
            patch(
                "agents._infrastructure.providers.tencent_location.search_osm_places",
                AsyncMock(return_value=[]),
            ),
        ):
            places = await search_verified_places_bounded(
                "key", "北京西站", city="北京", limit=3, timeout_seconds=10,
            )
        self.assertEqual(places, [])

    async def test_exact_primary_keeps_tencent_branches_without_fake_correction(self):
        exact = {
            **PLACE,
            "name": "万达广场",
            "place_id": "poi-wanda-cbd",
            "address": "北京市朝阳区建国路93号",
        }
        branch = {
            **PLACE,
            "name": "万达广场(丰台店)",
            "place_id": "poi-wanda-fengtai",
            "address": "北京市丰台区",
        }
        with (
            patch(
                "agents._infrastructure.providers.tencent_location.search_places",
                AsyncMock(return_value=[exact, branch]),
            ),
            patch(
                "agents._infrastructure.providers.tencent_location.search_place_suggestions",
                AsyncMock(return_value=[]),
            ) as suggestions,
        ):
            places = await search_verified_places_bounded(
                "key", "万达广场", city="北京", limit=6, timeout_seconds=10,
            )

        self.assertEqual(
            [item["place_id"] for item in places],
            ["poi-wanda-cbd", "poi-wanda-fengtai"],
        )
        self.assertTrue(all("query_correction" not in item for item in places))
        suggestions.assert_not_awaited()

    async def test_single_exact_primary_merges_tencent_suggestion_branches(self):
        exact = {
            **PLACE,
            "name": "万达广场",
            "place_id": "poi-wanda-cbd",
            "address": "北京市朝阳区建国路93号",
        }
        branch = {
            **PLACE,
            "name": "万达广场(丰台店)",
            "place_id": "poi-wanda-fengtai",
            "address": "北京市丰台区",
        }
        with (
            patch(
                "agents._infrastructure.providers.tencent_location.search_places",
                AsyncMock(return_value=[exact]),
            ),
            patch(
                "agents._infrastructure.providers.tencent_location.search_place_suggestions",
                AsyncMock(return_value=[exact, branch]),
            ) as suggestions,
        ):
            places = await search_verified_places_bounded(
                "key", "万达广场", city="北京", limit=6, timeout_seconds=10,
            )

        self.assertEqual(
            [item["place_id"] for item in places],
            ["poi-wanda-cbd", "poi-wanda-fengtai"],
        )
        self.assertTrue(all("query_correction" not in item for item in places))
        suggestions.assert_awaited_once()

    def test_workspace_candidates_do_not_collapse_similar_station_names(self):
        east_station = {
            **PLACE,
            "name": "北京站",
            "place_id": "poi-beijing-station",
        }
        candidates = {east_station["place_id"]: east_station}
        self.assertEqual(
            _rank_verified_workspace_matches("北京西站", candidates, "北京"),
            [],
        )
        self.assertEqual(
            _rank_verified_workspace_matches("北京站", candidates, "北京"),
            [],
        )
        self.assertEqual(
            _rank_verified_workspace_matches(
                "北京站｜北京市东城区景山前街4号",
                candidates,
                "北京",
            ),
            [east_station],
        )
        west_station_hotel = {
            **PLACE,
            "name": "锦江之星(北京西客站店)",
            "place_id": "poi-west-station-hotel",
        }
        self.assertEqual(
            _rank_verified_workspace_matches(
                "北京西站",
                {west_station_hotel["place_id"]: west_station_hotel},
                "北京",
            ),
            [],
        )

    def test_workspace_candidates_never_reuse_unconfirmed_correction(self):
        corrected = {
            **PLACE,
            "name": "天安门",
            "place_id": "poi-tiananmen",
            "query_correction": {
                "original_query": "天安们",
                "corrected_name": "天安门",
                "confidence": 0.88,
                "evidence": "tencent_place_suggestion",
            },
        }
        self.assertEqual(
            _rank_verified_workspace_matches(
                "天安们", {corrected["place_id"]: corrected}, "北京",
            ),
            [],
        )
        exact_reuse = _rank_verified_workspace_matches(
            "天安门", {corrected["place_id"]: corrected}, "北京",
        )
        self.assertEqual(exact_reuse, [])
        unproven = {
            key: value for key, value in corrected.items()
            if key != "query_correction"
        }
        self.assertEqual(
            _rank_verified_workspace_matches(
                "天安们", {unproven["place_id"]: unproven}, "北京",
            ),
            [],
        )

    def test_single_short_fuzzy_workspace_candidate_requires_fresh_provider_evidence(self):
        cached_restaurant = {
            **PLACE,
            "name": "京宴·鸭儿季烤鸭·北京菜(王府井店)",
            "place_id": "poi-wangfujing-restaurant",
            "category": "美食:中餐厅:北京菜",
        }
        self.assertEqual(
            _rank_verified_workspace_matches(
                "王府井",
                {cached_restaurant["place_id"]: cached_restaurant},
                "北京",
            ),
            [],
        )
        self.assertEqual(
            _rank_verified_workspace_matches(
                "京宴鸭儿季烤鸭北京菜王府井店",
                {cached_restaurant["place_id"]: cached_restaurant},
                "北京",
            ),
            [],
        )
        self.assertEqual(
            _rank_verified_workspace_matches(
                "京宴·鸭儿季烤鸭·北京菜(王府井店)｜北京市东城区景山前街4号",
                {cached_restaurant["place_id"]: cached_restaurant},
                "北京",
            ),
            [cached_restaurant],
        )

    def test_bare_branch_name_never_collapses_to_one_workspace_candidate(self):
        wanda = {
            **PLACE,
            "name": "万达广场",
            "place_id": "poi-wanda-cbd",
            "address": "北京市朝阳区建国路93号",
        }
        self.assertEqual(
            _rank_verified_workspace_matches(
                "万达广场",
                {wanda["place_id"]: wanda},
                "北京",
            ),
            [],
        )
        self.assertEqual(
            _rank_verified_workspace_matches(
                "万达广场｜北京市朝阳区建国路93号",
                {wanda["place_id"]: wanda},
                "北京",
            ),
            [wanda],
        )
