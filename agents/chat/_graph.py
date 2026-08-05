"""LangGraph state graph backed by Makers checkpointer and store adapters."""

from typing import Iterable, Literal
import json
import logging
import uuid

from langchain_core.messages import AIMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.types import RetryPolicy

from ._history import (
    bounded_history,
    compact_tool_results_for_model,
    flatten_completed_tools_for_model,
)
from ._protocol import dsml_tool_calls, public_content
from ._capability_plan import next_required_tool
from ._llm import _is_quota_error, _is_transient_gateway_error
from .._application.i18n import text
from .._application.chat.turn_control import committed_checkpoint_messages


# Tool payloads may be rendered directly when both synthesis passes fail, so a
# runtime detail must always be safe user copy rather than a model instruction.
TOOL_FAILURE_MESSAGE = text("chat.fallback.required_failed", "zh-CN")

# These tools already accept a batch, a composite request, or one complete
# side-effect proposal. Calling the same capability again in one logical turn
# is therefore retry churn, not additional reasoning. The LLM still plans the
# tool and its arguments; this is only a runtime safety budget.
TURN_SINGLE_USE_TOOLS = {
    "get_current_location",
    "rich_search",
    "search_places",
    "search_places_batch",
    "plan_route_between_places",
    "prepare_map_recommendation",
    "recommend_places_on_map",
    "recommend_nearby_places_on_map",
    "propose_calendar_changes",
    "propose_meeting",
    "propose_image",
    "search_arxiv",
    "ask_user_clarification",
}
# An argument-validation error occurs before an Action is created. Two bounded
# correction passes are enough to repair dependent fixed-schema payloads (for
# example, first fixing a time window and then restoring a required route stop)
# without turning provider/runtime failures into retry loops.
MAX_REQUIRED_VALIDATION_ATTEMPTS = 3

from ._fallbacks import (
    _linked_trip_result_answer,
    _route_result_answer,
    _route_result_with_calendar_degraded,
    action_completion_fallback,
    blocked_capability_response,
    grounded_route_action_answer,
    grounded_route_stream_answer,
    tool_failure_fallback,
    tool_result_fallback,
)


def _tool_call_signature(tool_call: dict) -> str:
    name = str(tool_call.get("name") or "")
    args = tool_call.get("args") if isinstance(tool_call, dict) else {}
    return f"{name}:{json.dumps(args, ensure_ascii=False, sort_keys=True, default=str, separators=(',', ':'))}"


def _tagged(model, tag: str):
    """Attach LangChain stream metadata without constraining test doubles."""
    with_config = getattr(model, "with_config", None)
    return with_config(tags=[tag]) if callable(with_config) else model


def _tool_failure_message(exc: Exception) -> str:
    """Keep safe validation feedback so the model can answer naturally."""
    if isinstance(exc, ValueError):
        detail = str(exc).strip()[:500] or text(
            "chat.fallback.invalid_input", "zh-CN",
        )
        kind = "validation"
        retry_same_call = True
    else:
        detail = TOOL_FAILURE_MESSAGE
        kind = "runtime"
        retry_same_call = False
    return json.dumps({
        "tool_error": {
            "kind": kind,
            "detail": detail,
            # Validation failures happen before an Action is created or any
            # side effect is applied. One corrected argument-generation pass is
            # therefore safe; runtime/provider failures remain terminal.
            "retry_same_call": retry_same_call,
        },
    }, ensure_ascii=False)


def _retry_model_node(error: Exception) -> bool:
    """Retry only provider conditions that are safe before state is emitted."""
    return _is_quota_error(error) or _is_transient_gateway_error(error)


def _hidden_clarification_answer(message) -> bool:
    if getattr(message, "type", "") not in {"human", "user"}:
        return False
    additional = getattr(message, "additional_kwargs", None) or {}
    return (
        isinstance(additional, dict)
        and additional.get("floris_interaction") == "clarification"
    )


def build_graph(
    model: ChatOpenAI,
    tools: list,
    system_prompt: str,
    checkpointer=None,
    store=None,
    required_tool: str = "",
    required_tools: Iterable[str] | None = None,
    blocked_skill: str = "",
    response_language: str = "zh-CN",
    public_answer_model=None,
    fast_tool_model=None,
    reasoning_tools: Iterable[str] | None = None,
    stage_system_prompts: dict[str, str] | None = None,
    public_system_prompt: str | None = None,
    planned_tool_arguments: dict[str, dict] | None = None,
    direct_answer: str = "",
    discarded_client_message_ids: Iterable[str] | None = None,
):
    public_model = _tagged(
        public_answer_model or model,
        "floris:public-answer",
    )
    model_with_tools = (
        _tagged(model.bind_tools(tools), "floris:tool-capable")
        if tools else public_model
    )
    allowed_tool_names = {getattr(tool, "name", "") for tool in tools}
    required_sequence = tuple(required_tools or (() if not required_tool else (required_tool,)))
    fast_decision_model = fast_tool_model or model
    reasoning_tool_names = set(reasoning_tools or ())
    tool_stage_prompts = dict(stage_system_prompts or {})
    final_system_prompt = public_system_prompt or system_prompt
    direct_tool_arguments = dict(planned_tool_arguments or {})
    discarded_turns = {
        str(value) for value in (discarded_client_message_ids or ()) if str(value)
    }
    history_run = {
        "discarded_client_message_ids": list(discarded_turns),
    }

    async def agent_node(state: MessagesState):
        runtime_messages = committed_checkpoint_messages(
            state["messages"], history_run,
        )
        if direct_answer:
            return {"messages": [AIMessage(content=direct_answer)]}
        # The semantic LLM planner—not a keyword rule—decides that a disabled
        # Skill is indispensable. Once decided, the runtime enforces the UI
        # truth contract: no model may simulate a card, search result or side
        # effect that cannot exist.
        if blocked_skill:
            return {"messages": [AIMessage(content=blocked_capability_response(
                [blocked_skill], response_language,
            ))]}
        tools_this_turn = 0
        used_tool_names = []
        seen_tool_call_signatures: set[str] = set()
        clarification_ready = False
        crossed_clarification_answer = False
        route_result_payload = None
        calendar_result_payload = None
        required_tool_failed = False
        failed_required_tools: set[str] = set()
        retryable_required_failures: dict[str, int] = {}
        for message in reversed(runtime_messages):
            if getattr(message, "type", "") in {"human", "user"}:
                # A structured-card answer is a continuation of the original
                # logical turn, not a brand-new task. Reuse completed route,
                # place and search tools from before the card so submitting one
                # missing time does not repeat expensive work. The prior
                # clarification tool itself is deliberately excluded below:
                # its card was terminal only before the user answered it.
                if _hidden_clarification_answer(message):
                    crossed_clarification_answer = True
                    continue
                break
            if getattr(message, "type", "") == "tool":
                name = getattr(message, "name", "")
                payload = None
                try:
                    payload = json.loads(str(getattr(message, "content", "") or ""))
                except (TypeError, json.JSONDecodeError):
                    pass
                tool_error = (
                    payload.get("tool_error")
                    if isinstance(payload, dict)
                    and isinstance(payload.get("tool_error"), dict)
                    else None
                )
                if name in required_sequence and isinstance(tool_error, dict):
                    failed_required_tools.add(name)
                    retryable = bool(tool_error.get("retry_same_call"))
                    retryable_required_failures[name] = (
                        retryable_required_failures.get(name, 0) + 1
                    )
                    required_tool_failed = required_tool_failed or (
                        not retryable
                        or retryable_required_failures[name]
                        >= MAX_REQUIRED_VALIDATION_ATTEMPTS
                    )
                emitted_clarification = (
                    isinstance(payload, dict)
                    and payload.get("ui_action") == "clarification_action"
                )
                if (
                    name == "plan_route_between_places"
                    and isinstance(payload, dict)
                    and payload.get("ui_action") == "map_action"
                    and isinstance(payload.get("route"), dict)
                ):
                    route_result_payload = payload
                if (
                    isinstance(payload, dict)
                    and payload.get("ui_action") == "calendar_action"
                    and isinstance(payload.get("action"), dict)
                ):
                    calendar_result_payload = payload
                if crossed_clarification_answer and (
                    name == "ask_user_clarification" or emitted_clarification
                ):
                    # A required domain tool can itself discover ambiguity and
                    # return a structured card (for example, multiple hotel
                    # branches). Answering that card does not mean the route or
                    # action completed; the same capability must run again with
                    # the newly supplied choice.
                    continue
                if (
                    name in required_sequence
                    and isinstance(tool_error, dict)
                    and bool(tool_error.get("retry_same_call"))
                    and retryable_required_failures.get(name, 0)
                    < MAX_REQUIRED_VALIDATION_ATTEMPTS
                ):
                    # Do not mark a validation-only attempt complete. The next
                    # pass sees the exact structured error and may correct the
                    # required tool arguments within the bounded budget;
                    # identical calls are still blocked by the signature guard.
                    continue
                if not crossed_clarification_answer:
                    tools_this_turn += 1
                used_tool_names.append(name)
                clarification_ready = clarification_ready or (
                    not crossed_clarification_answer and emitted_clarification
                )
            if getattr(message, "type", "") in {"ai", "assistant"}:
                for tool_call in list(getattr(message, "tool_calls", None) or []):
                    if isinstance(tool_call, dict):
                        seen_tool_call_signatures.add(_tool_call_signature(tool_call))
        # The structured card is the complete response for a clarification
        # turn. Do not run a second prose pass that repeats the questions after
        # the card and makes the interaction feel like an afterthought.
        if "ask_user_clarification" in used_tool_names or clarification_ready:
            # Keep the unfinished machine protocol in the native LangGraph
            # checkpoint. A card answer is only one field update, not a new
            # user goal; the next request must therefore recover the original
            # tool sequence and planner-authored arguments without asking an
            # LLM to reconstruct them from prose.
            return {"messages": [AIMessage(
                content="",
                additional_kwargs={
                    "floris_resume": {
                        "version": 1,
                        "required_tools": list(required_sequence),
                        "planned_tool_arguments": direct_tool_arguments,
                    },
                },
            )]}
        # Preserve an earlier verified route if only its independent calendar
        # enhancement failed. Never tell the user that nothing ran after a real
        # Tencent map Action was already emitted.
        search_only_degraded = bool(
            required_tool_failed
            and tuple(required_sequence) == ("rich_search",)
            and failed_required_tools == {"rich_search"}
        )
        if required_tool_failed and not search_only_degraded:
            route_only_answer = _route_result_with_calendar_degraded(
                route_result_payload, response_language,
            )
            if (
                route_only_answer
                and "propose_calendar_changes" in required_sequence
            ):
                return {"messages": [AIMessage(content=route_only_answer)]}
            return {"messages": [AIMessage(content=(
                tool_failure_fallback(runtime_messages, response_language)
                or text("chat.fallback.required_failed", response_language)
            ))]}
        # Current-location lookup has a fixed privacy-preserving presentation.
        # Once Tencent reverse geocoding succeeds (or truthfully reports
        # unavailable), another model round cannot add facts and may only
        # hallucinate permission state.
        if (
            tuple(required_sequence) == ("get_current_location",)
            and {name for name in used_tool_names if name}
            == {"get_current_location"}
        ):
            location_answer = tool_result_fallback(
                runtime_messages, response_language,
            )
            if location_answer:
                return {"messages": [AIMessage(content=location_answer)]}
        # A calendar Action is the frozen, user-confirmable source of truth.
        # Do not ask a second model pass to restate its event timestamps: that
        # can contradict the same structured card even though the Adapter
        # computed every event correctly. This protocol rule applies to every
        # calendar proposal, including route continuations, without inspecting
        # user wording, place names, or dates.
        if calendar_result_payload is not None:
            grounded_calendar_answer = grounded_route_stream_answer(
                [
                    *([route_result_payload] if route_result_payload else []),
                    calendar_result_payload,
                ],
                calendar_required=True,
                clarification_emitted=False,
                run_error="",
                response_language=response_language,
            )
            if grounded_calendar_answer:
                return {"messages": [AIMessage(content=grounded_calendar_answer)]}
        # Structured paper and route results are evidence and UI actions, not
        # canned answers. The public model receives them
        # and writes the final response in the current conversational style.
        # Local renderers remain available only as last-resort fallbacks when
        # both normal and clean synthesis passes return no public text.
        # A model can occasionally keep reformulating the same search. Preserve
        # multi-tool reasoning, but after a generous turn-local budget force a
        # normal answer from the evidence already collected instead of exposing
        # LangGraph's recursion error to the user.
        force_finalize = tools_this_turn >= 4
        rich_search_used = "rich_search" in used_tool_names
        unavailable_required_tools = [
            name for name in required_sequence
            if name not in allowed_tool_names and name not in used_tool_names
        ]
        next_available_required = next_required_tool(
            required_sequence, used_tool_names, allowed_tool_names,
        )
        # Execute every available prefix before degrading on a later missing
        # capability. This is what lets a verified route survive an unavailable
        # independent calendar proposal.
        if unavailable_required_tools and not next_available_required:
            route_only_answer = _route_result_with_calendar_degraded(
                route_result_payload, response_language,
            )
            if (
                route_only_answer
                and set(unavailable_required_tools)
                == {"propose_calendar_changes"}
            ):
                return {"messages": [AIMessage(content=route_only_answer)]}
            return {"messages": [AIMessage(content=blocked_capability_response(
                unavailable_required_tools,
                response_language,
                configured=True,
            ))]}
        required_name = "" if force_finalize else next_available_required
        planned_sequence_complete = bool(required_sequence) and not required_name
        planned_arguments = direct_tool_arguments.get(required_name)
        if (
            required_name
            and required_name not in used_tool_names
            and isinstance(planned_arguments, dict)
        ):
            return {"messages": [AIMessage(content="", tool_calls=[{
                "name": required_name,
                "args": planned_arguments,
                "id": f"planned-{required_name}-{uuid.uuid4().hex}",
            }])]}
        # The semantic LLM planner has already decided that rich_search is
        # required and the tool adapter already owns its merged search query.
        # Asking a second tool-bound LLM to merely echo that decision adds a
        # full model round without changing any provider input.  Emit the
        # planned call directly; all search decisions still come from the LLM
        # plan and the answering pass remains model-generated.
        if required_name == "rich_search" and not rich_search_used:
            return {"messages": [AIMessage(content="", tool_calls=[{
                "name": "rich_search",
                "args": {"query": text(
                    "model.graph.planned_search_placeholder", response_language,
                )},
                "id": f"planned-rich-search-{uuid.uuid4().hex}",
            }])]}
        # Once the planner-required rich search is complete and no other
        # capability remains, close the tool surface for the answer pass.  A
        # tool-bound answer model otherwise tends to request rich_search again;
        # the request is safely suppressed below, but that costs a second LLM
        # round after the provider has already returned.
        finalize_after_rich_search = rich_search_used and not required_name
        remaining_tools = [
            tool for tool in tools
            if getattr(tool, "name", "") != "rich_search"
        ]
        tools_closed = (
            force_finalize
            or planned_sequence_complete
            # A failed rich-search-only chain is an enhancement downgrade, not
            # a reason to expose the rest of the tool surface.  Closing the
            # optional tools here guarantees that the public model receives
            # the original conversation plus a small freshness boundary and
            # can answer naturally from its own knowledge.
            or search_only_degraded
            or (finalize_after_rich_search and not remaining_tools)
        )
        route_verified_for_calendar = bool(
            required_name == "propose_calendar_changes"
            and "plan_route_between_places" in used_tool_names
            and "plan_route_between_places" in required_sequence
            and not required_tool_failed
        )
        allow_stage_clarification = bool(
            "ask_user_clarification" in allowed_tool_names
            and not route_verified_for_calendar
        )
        linked_trip_step = False
        reasoning_tool_step = False
        if force_finalize or search_only_degraded:
            active_model = public_model
        elif planned_sequence_complete:
            # The semantic planner's shortest capability chain has completed.
            # Close the tool surface for synthesis so the answer model cannot
            # restart a successful place/search/action capability.
            active_model = public_model
        elif finalize_after_rich_search:
            active_model = (
                _tagged(model.bind_tools(remaining_tools), "floris:tool-capable")
                if remaining_tools else public_model
            )
        elif required_name and "ask_user_clarification" in allowed_tool_names:
            # The planner guarantees that one capability is required, while
            # the full-history model decides whether the dialogue has actually
            # supplied every blocking parameter. This applies uniformly to
            # writing, translation, image, place, route, calendar, meeting and
            # other tool-backed Q&A—not to a hard-coded task category.
            #
            # A linked calendar stage is different after its route Action has
            # already succeeded: every physical stop is provider-verified and
            # the semantic preflight has already checked the user-level
            # dependencies before any provider work. Re-exposing the generic
            # clarification tool here lets the JSON argument model second-guess
            # settled Tencent results, producing a route Action and a
            # contradictory place card in the same response. Close that one
            # redundant branch and require the dependent calendar proposal to
            # consume the verified route instead.
            required_or_question_tools = [
                tool for tool in tools
                if getattr(tool, "name", "") in {
                    required_name,
                    *(
                        set()
                        if not allow_stage_clarification
                        else {"ask_user_clarification"}
                    ),
                }
            ]
            # Some OpenAI-compatible gateways reject a complex multi-stop
            # route/calendar request when tool_choice="required" is combined
            # with either large tool schema. Keep each dependent decision
            # constrained to its current capability-or-clarification, but let
            # the model select automatically. The sequence still prevents the
            # calendar step from seeing or restarting the route capability.
            linked_trip_step = (
                required_name in {
                    "plan_route_between_places",
                    "propose_calendar_changes",
                }
                and "plan_route_between_places" in required_sequence
                and "propose_calendar_changes" in required_sequence
            )
            reasoning_tool_step = required_name in reasoning_tool_names
            decision_model = (
                model
                if reasoning_tool_step
                else fast_decision_model
            )
            active_model = _tagged(
                decision_model.bind_tools(
                    required_or_question_tools,
                    **(
                        {}
                        if linked_trip_step or reasoning_tool_step
                        else {"tool_choice": "required"}
                    ),
                ),
                "floris:tool-decision",
            )
        else:
            reasoning_tool_step = required_name in reasoning_tool_names
            decision_model = (
                model
                if reasoning_tool_step
                else fast_decision_model
            )
            active_model = (
                _tagged(
                    decision_model.bind_tools(
                        tools,
                        **(
                            {}
                            if reasoning_tool_step
                            else {"tool_choice": required_name}
                        ),
                    ),
                    "floris:tool-decision",
                )
                if required_name else model_with_tools
            )
        history = flatten_completed_tools_for_model(
            compact_tool_results_for_model(
                bounded_history(runtime_messages),
            ),
        )
        active_system_prompt = tool_stage_prompts.get(
            required_name, system_prompt,
        )
        if tools_closed or not tools:
            active_system_prompt = final_system_prompt
        messages = [SystemMessage(content=active_system_prompt), *history]
        if force_finalize:
            messages.append(SystemMessage(content=text(
                "model.graph.force_finalize", response_language,
            )))
        elif planned_sequence_complete:
            messages.append(SystemMessage(content=text(
                "model.graph.sequence_complete", response_language,
            )))
        elif finalize_after_rich_search:
            messages.append(SystemMessage(content=text(
                "model.graph.search_complete", response_language,
            )))
        if search_only_degraded:
            messages.append(SystemMessage(content=text(
                "model.graph.search_degraded", response_language,
            )))
        response = await active_model.ainvoke(messages)
        if required_name and not getattr(response, "tool_calls", None):
            response = await active_model.ainvoke([
                *messages,
                SystemMessage(content=text(
                    "model.graph.require_tool", response_language,
                    tool_name=required_name,
                )),
            ])
        if not tools_closed and not getattr(response, "tool_calls", None):
            normalized = dsml_tool_calls(getattr(response, "content", ""), allowed_tool_names)
            if normalized:
                response = AIMessage(content="", tool_calls=normalized)
        if required_name and not getattr(response, "tool_calls", None):
            # Some compatible gateways may ignore tool_choice even after the
            # explicit retry. Never expose their premature prose as if the
            # required search, card, route, or side effect had completed.
            route_only_answer = _route_result_with_calendar_degraded(
                route_result_payload, response_language,
            )
            if (
                route_only_answer
                and required_name == "propose_calendar_changes"
            ):
                return {"messages": [AIMessage(content=route_only_answer)]}
            return {"messages": [AIMessage(content=blocked_capability_response(
                [required_name],
                response_language,
                configured=True,
            ))]}
        response_tool_calls = list(getattr(response, "tool_calls", None) or [])
        if not tools_closed and response_tool_calls:
            filtered_tool_calls = []
            suppressed_rich_search = False
            suppressed_duplicate = False
            suppressed_out_of_stage = False
            used_tool_name_set = set(used_tool_names)
            accepted_signatures = set(seen_tool_call_signatures)
            accepted_single_use_names = set(used_tool_name_set)
            stage_allowed_tool_names = (
                {
                    required_name,
                    *(
                        {"ask_user_clarification"}
                        if allow_stage_clarification
                        else set()
                    ),
                }
                if required_name
                else allowed_tool_names
            )
            for tool_call in response_tool_calls:
                name = tool_call.get("name", "") if isinstance(tool_call, dict) else ""
                signature = _tool_call_signature(tool_call) if isinstance(tool_call, dict) else ""
                if name not in stage_allowed_tool_names:
                    suppressed_out_of_stage = True
                    logging.info(
                        "suppressed out-of-stage tool call name=%s required=%s",
                        name,
                        required_name,
                    )
                    continue
                if (
                    signature in accepted_signatures
                    or (name in TURN_SINGLE_USE_TOOLS and name in accepted_single_use_names)
                ):
                    suppressed_duplicate = True
                    logging.info("suppressed repeated tool call name=%s", name)
                    continue
                if name == "rich_search":
                    if rich_search_used:
                        suppressed_rich_search = True
                        continue
                    rich_search_used = True
                filtered_tool_calls.append(tool_call)
                if signature:
                    accepted_signatures.add(signature)
                if name in TURN_SINGLE_USE_TOOLS:
                    accepted_single_use_names.add(name)
            if suppressed_rich_search or suppressed_duplicate or suppressed_out_of_stage:
                if filtered_tool_calls:
                    response = response.model_copy(update={"tool_calls": filtered_tool_calls})
                elif required_name and suppressed_out_of_stage:
                    response = await active_model.ainvoke([
                        *messages,
                        SystemMessage(content=text(
                            "model.graph.stage_tool_only", response_language,
                            tool_name=required_name,
                            clarification_clause=text(
                                "model.graph.clarification_clause",
                                response_language,
                            ) if "ask_user_clarification" in stage_allowed_tool_names else text(
                                "model.graph.sentence_end", response_language,
                            ),
                        )),
                    ])
                else:
                    response = await public_model.ainvoke([
                        SystemMessage(content=final_system_prompt),
                        *history,
                        SystemMessage(content=text(
                            "model.graph.duplicate_tool", response_language,
                        )),
                    ])
        if force_finalize and not public_content(getattr(response, "content", "")).strip():
            # Some provider models keep imitating their previous DSML transport
            # after tools are unbound. One clean retry yields prose without
            # exposing a placeholder or inventing results.
            response = await public_model.ainvoke([
                SystemMessage(content=final_system_prompt),
                *history,
                SystemMessage(content=text(
                    "model.graph.final_only", response_language,
                )),
            ])
            if not public_content(getattr(response, "content", "")).strip():
                response = AIMessage(content=text(
                    "chat.fallback.insufficient", response_language,
                ))
        if (
            used_tool_names
            and "ask_user_clarification" not in used_tool_names
            and not getattr(response, "tool_calls", None)
            and not public_content(getattr(response, "content", "")).strip()
        ):
            # Empty answer turns are not limited to the recursion-budget path.
            # Some OpenAI-compatible providers emit an empty assistant message
            # immediately after a successful tool result. Give that completed
            # tool history one clean, tool-free synthesis pass so a valid route
            # or calendar proposal cannot collapse into the generic
            # “模型未返回有效回答” terminal error.
            response = await public_model.ainvoke([
                SystemMessage(content=final_system_prompt),
                *history,
                SystemMessage(content=text(
                    "model.graph.final_synthesis", response_language,
                )),
            ])
        if not getattr(response, "tool_calls", None) and not public_content(getattr(response, "content", "")).strip():
            fallback = (
                action_completion_fallback(runtime_messages, response_language)
                or tool_failure_fallback(runtime_messages, response_language)
                or tool_result_fallback(runtime_messages, response_language)
            )
            if fallback:
                response = AIMessage(content=fallback)
        return {"messages": [response]}

    def should_continue(state: MessagesState) -> Literal["tools", "__end__"]:
        last = state["messages"][-1]
        return "tools" if getattr(last, "tool_calls", None) else END

    graph = StateGraph(MessagesState)
    graph.add_node(
        "agent",
        agent_node,
        retry_policy=RetryPolicy(
            initial_interval=0.4,
            backoff_factor=2.0,
            max_interval=1.5,
            max_attempts=2,
            jitter=True,
            retry_on=_retry_model_node,
        ),
    )
    graph.add_edge(START, "agent")
    if tools:
        graph.add_node(
            "tools",
            ToolNode(
                tools,
                handle_tool_errors=_tool_failure_message,
            ),
        )
        graph.add_conditional_edges("agent", should_continue)
        graph.add_edge("tools", "agent")
    else:
        graph.add_edge("agent", END)

    return graph.compile(checkpointer=checkpointer, store=store)
