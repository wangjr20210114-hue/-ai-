from ..._application.i18n import text
from ..._application.skills.tool_contracts import RoutePlanInput
from .._tool_factory import build_service_tools


def build_tools(context):
    return build_service_tools(
        context,
        "maps",
        {
            "get_current_location": (
                "Read only this request's fresh browser location and reverse-geocode "
                "it; never infer, persist, or expose coordinates."
            ),
            "search_places": "Verify one real place with Tencent Location Service.",
            "search_places_batch": (
                "Verify multiple independent real place queries in one bounded call."
            ),
            "recommend_nearby_places_on_map": (
                "Find real places around one or more verified anchors and prepare a "
                "click-to-activate map action."
            ),
            "recommend_places_on_map": (
                text("model.tool.recommend_places_on_map.description", "zh-CN")
            ),
            "prepare_map_recommendation": (
                "Prepare a map action from already verified provider place IDs."
            ),
            "plan_route_between_places": (
                text("model.tool.plan_route_between_places.description", "zh-CN")
            ),
        },
        schemas={"plan_route_between_places": RoutePlanInput},
    )
