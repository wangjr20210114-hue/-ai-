from ..._infrastructure.skills.builtin_operations import RoutePlanInput
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
                "Verify a non-nearby list of named places and prepare one map action."
            ),
            "prepare_map_recommendation": (
                "Prepare a map action from already verified provider place IDs."
            ),
            "plan_route_between_places": (
                "Verify every ordered stop and use Tencent road routing for distance, "
                "duration, fare, and a click-to-activate route action."
            ),
        },
        schemas={"plan_route_between_places": RoutePlanInput},
    )
