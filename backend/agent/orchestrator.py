"""Persistent Agent orchestrator.

Owns the decision pipeline only:
classify -> plan -> policy -> queue/confirm.  All actual execution is delegated to
``AgentExecutor`` so WebSocket, REST and background workers share one path.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from agent.context import AgentContext
from agent.contracts import (
    AgentPlan,
    AgentResponse,
    ConfirmationPolicy,
    FailurePolicy,
    PermissionLevel,
    ResponseType,
    RiskLevel,
    plan_to_dict,
)
from agent.events import AgentEvent
from agent.executor import AgentExecutor
from agent.intent_router import IntentRouter
from agent.policy import AgentPolicy
from agent.responder import AgentResponder
from agent.runtime import PersistentRuntime
from application.action_service import ActionService
from skills.base_skill import SkillRegistry

AgentHandler = Callable[[Any, str, dict[str, Any], list[str]], Awaitable[None]]


class AgentOrchestrator:
    def __init__(
        self,
        *,
        registry: SkillRegistry,
        executor: AgentExecutor,
        action_service: ActionService,
        handlers: dict[str, AgentHandler] | None = None,
        fallback_intent: str = "chat",
        policy: AgentPolicy | None = None,
        runtime: PersistentRuntime | None = None,
        responder: AgentResponder | None = None,
        intent_router: IntentRouter | None = None,
    ) -> None:
        self.registry = registry
        self.handlers = handlers or {}
        self.fallback_intent = fallback_intent
        self.policy = policy or AgentPolicy()
        self.runtime = runtime or PersistentRuntime()
        self.responder = responder or AgentResponder()
        self.executor = executor
        self.action_service = action_service
        self.intent_router = intent_router

    async def handle_user_activity(
        self,
        websocket: Any,
        event: AgentEvent,
        context: AgentContext,
        *,
        run_id: str,
    ) -> AgentResponse:
        return await self.handle_event(websocket, event, context, run_id=run_id)

    async def handle_event(
        self,
        websocket: Any | None,
        event: AgentEvent,
        context: AgentContext,
        *,
        run_id: str,
    ) -> AgentResponse:
        try:
            intent_result = await self._classify(run_id, event, context)
            plan = await self._plan(run_id, event, intent_result)
            decision = self.policy.decide(plan, context)
            await self.runtime.transition(
                run_id,
                "planned",
                "policy_checked",
                step="policy_checked",
                payload={
                    "allowed": decision.allowed,
                    "requires_confirmation": decision.requires_confirmation,
                    "reason": decision.reason,
                    "permission_level": decision.permission_level.value,
                    "risk_level": decision.risk_level.value,
                },
            )

            if not decision.allowed:
                return await self._respond_denied(websocket, run_id, plan, decision.reason)

            skill = self.registry.get(plan.intent)
            if decision.requires_confirmation:
                if skill is None or not skill.side_effect:
                    raise RuntimeError(
                        f"confirmation was requested for a non-action skill: {plan.intent}"
                    )
                await self.runtime.transition(
                    run_id,
                    "policy_checked",
                    "waiting_confirmation",
                    step="confirmation_required",
                    payload={"reason": decision.reason},
                )
                action = await self.action_service.create_pending_action(run_id, plan, skill)
                return await self._respond_suggestion(websocket, run_id, plan, action)

            # PermissionLevel.SUGGEST is a rendering mode, not an execution bypass.
            # Read-only plans still travel through the single executor.
            await self.runtime.transition(
                run_id,
                "policy_checked",
                "queued",
                step="run_queued",
                payload={"execution_lane": "interactive"},
            )
            result = await self.executor.execute_run(
                run_id,
                worker_id=f"interactive:{event.session_id}",
                websocket=websocket,
                context=context,
            )
            return AgentResponse(
                run_id=run_id,
                response_type=(
                    ResponseType.ERROR if result.status == "failed" else ResponseType.SKILL_RESULT
                ),
                payload={"status": result.status, "data": result.data},
                handled_by_transport=websocket is not None,
            )
        except Exception as error:
            await self.runtime.fail_if_possible(run_id, f"{type(error).__name__}: {error}")
            if websocket is not None:
                await self.responder.send_error(
                    websocket,
                    f"Agent 执行失败：{type(error).__name__}: {error}",
                    run_id=run_id,
                )
            return AgentResponse(
                run_id=run_id,
                response_type=ResponseType.ERROR,
                payload={"error": str(error), "error_type": type(error).__name__},
                handled_by_transport=websocket is not None,
            )

    async def _classify(
        self,
        run_id: str,
        event: AgentEvent,
        context: AgentContext,
    ) -> dict[str, Any]:
        if self.intent_router is not None:
            result = await self.intent_router.classify(
                event.text,
                context.history,
                run_id=run_id,
                conversation_id=event.session_id,
            )
        else:
            from agent.intent_router import classify_intent

            result = await classify_intent(event.text, context.history)
        intent = str(result.get("intent") or self.fallback_intent)
        params = dict(result.get("params") or {})
        await self.runtime.set_classification(
            run_id,
            intent,
            {"intent": intent, "params": params, "raw": result},
        )
        return {"intent": intent, "params": params, "raw": result}

    async def _plan(
        self,
        run_id: str,
        event: AgentEvent,
        intent_result: dict[str, Any],
    ) -> AgentPlan:
        intent = str(intent_result.get("intent") or self.fallback_intent)
        params = dict(intent_result.get("params") or {})
        # Transport preferences are not intent-classification inputs.  Copy only
        # explicitly supported client controls instead of merging the arbitrary
        # event payload into a persisted execution plan.
        if "web_search" in event.payload:
            params["web_search"] = bool(event.payload["web_search"])
        skill = self.registry.get(intent)

        if skill is None and intent not in self.handlers:
            intent = self.fallback_intent
            params = {}
            skill = self.registry.get(intent)

        if skill is None:
            plan = AgentPlan(
                run_id=run_id,
                session_id=event.session_id,
                event_type=event.type,
                user_message=event.text,
                intent=intent,
                skill_name=intent,
                params=params,
                permission_level=PermissionLevel.AUTO,
                risk_level=RiskLevel.LOW,
                confirmation=ConfirmationPolicy(required=False),
                failure_policy=FailurePolicy(max_retries=0, user_visible=True),
                steps=["respond"],
                rationale="registered_transport_handler",
            )
        else:
            plan = await skill.create_plan(
                run_id=run_id,
                session_id=event.session_id,
                event_type=event.type,
                message=event.text,
                params=params,
                rationale="classified_by_intent_router",
            )

        execution_lane = "background" if skill is not None and skill.side_effect else "interactive"
        await self.runtime.set_plan(
            run_id,
            plan_to_dict(plan),
            execution_lane=execution_lane,
            max_attempts=plan.failure_policy.max_retries + 1,
        )
        return plan

    async def _respond_suggestion(
        self,
        websocket: Any | None,
        run_id: str,
        plan: AgentPlan,
        action: dict[str, Any],
    ) -> AgentResponse:
        skill = self.registry.get(plan.intent)
        if skill is None:
            return await self._respond_denied(websocket, run_id, plan, "skill_unavailable")
        result = await skill.suggest(plan.user_message, plan.params)
        snapshot = action.get("snapshot") or {}
        result.data = {
            **result.data,
            "run_id": run_id,
            "action_id": action["id"],
            "action_version": action["version"],
            "action_status": action["status"],
            "expires_at": action.get("expires_at"),
            "confirmation": snapshot.get("confirmation") or {},
            "action_input": snapshot.get("input") or {},
            "permission_level": plan.permission_level.value,
            "risk_level": plan.risk_level.value,
            "requires_confirmation": True,
            "plan_steps": list(plan.steps),
        }
        if websocket is not None:
            await self.responder.send_skill_result(websocket, result, run_id=run_id)
        await self.runtime.append_observation(
            run_id,
            step="suggestion_sent",
            payload={"action_id": action["id"], "version": action["version"]},
        )
        return AgentResponse(
            run_id=run_id,
            response_type=ResponseType.SUGGESTION,
            payload={
                "intent": plan.intent,
                "action_id": action["id"],
                "version": action["version"],
            },
            handled_by_transport=websocket is not None,
        )

    async def _respond_denied(
        self,
        websocket: Any | None,
        run_id: str,
        plan: AgentPlan,
        reason: str,
    ) -> AgentResponse:
        await self.runtime.transition(
            run_id,
            "policy_checked",
            "skipped",
            step="policy_denied",
            payload={"reason": reason, "intent": plan.intent},
        )
        message = f"这个动作暂时不能自动执行：{reason}"
        if websocket is not None:
            await self.responder.send_error(websocket, message, run_id=run_id)
        return AgentResponse(
            run_id=run_id,
            response_type=ResponseType.ERROR,
            payload={"reason": reason},
            handled_by_transport=websocket is not None,
        )
