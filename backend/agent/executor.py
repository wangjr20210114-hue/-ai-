"""The single execution entry point for Agent plans and confirmed actions."""
from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import Any, Awaitable, Callable

from agent.cancellation import AgentCancelledError, CancellationToken, RunCancellationService
from agent.context import AgentContext
from agent.errors import (
    AgentErrorInfo,
    BudgetExceededError,
    UnknownSideEffectResult,
    classify_exception,
)
from agent.responder import AgentResponder
from agent.runtime import PersistentRuntime
from application.notification_service import NotificationService
from application.usage_service import UsageService
from database.repositories import provider_call_repo, runtime_repo
from skills.base_skill import (
    SkillExecutionContext,
    SkillExecutionResult,
    SkillRegistry,
)

AgentHandler = Callable[[Any, str, dict[str, Any], list[str]], Awaitable[None]]

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ExecutionResult:
    run_id: str
    status: str
    content: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    action_id: str | None = None


class AgentExecutor:
    def __init__(
        self,
        *,
        registry: SkillRegistry,
        runtime: PersistentRuntime,
        handlers: dict[str, AgentHandler] | None = None,
        responder: AgentResponder | None = None,
        notifications: NotificationService | None = None,
        usage: UsageService | None = None,
        cancellations: RunCancellationService | None = None,
    ) -> None:
        self.registry = registry
        self.runtime = runtime
        self.handlers = handlers or {}
        self.responder = responder or AgentResponder()
        self.notifications = notifications or NotificationService()
        self.usage = usage or UsageService()
        self.cancellations = cancellations or RunCancellationService()

    async def execute_run(
        self,
        run_or_id: dict[str, Any] | str,
        *,
        worker_id: str,
        websocket: Any | None = None,
        context: AgentContext | None = None,
        lease_seconds: int = 120,
    ) -> ExecutionResult:
        run = (
            await self.runtime.get_run(run_or_id)
            if isinstance(run_or_id, str)
            else run_or_id
        )
        if run is None:
            raise runtime_repo.StateConflict("run not found")
        if run["status"] == "queued":
            claimed = await self.runtime.claim_run(run["id"], worker_id, lease_seconds)
            if claimed is None:
                latest = await self.runtime.get_run(run["id"])
                if latest and latest["status"] == "succeeded":
                    return ExecutionResult(run["id"], "succeeded")
                raise runtime_repo.StateConflict("run was claimed by another worker")
            run = claimed
        if run["status"] != "executing":
            raise runtime_repo.StateConflict(f"run is not executable: {run['status']}")

        action = run.get("action") or await runtime_repo.get_action_for_run(run["id"])
        cancellation = await self.cancellations.acquire(run["id"])
        try:
            cancellation.raise_if_cancelled()
            if action is not None:
                return await self.execute_action(action, run=run, websocket=websocket)
            return await self._execute_plan(
                run,
                websocket=websocket,
                context=context,
                cancellation=cancellation,
            )
        except AgentCancelledError:
            latest = await self.runtime.get_run(run["id"])
            if latest is not None and latest["status"] != "cancelled":
                try:
                    latest = await self.runtime.cancel(run["id"], reason="cancelled_during_execution")
                except runtime_repo.StateConflict:
                    latest = await self.runtime.get_run(run["id"])
            if websocket is not None:
                try:
                    from models.schemas import WSMessage
                    await websocket.send_text(
                        WSMessage(
                            type="stream_end",
                            payload={"id": f"ai-{run['id']}", "run_id": run["id"], "cancelled": True},
                        ).model_dump_json()
                    )
                except Exception:
                    pass
            return ExecutionResult(
                run_id=run["id"],
                status="cancelled",
                data={"cancelled": True},
                action_id=action["id"] if action else None,
            )
        except Exception as error:
            latest = await self.runtime.get_run(run["id"])
            if latest is not None and latest["status"] == "cancelled":
                return ExecutionResult(
                    run_id=run["id"],
                    status="cancelled",
                    data={"cancelled": True},
                    action_id=action["id"] if action else None,
                )
            info = classify_exception(error)
            if action is not None:
                await runtime_repo.fail_action_and_run(
                    action["id"],
                    info.message,
                    retryable=info.retryable,
                    reconciliation_required=info.reconciliation_required,
                )
                await self._notify_failure(run, action, info)
            else:
                await self.runtime.fail(run["id"], info.message, retryable=info.retryable)
            if websocket is not None:
                await self.responder.send_error(websocket, info.message, run_id=run["id"])
            return ExecutionResult(
                run_id=run["id"],
                status="failed",
                data={"error": info.message, "error_code": info.code},
                action_id=action["id"] if action else None,
            )
        finally:
            await self.cancellations.release(run["id"])

    async def _execute_plan(
        self,
        run: dict[str, Any],
        *,
        websocket: Any | None,
        context: AgentContext | None,
        cancellation: CancellationToken,
    ) -> ExecutionResult:
        plan = run.get("plan_json") or {}
        intent = str(plan.get("intent") or run.get("intent") or "")
        message = str(plan.get("user_message") or "")
        params = dict(plan.get("params") or {})
        handler = self.handlers.get(intent)
        skill = self.registry.get(intent)
        history = context.history if context else []

        if handler is not None:
            if websocket is None:
                raise RuntimeError(f"interactive handler {intent} requires a live transport")
            await handler(websocket, message, params, history)
            await self.runtime.complete(run["id"], {"intent": intent, "delivery": "stream"})
            return ExecutionResult(run["id"], "succeeded", data={"intent": intent})

        if skill is None:
            raise RuntimeError(f"no skill or handler registered for intent={intent}")
        session_id = str(plan.get("session_id") or "")
        if skill.streaming:
            return await self._execute_streaming_skill(
                run=run,
                skill=skill,
                intent=intent,
                message=message,
                params=params,
                session_id=session_id,
                history=history,
                websocket=websocket,
                cancellation=cancellation,
            )

        result = await skill.execute(message, params, session_id)
        rendered = await skill.render(result)
        if websocket is not None:
            await self.responder.send_skill_result(websocket, rendered, run_id=run["id"])
        await self.runtime.complete(
            run["id"],
            {"intent": intent, "mode": rendered.mode, "data": rendered.data},
        )
        return ExecutionResult(
            run_id=run["id"],
            status="succeeded",
            content=rendered.content,
            data=rendered.data,
        )

    async def _execute_streaming_skill(
        self,
        *,
        run: dict[str, Any],
        skill: Any,
        intent: str,
        message: str,
        params: dict[str, Any],
        session_id: str,
        history: list[str],
        websocket: Any | None,
        cancellation: CancellationToken,
    ) -> ExecutionResult:
        from database.repositories.conversation_repo import save_message
        from models.schemas import WSMessage

        message_id = f"ai-{run['id']}"
        transport_connected = websocket is not None

        async def deliver(message_type: str, payload: dict[str, Any]) -> None:
            nonlocal transport_connected
            if not transport_connected or websocket is None:
                return
            try:
                await websocket.send_text(WSMessage(type=message_type, payload=payload).model_dump_json())
            except Exception as error:  # client disconnect must not cancel model generation
                transport_connected = False
                logger.info(
                    "stream transport disconnected: run=%s error=%s",
                    run["id"],
                    type(error).__name__,
                )
                await self.runtime.append_observation(
                    run["id"],
                    step="stream_transport_disconnected",
                    payload={"schema_version": 1, "message_id": message_id},
                    error=f"{type(error).__name__}: {error}",
                )

        await deliver(
            "stream_start",
            {"id": message_id, "intent": intent, "run_id": run["id"]},
        )
        full_text = ""
        final_data: dict[str, Any] = {}
        final_usage: dict[str, Any] = {}
        provider_request_id = ""
        async for event in skill.stream(
            message,
            params,
            session_id,
            history,
            run_id=run["id"],
            cancellation=cancellation,
        ):
            if event.event_type:
                await deliver(
                    event.event_type,
                    {"id": message_id, "run_id": run["id"], **event.data},
                )
            if event.delta:
                full_text += event.delta
                await deliver(
                    "stream_delta",
                    {"id": message_id, "delta": event.delta, "run_id": run["id"]},
                )
            if event.done:
                if event.content:
                    full_text = event.content
                final_data = dict(event.data)
                final_usage = dict(event.usage)
                provider_request_id = event.provider_request_id

        if not full_text.strip():
            raise RuntimeError(f"streaming skill {intent} produced no content")

        metadata = {
            "schema_version": 1,
            "run_id": run["id"],
            "intent": intent,
            "provider_request_id": provider_request_id,
            "usage": final_usage,
            "data": final_data,
        }
        await save_message(
            session_id,
            message_id,
            "ai",
            full_text,
            metadata,
        )
        history.append(f"AI({intent}): {full_text}")
        await self.runtime.complete(
            run["id"],
            {
                "intent": intent,
                "mode": "stream",
                "message_id": message_id,
                "data": final_data,
                "usage": final_usage,
                "transport_delivered": transport_connected,
            },
        )
        await deliver(
            "stream_end",
            {
                "id": message_id,
                "run_id": run["id"],
                **final_data,
                "data": final_data,
                "usage": final_usage,
            },
        )
        return ExecutionResult(
            run_id=run["id"],
            status="succeeded",
            content=full_text,
            data={
                **final_data,
                "message_id": message_id,
                "usage": final_usage,
                "transport_delivered": transport_connected,
            },
        )

    async def execute_action(
        self,
        action: dict[str, Any],
        *,
        run: dict[str, Any],
        websocket: Any | None = None,
    ) -> ExecutionResult:
        if action["status"] == "succeeded":
            result = action.get("result_json") or {}
            return ExecutionResult(
                run_id=run["id"],
                status="succeeded",
                content=str(result.get("content") or ""),
                data=dict(result.get("data") or {}),
                action_id=action["id"],
            )
        action = await runtime_repo.start_action_execution(action["id"])
        skill = self.registry.get(action["skill_name"])
        if skill is None or not skill.side_effect or skill.action_input_model is None:
            raise RuntimeError(f"side-effect skill is unavailable: {action['skill_name']}")
        snapshot = action.get("snapshot") or {}
        input_model = skill.action_input_model.model_validate(snapshot.get("input") or {})
        estimated_cost = float((snapshot.get("confirmation") or {}).get("estimated_cost_cny") or 0)
        budget = await self.usage.check_budget(estimated_cost)
        if not budget["allowed"]:
            raise BudgetExceededError(
                f"今日成本预算不足：当前 {budget['current_cost']:.2f} 元，预计执行后 {budget['projected_cost']:.2f} 元，预算 {budget['daily_limit']:.2f} 元"
            )
        provider_call, created = await provider_call_repo.begin_call(
            call_id=f"call-{action['id']}",
            run_id=run["id"],
            action_id=action["id"],
            provider=skill.name,
            operation="execute_action",
            idempotency_key=action["idempotency_key"],
            request_hash=action["snapshot_hash"],
        )
        if not created:
            if provider_call["status"] == "succeeded":
                result_payload = dict(provider_call.get("response_json") or {})
                completed_action, _ = await runtime_repo.recover_action_success(
                    action["id"],
                    result_payload,
                    provider_request_id=str(provider_call.get("external_resource_id") or ""),
                )
                recovered_result = SkillExecutionResult(
                    content=str(result_payload.get("content") or ""),
                    data=dict(result_payload.get("data") or {}),
                    usage=dict(result_payload.get("usage") or {}),
                    provider_request_id=str(provider_call.get("external_resource_id") or ""),
                )
                await self._run_post_success_tasks(
                    run=run,
                    action=action,
                    skill=skill,
                    skill_result=recovered_result,
                    estimated_cost=estimated_cost,
                    websocket=websocket,
                )
                return ExecutionResult(
                    run_id=run["id"],
                    status="succeeded",
                    content=recovered_result.content,
                    data=completed_action.get("result_json") or result_payload,
                    action_id=action["id"],
                )
            if provider_call["status"] == "failed":
                raise RuntimeError(provider_call.get("error") or "external action previously failed")
            if provider_call["status"] == "started":
                await provider_call_repo.mark_started_call_unknown(
                    provider_call["id"],
                    "duplicate execution encountered an unfinished provider call",
                )
            raise UnknownSideEffectResult(
                "外部请求已经开始，但结果尚未得到安全确认；系统不会自动重复执行"
            )

        try:
            skill_result: SkillExecutionResult = await skill.execute_action(
                input_model,
                SkillExecutionContext(
                    run_id=run["id"],
                    action_id=action["id"],
                    idempotency_key=action["idempotency_key"],
                ),
            )
        except Exception as error:
            info = classify_exception(error)
            uncertain = info.reconciliation_required or isinstance(
                error, (TimeoutError, ConnectionError, OSError)
            ) or "timeout" in type(error).__name__.lower()
            await provider_call_repo.fail_call(
                provider_call["id"],
                f"{type(error).__name__}: {error}",
                result_unknown=uncertain,
            )
            if uncertain:
                raise UnknownSideEffectResult(
                    "外部服务调用中断，操作可能已经成功；为避免重复副作用，系统已转入人工核对"
                ) from error
            raise

        result_payload = {
            "content": skill_result.content,
            "data": skill_result.data,
            "usage": skill_result.usage,
        }
        await provider_call_repo.complete_call(
            provider_call["id"],
            response=result_payload,
            external_resource_id=skill_result.provider_request_id,
        )
        completed_action, _ = await runtime_repo.complete_action_and_run(
            action["id"],
            result_payload,
            provider_request_id=skill_result.provider_request_id,
        )

        # The external side effect and its durable result are already committed.
        # Telemetry, notification delivery, or a disconnected WebSocket must never
        # turn a succeeded action back into failed or trigger a duplicate retry.
        await self._run_post_success_tasks(
            run=run,
            action=action,
            skill=skill,
            skill_result=skill_result,
            estimated_cost=estimated_cost,
            websocket=websocket,
        )
        return ExecutionResult(
            run_id=run["id"],
            status="succeeded",
            content=skill_result.content,
            data=completed_action.get("result_json") or result_payload,
            action_id=action["id"],
        )

    async def _run_post_success_tasks(
        self,
        *,
        run: dict[str, Any],
        action: dict[str, Any],
        skill: Any,
        skill_result: SkillExecutionResult,
        estimated_cost: float,
        websocket: Any | None,
    ) -> None:
        tasks: list[tuple[str, Awaitable[Any]]] = [
            (
                "usage_recording",
                self.usage.record_usage(
                    run_id=run["id"],
                    provider=skill.name,
                    operation="execute_action",
                    units=float(skill_result.usage.get("image_generations") or 0),
                    estimated_cost=estimated_cost,
                ),
            ),
            (
                "success_notification",
                self.notifications.create_notification(
                    notification_type="action.succeeded",
                    title=f"{skill.action_label}完成",
                    body=skill_result.content,
                    dedup_key=f"action-result:{action['id']}:succeeded",
                    run_id=run["id"],
                    event_id=run.get("event_id"),
                    action_id=action["id"],
                    reason="confirmed_action_completed",
                    source_label=skill.name,
                    priority=10,
                    metadata={"result": skill_result.data},
                ),
            ),
        ]
        if websocket is not None:
            from skills.base_skill import SkillResult

            tasks.append(
                (
                    "transport_delivery",
                    self.responder.send_skill_result(
                        websocket,
                        SkillResult(
                            intent=skill.name,
                            mode="immediate",
                            content=skill_result.content,
                            icon=skill.icon,
                            action_label=skill.action_label,
                            data=skill_result.data,
                        ),
                        run_id=run["id"],
                    ),
                )
            )

        for step, operation in tasks:
            try:
                await operation
            except Exception as error:  # noqa: BLE001 - post-commit isolation boundary
                logger.exception("post-success task failed: run=%s step=%s", run["id"], step)
                try:
                    await self.runtime.append_observation(
                        run["id"],
                        step=f"{step}_failed",
                        payload={"schema_version": 1, "non_fatal": True},
                        error=f"{type(error).__name__}: {error}",
                    )
                except Exception:  # pragma: no cover - logging is the final fallback
                    logger.exception("failed to persist post-success observation")

    async def reconcile_unknown_side_effect(
        self,
        action: dict[str, Any],
    ) -> dict[str, Any]:
        """Conservative reconciliation hook.

        Current providers do not expose a reliable lookup-by-idempotency API, so
        unknown results are surfaced to the user instead of being retried.
        """
        provider_call = await provider_call_repo.get_call_for_action(action["id"])
        if provider_call is not None and provider_call["status"] == "succeeded":
            result_payload = dict(provider_call.get("response_json") or {})
            await runtime_repo.recover_action_success(
                action["id"],
                result_payload,
                provider_request_id=str(provider_call.get("external_resource_id") or ""),
            )
            await self.notifications.create_notification(
                notification_type="action.reconciled",
                title="外部操作结果已自动恢复",
                body=str(result_payload.get("content") or "外部操作已成功，运行记录已恢复。"),
                dedup_key=f"action-reconcile:{action['id']}:succeeded",
                run_id=action["run_id"],
                action_id=action["id"],
                reason="provider_call_ledger_succeeded",
                source_label=action["skill_name"],
                priority=40,
            )
            return {"status": "succeeded", "action_id": action["id"], "automatic": True}

        if provider_call is not None and provider_call["status"] == "failed":
            error = str(provider_call.get("error") or "外部服务已确认调用失败")
            await runtime_repo.resolve_action_reconciliation_failure(action["id"], error)
            return {"status": "failed", "action_id": action["id"], "automatic": True}

        if provider_call is not None and provider_call["status"] == "started":
            provider_call = await provider_call_repo.mark_started_call_unknown(
                provider_call["id"],
                "worker lease expired before a durable provider result was recorded",
            )

        await self.notifications.create_notification(
            notification_type="action.reconciliation_required",
            title="需要核对外部操作结果",
            body="外部请求可能已经成功，系统不会自动重试。请核对腾讯会议或生图结果后再决定。",
            dedup_key=f"action-reconcile:{action['id']}:unknown",
            run_id=action["run_id"],
            action_id=action["id"],
            reason="unknown_side_effect_result",
            source_label=action["skill_name"],
            priority=100,
            metadata={
                "provider_call_id": provider_call.get("id") if provider_call else None,
                "provider_call_status": provider_call.get("status") if provider_call else "missing",
            },
        )
        return {"status": "unknown", "action_id": action["id"], "automatic": False}

    async def _notify_failure(
        self,
        run: dict[str, Any],
        action: dict[str, Any],
        error: AgentErrorInfo,
    ) -> None:
        await self.notifications.create_notification(
            notification_type="action.failed",
            title=f"{action['skill_name']} 执行失败",
            body=error.message,
            dedup_key=f"action-result:{action['id']}:failed:{error.code}",
            run_id=run["id"],
            event_id=run.get("event_id"),
            action_id=action["id"],
            reason=error.code,
            source_label=action["skill_name"],
            priority=80,
            metadata={"reconciliation_required": error.reconciliation_required},
        )
