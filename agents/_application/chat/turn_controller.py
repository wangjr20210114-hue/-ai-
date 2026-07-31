"""Thin application controller for an authenticated chat turn."""

from .turn_service import (
    ChatTurnService,
    SYSTEM_PROMPT,
    SYSTEM_PROMPT_SECTIONS,
    SYSTEM_PROMPT_SECTION_ORDER,
    _document_context,
    capability_planning_message,
    checkpoint_clarification_answers,
    checkpoint_clarification_state,
    checkpoint_dialogue_context,
    checkpoint_final_answer,
    clarification_answer_value,
    clarification_response_answers,
    clarification_response_id,
    direct_paper_tool_arguments,
    dynamic_system_prompt,
    empty_generation_error,
    graph_user_message,
    location_clarification_copy,
    normalize_browser_current_location,
    normalize_browser_location_request,
    resume_capability_protocol,
    run_cancelled,
    runtime_datetime_context,
    should_buffer_public_answer,
    should_persist_user_message,
    tools_for_capability_stage,
)


class ChatTurnController:
    """Own route-to-use-case delegation for one authenticated chat turn."""

    def __init__(self, ctx) -> None:
        self._service = ChatTurnService(ctx)

    async def handle(self):
        return await self._service.handle()


__all__ = (
    "ChatTurnController",
    "SYSTEM_PROMPT",
    "SYSTEM_PROMPT_SECTIONS",
    "SYSTEM_PROMPT_SECTION_ORDER",
    "_document_context",
    "capability_planning_message",
    "checkpoint_clarification_answers",
    "checkpoint_clarification_state",
    "checkpoint_dialogue_context",
    "checkpoint_final_answer",
    "clarification_answer_value",
    "clarification_response_answers",
    "clarification_response_id",
    "direct_paper_tool_arguments",
    "dynamic_system_prompt",
    "empty_generation_error",
    "graph_user_message",
    "location_clarification_copy",
    "normalize_browser_current_location",
    "normalize_browser_location_request",
    "resume_capability_protocol",
    "run_cancelled",
    "runtime_datetime_context",
    "should_buffer_public_answer",
    "should_persist_user_message",
    "tools_for_capability_stage",
)
