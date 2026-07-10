"""Agent orchestrator.

Owns the full pipeline:
classify -> plan -> policy -> execute -> observe -> respond.

The transport layer (WebSocket/REST/background worker) should only turn incoming
signals into AgentEvent and pass them here.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from agent.context import AgentContext
from agent.contracts import (
    AgentPlan,
    AgentResponse,
    ConfirmationPolicy,
    ExecutionStatus,
    FailurePolicy,
    PermissionLevel,
    ResponseType,
    RiskLevel,
)
from agent.events import AgentEvent
from agent.policy import AgentPolicy
from agent.responder import AgentResponder
from agent.runtime import AgentRun, AgentRuntime
from skills.base_skill import BaseSkill, SkillRegistry

AgentHandler = Callable[[Any, str, dict[str, Any], list[str]], Awaitable[None]]


class AgentOrchestrator:
    def __init__(
        self,
        *,
        registry: SkillRegistry,
        handlers: dict[str, AgentHandler] | None = None,
        fallback_intent: str = "chat",
        policy: AgentPolicy | None = None,
        runtime: AgentRuntime | None = None,
        responder: AgentResponder | None = None,
    ) -> None:
        self.registry = registry
        self.handlers = handlers or {}
        self.fallback_intent = fallback_intent
        self.policy = policy or AgentPolicy()
        self.runtime = runtime or AgentRuntime()
        self.responder = responder or AgentResponder()

    async def handle_user_activity(
        self,
        websocket: Any,
        event: AgentEvent,
        context: AgentContext,
    ) -> AgentResponse:
        return await self.handle_event(websocket, event, context)

    async def handle_event(
        self,
        websocket: Any,
        event: AgentEvent,
        context: AgentContext,
    ) -> AgentResponse:
        run = self.runtime.start_run(event)
        try:
            intent_result = await self._classify(run, event, context)
            plan = await self._plan(run, event, context, intent_result)
            decision = self.policy.decide(plan, context)
            self.runtime.observe(
                run,
                ExecutionStatus.POLICY_CHECKED,
                intent=plan.intent,
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
                response = await self._respond_denied(websocket, run, plan, decision.reason)
                self.runtime.finish(run, ExecutionStatus.SKIPPED)
                return response

            if decision.requires_confirmation or plan.permission_level == PermissionLevel.SUGGEST:
                response = await self._respond_suggestion(websocket, run, plan)
                self.runtime.finish(run, ExecutionStatus.WAITING_CONFIRMATION)
                return response

            response = await self._execute(websocket, run, plan, context)
            self.runtime.finish(run, ExecutionStatus.SUCCEEDED)
            return response
        except Exception as e:
            if type(e).__name__ == "QuotaExhaustedError":
                raise
            self.runtime.finish(run, ExecutionStatus.FAILED, error=f"{type(e).__name__}: {e}")
            await self.responder.send_error(websocket, f"Agent 执行失败：{type(e).__name__}: {e}", run_id=run.run_id)
            return AgentResponse(
                run_id=run.run_id,
                response_type=ResponseType.ERROR,
                payload={"error": str(e), "error_type": type(e).__name__},
                handled_by_transport=True,
            )

    async def _classify(self, run: AgentRun, event: AgentEvent, context: AgentContext) -> dict[str, Any]:
        self.runtime.observe(run, ExecutionStatus.CLASSIFIED, step="classify_started")
        from agent.intent_router import classify_intent

        result = await classify_intent(event.text, context.history)
        intent = result.get("intent", self.fallback_intent)
        params = result.get("params", {}) or {}
        self.runtime.observe(
            run,
            ExecutionStatus.CLASSIFIED,
            intent=intent,
            step="classify_finished",
            payload={"intent": intent, "params": params},
        )
        return {"intent": intent, "params": params, "raw": result}

    async def _plan(
        self,
        run: AgentRun,
        event: AgentEvent,
        context: AgentContext,
        intent_result: dict[str, Any],
    ) -> AgentPlan:
        intent = intent_result.get("intent") or self.fallback_intent
        params = intent_result.get("params", {}) or {}
        skill = self.registry.get(intent)

        if skill is None and intent not in self.handlers:
            intent = self.fallback_intent
            params = {}
            skill = self.registry.get(intent)

        if skill is None:
            plan = AgentPlan(
                run_id=run.run_id,
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
                rationale="transport_handler_without_registered_skill",
            )
        else:
            plan = await skill.create_plan(
                run_id=run.run_id,
                session_id=event.session_id,
                event_type=event.type,
                message=event.text,
                params=params,
                rationale="classified_by_intent_router",
            )

        self.runtime.attach_plan(run, plan)
        return plan

    async def _execute(
        self,
        websocket: Any,
        run: AgentRun,
        plan: AgentPlan,
        context: AgentContext,
    ) -> AgentResponse:
        self.runtime.observe(run, ExecutionStatus.EXECUTING, intent=plan.intent, step="execute_started")
        skill = self.registry.get(plan.intent)
        handler = self.handlers.get(plan.intent)
        attempts = max(1, plan.failure_policy.max_retries + 1)
        last_error: Exception | None = None

        for attempt in range(1, attempts + 1):
            try:
                self.runtime.observe(
                    run,
                    ExecutionStatus.EXECUTING,
                    intent=plan.intent,
                    step="execute_attempt",
                    payload={"attempt": attempt, "max_attempts": attempts},
                )
                if handler is not None:
                    await handler(websocket, plan.user_message, plan.params, context.history)
                    obs = self.runtime.observe(run, ExecutionStatus.SUCCEEDED, intent=plan.intent, step="handler_completed")
                    return AgentResponse(
                        run_id=run.run_id,
                        response_type=ResponseType.STREAM,
                        handled_by_transport=True,
                        observation=obs,
                    )

                if skill is None:
                    raise RuntimeError(f"No skill or handler registered for intent={plan.intent}")

                result = await skill.execute(plan.user_message, plan.params, plan.session_id)
                rendered = await skill.render(result)
                await self.responder.send_skill_result(websocket, rendered, run_id=run.run_id)
                obs = self.runtime.observe(run, ExecutionStatus.SUCCEEDED, intent=plan.intent, step="skill_completed")
                return AgentResponse(
                    run_id=run.run_id,
                    response_type=ResponseType.SKILL_RESULT,
                    payload={"intent": rendered.intent, "mode": rendered.mode},
                    handled_by_transport=True,
                    observation=obs,
                )
            except Exception as e:
                if type(e).__name__ == "QuotaExhaustedError":
                    raise
                last_error = e
                self.runtime.observe(
                    run,
                    ExecutionStatus.FAILED,
                    intent=plan.intent,
                    step="execute_attempt_failed",
                    payload={"attempt": attempt},
                    error=f"{type(e).__name__}: {e}",
                )

        if skill is not None and last_error is not None and plan.failure_policy.user_visible:
            result = await skill.failure_result(plan.user_message, plan.params, last_error)
            await self.responder.send_skill_result(websocket, result, run_id=run.run_id)
            return AgentResponse(
                run_id=run.run_id,
                response_type=ResponseType.ERROR,
                payload={"error": str(last_error), "error_type": type(last_error).__name__},
                handled_by_transport=True,
            )

        raise last_error or RuntimeError("Agent execution failed")

    async def _respond_suggestion(self, websocket: Any, run: AgentRun, plan: AgentPlan) -> AgentResponse:
        skill = self.registry.get(plan.intent)
        if skill is None:
            return await self._respond_denied(websocket, run, plan, "no_skill_for_suggestion")
        result = await skill.suggest(plan.user_message, plan.params)
        result.data = {
            **result.data,
            "run_id": run.run_id,
            "permission_level": plan.permission_level.value,
            "risk_level": plan.risk_level.value,
            "requires_confirmation": plan.confirmation.required,
            "confirmation_reason": plan.confirmation.reason,
            "plan_steps": plan.steps,
        }
        await self.responder.send_skill_result(websocket, result, run_id=run.run_id)
        obs = self.runtime.observe(run, ExecutionStatus.WAITING_CONFIRMATION, intent=plan.intent, step="suggestion_sent")
        return AgentResponse(
            run_id=run.run_id,
            response_type=ResponseType.SUGGESTION,
            payload={"intent": plan.intent, "permission_level": plan.permission_level.value},
            handled_by_transport=True,
            observation=obs,
        )

    async def _respond_denied(self, websocket: Any, run: AgentRun, plan: AgentPlan, reason: str) -> AgentResponse:
        message = f"这个动作暂时不能自动执行：{reason}"
        await self.responder.send_error(websocket, message, run_id=run.run_id)
        obs = self.runtime.observe(run, ExecutionStatus.SKIPPED, intent=plan.intent, step="denied", message=message)
        return AgentResponse(
            run_id=run.run_id,
            response_type=ResponseType.ERROR,
            payload={"reason": reason},
            handled_by_transport=True,
            observation=obs,
        )