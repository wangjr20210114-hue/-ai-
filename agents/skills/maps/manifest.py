MANIFEST = {
    "schema_version": 1,
    "id": "maps",
    "order": 40,
    "default_enabled": True,
    "capabilities": [
        "current_location",
        "nearby_places",
        "places",
        "map_action",
        "route",
    ],
    "plan_flags": [
        "needs_places",
        "needs_current_location",
        "needs_nearby_places",
        "needs_route",
        "needs_map_action",
    ],
    "tools": [
        {"name": "get_current_location", "capability": "current_location"},
        {"name": "search_places", "capability": "places"},
        {"name": "search_places_batch", "capability": "places", "required": False},
        {"name": "recommend_nearby_places_on_map", "capability": "nearby_places"},
        {"name": "recommend_places_on_map", "capability": "map_action"},
        {"name": "prepare_map_recommendation", "capability": "map_action", "required": False},
        {"name": "plan_route_between_places", "capability": "route"},
    ],
    "action_kinds": ["map_recommendation"],
    "permissions": [
        "makers.state",
        "makers.trace",
        "conversation.read",
        "user.read",
        "browser.location",
    ],
    "env_keys": ["TENCENT_MAP_KEY", "TENCENT_MAP_SK"],
    "ui": {
        "icon": "⌖",
        "name": {"zh-CN": "真实地点与地图", "zh-TW": "真實地點與地圖", "en": "Real places and maps"},
        "description": {
            "zh-CN": "核实餐厅、景点和地址，并展示真实坐标与腾讯路线。",
            "zh-TW": "核實餐廳、景點和地址，並展示真實座標與騰訊路線。",
            "en": "Verify places and addresses, then show real coordinates and Tencent routes.",
        },
    },
    "planner": {
        "topic": "maps",
        "summary": "Real places, browser location, nearby discovery, ordered stops and road routes.",
        "instructions": (
            "【地图与路线】直接问当前位置用 needs_current_location；周边商家只用 "
            "needs_nearby_places，并填写 nearby_query、明确参照地或 "
            "nearby_uses_current_location；目的地介绍/多地点推荐用 "
            "needs_places+needs_map_action；真实道路距离、耗时、费用或有序停靠用 needs_route。"
            "route_stops 逐字、按原顺序保留，不得在规划器中纠错、改名或选择分店；若使用浏览器"
            "当前位置作起点，route_uses_current_location=true 且 route_stops 只列目的地；"
            "错字/同名交给腾讯地点服务处理，不得提前澄清。只有用户明确优先最短耗时才设置 "
            "route_strategy=least_time；询问真实耗时或要求按路程安排日程不代表该偏好，保持 default。"
        ),
        "recovery_tools": [
            "get_current_location",
            "search_places",
            "recommend_nearby_places_on_map",
            "recommend_places_on_map",
            "plan_route_between_places",
        ],
    },
}
