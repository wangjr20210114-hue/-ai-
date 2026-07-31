from ..._application.proactive.service import (
    load_proactive_state,
    save_proactive_state,
    update_preferences,
)
from .._tool_factory import build_service_tools


def build_tools(context):
    return build_service_tools(
        context,
        "proactive",
        {
            "propose_workflow": (
                "Prepare a confirmable multi-step workflow with ordered dependencies "
                "and optional compensation; never activate it before confirmation."
            ),
        },
    )


async def on_preference_changed(context, enabled: bool) -> None:
    state = await load_proactive_state(context.state_store, context.user_id)
    update_preferences(state, {"enabled": bool(enabled)})
    await save_proactive_state(context.state_store, state, context.user_id)

