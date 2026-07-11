"""Health, diagnostics, and local backup/restore APIs."""
from __future__ import annotations

import asyncio
import time
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse

from config import settings
from database.connection import get_db
from services.backup_service import BackupValidationError

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/health")
async def system_health(request: Request) -> dict:
    components: dict[str, dict] = {}
    status = "ok"
    try:
        db = await get_db()
        await (await db.execute("SELECT 1")).fetchone()
        components["database"] = {"status": "ok"}
    except Exception as error:
        status = "unhealthy"
        components["database"] = {"status": "error", "error": type(error).__name__}

    supervisor = request.app.state.agent_supervisor
    try:
        supervisor_health = await supervisor.health()
    except Exception as error:
        supervisor_health = {
            "status": "error",
            "running": supervisor.running,
            "worker_id": supervisor.worker_id,
            "error": f"{type(error).__name__}: {error}",
        }
    startup_error = getattr(request.app.state, "supervisor_start_error", "")
    if startup_error:
        supervisor_health["startup_error"] = startup_error
        supervisor_health["status"] = "error"
    components["supervisor"] = supervisor_health
    if supervisor_health.get("status") != "ok" and status == "ok":
        status = "degraded"
    components["model"] = {
        "status": "ready" if settings.llm_ready else "not_configured",
        "provider": settings.llm_provider,
        "model": settings.llm_model,
    }
    components["local_auth"] = {
        "status": "enabled" if settings.local_auth_enabled else "disabled"
    }
    components["restore"] = {
        "status": "restart_required" if request.app.state.backup_service.pending_restore() else "idle"
    }
    return {
        "status": status,
        "version": request.app.version,
        "time": time.time(),
        "components": components,
        "startup_recovery": request.app.state.supervisor_recovery,
        "restore_applied": request.app.state.restore_applied,
    }


@router.post("/backup/export")
async def export_backup(request: Request) -> FileResponse:
    try:
        path = await asyncio.to_thread(request.app.state.backup_service.create_backup)
    except (OSError, BackupValidationError) as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
    return FileResponse(
        path,
        media_type="application/zip",
        filename=Path(path).name,
        headers={"Cache-Control": "no-store"},
    )


@router.post("/backup/restore")
async def stage_backup_restore(
    request: Request,
    file: UploadFile = File(...),
    confirm: bool = Query(default=False),
) -> dict:
    if not confirm:
        raise HTTPException(status_code=400, detail="restore requires confirm=true")
    try:
        result = await asyncio.to_thread(
            request.app.state.backup_service.stage_restore_file, file.file
        )
    except BackupValidationError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return result
