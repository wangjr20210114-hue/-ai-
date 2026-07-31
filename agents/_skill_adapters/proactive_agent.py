"""Preference lifecycle integration for the proactive Agent Skill.

The leading underscore keeps this trusted runtime module outside EdgeOne's
filesystem-to-route discovery.
"""

from __future__ import annotations

from .._shared.proactive import (
    load_proactive_state,
    save_proactive_state,
    update_preferences,
)


async def on_preference_changed(context, enabled: bool) -> None:
    state = await load_proactive_state(context.state_store, context.user_id)
    update_preferences(state, {"enabled": True})
    await save_proactive_state(context.state_store, state, context.user_id)
