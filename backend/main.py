"""FastAPI application entry point."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from security.local_auth import LocalAccessTokenService, LocalTokenMiddleware

from agent import register_all_skills
from agent.cancellation import RunCancellationService
from agent.executor import AgentExecutor
from agent.intent_router import IntentRouter
from agent.runtime import PersistentRuntime
from agent.scheduler import AgentScheduler, JobExecutionResult
from agent.collectors.schedule_collector import ScheduleCollector
from agent.collectors.file_collector import FileCollector
from agent.collectors.travel_weather_collector import TravelWeatherCollector
from agent.supervisor import AgentSupervisor
from api.agent_routes import router as agent_router
from api.conversation_routes import router as conversation_router
from api.file_routes import router as file_router
from api.feedback_routes import router as feedback_router
from api.memory_routes import router as memory_router
from api.setup_routes import router as setup_router
from api.system_routes import router as system_router
from api.usage_routes import router as usage_router
from api.paper_routes import router as paper_router
from api.routes import router as rest_router
from api.websocket import router as ws_router
from application.action_service import ActionService
from application.feedback_service import FeedbackService
from application.memory_service import MemoryService
from application.notification_service import NotificationService
from application.proactive_event_service import ProactiveEventService
from application.usage_service import UsageService
from config import settings
from database.connection import close_db
from database.init_db import init_db
from database.repositories import job_repo
from services.backup_service import BackupService
from services.hunyuan_service import hunyuan_service
from services.model_gateway import ModelGateway
from services.map_service import map_service
from skills.base_skill import SkillRegistry
from observability.request_logging import RequestLoggingMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    local_access_token_service = LocalAccessTokenService()
    local_access_token_service.initialize()
    app.state.local_access_token_service = local_access_token_service
    backup_service = BackupService()
    restore_applied = await asyncio.to_thread(backup_service.apply_pending_restore)
    await init_db()

    runtime = PersistentRuntime()
    action_service = ActionService()
    notification_service = NotificationService()
    memory_service = MemoryService()
    feedback_service = FeedbackService()
    usage_service = UsageService()
    run_cancellation_service = RunCancellationService()
    model_gateway = ModelGateway(usage=usage_service)
    registry = SkillRegistry()
    register_all_skills(registry, model_gateway=model_gateway)
    intent_router = IntentRouter(registry, model_gateway)
    background_executor = AgentExecutor(
        registry=registry,
        runtime=runtime,
        notifications=notification_service,
        usage=usage_service,
        cancellations=run_cancellation_service,
    )
    proactive_service = ProactiveEventService(
        runtime=runtime,
        notifications=notification_service,
    )
    schedule_collector = ScheduleCollector(lookahead_minutes=30)
    weather_collector = TravelWeatherCollector(horizon_days=7)
    file_collector = FileCollector()

    async def collect_schedules(job: dict) -> JobExecutionResult:
        batch = await schedule_collector.collect(job.get("checkpoint") or {})
        for signal in batch.events:
            await proactive_service.process_signal(signal.to_dict())
        return JobExecutionResult(
            checkpoint={
                **batch.next_checkpoint,
                "signals_processed": len(batch.events),
                "diagnostics": batch.diagnostics,
            },
            next_run_at=batch.next_run_at,
        )

    async def collect_travel_weather(job: dict) -> JobExecutionResult:
        batch = await weather_collector.collect(job.get("checkpoint") or {})
        for signal in batch.events:
            await proactive_service.process_signal(signal.to_dict())
        return JobExecutionResult(
            checkpoint={
                **batch.next_checkpoint,
                "signals_processed": len(batch.events),
                "diagnostics": batch.diagnostics,
            },
            next_run_at=batch.next_run_at,
        )

    scheduler = AgentScheduler({
        "collector.schedule": collect_schedules,
        "collector.travel_weather": collect_travel_weather,
    })
    await job_repo.upsert_job(
        "collector:schedule",
        "collector.schedule",
        {"lookahead_minutes": 30},
        next_run_at=__import__("time").time() + 1,
        interval_seconds=60,
        max_attempts=3,
    )
    await job_repo.upsert_job(
        "collector:travel-weather",
        "collector.travel_weather",
        {"horizon_days": 7},
        next_run_at=__import__("time").time() + 5,
        interval_seconds=1800,
        max_attempts=3,
    )
    supervisor = AgentSupervisor(
        runtime=runtime,
        executor=background_executor,
        scheduler=scheduler,
    )

    app.state.backup_service = backup_service
    app.state.restore_applied = restore_applied
    app.state.skill_registry = registry
    app.state.agent_runtime = runtime
    app.state.action_service = action_service
    app.state.notification_service = notification_service
    app.state.memory_service = memory_service
    app.state.feedback_service = feedback_service
    app.state.usage_service = usage_service
    app.state.run_cancellation_service = run_cancellation_service
    app.state.model_gateway = model_gateway
    app.state.intent_router = intent_router
    app.state.proactive_event_service = proactive_service
    app.state.file_collector = file_collector
    app.state.agent_scheduler = scheduler
    app.state.agent_supervisor = supervisor
    app.state.supervisor_start_error = ""
    try:
        app.state.supervisor_recovery = await supervisor.start()
    except Exception as error:
        # Database initialization remains fail-fast, but a background component
        # failure must leave the local UI available with an explicit health state.
        app.state.supervisor_start_error = f"{type(error).__name__}: {error}"
        app.state.supervisor_recovery = {
            "status": "failed",
            "error": app.state.supervisor_start_error,
        }

    try:
        yield
    finally:
        await supervisor.stop()
        await model_gateway.close()
        await hunyuan_service.close()
        await map_service.close()
        await close_db()


app = FastAPI(title="元宝主动式 Agent", version="4.0.0", lifespan=lifespan)

app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(LocalTokenMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Agent-Token", "X-Request-ID"],
)

app.include_router(setup_router)
app.include_router(system_router)
app.include_router(rest_router)
app.include_router(paper_router)
app.include_router(conversation_router)
app.include_router(file_router)
app.include_router(agent_router)
app.include_router(memory_router)
app.include_router(feedback_router)
app.include_router(usage_router)
app.include_router(ws_router)


@app.get("/")
async def root() -> dict:
    return {
        "name": "元宝主动式 Agent",
        "version": "4.0.0",
        "architecture": "persistent-event-run-action-supervisor",
        "llm_provider": settings.llm_provider,
        "llm_model": settings.llm_model,
        "llm_ready": settings.llm_ready,
        "map_ready": bool(settings.tencent_map_key),
    }


if __name__ == "__main__":
    uvicorn.run("main:app", host=settings.app_host, port=settings.app_port, reload=True)
