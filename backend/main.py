"""FastAPI 应用入口。"""
from __future__ import annotations

from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import router as rest_router
from api.paper_routes import router as paper_router
from api.conversation_routes import router as conversation_router
from api.file_routes import router as file_router
from api.agent_routes import router as agent_router
from api.websocket import router as ws_router
from config import settings
from database.connection import close_db
from database.init_db import init_db
from services.hunyuan_service import hunyuan_service
from services.map_service import map_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield
    await hunyuan_service.close()
    await map_service.close()
    await close_db()


app = FastAPI(title="元宝 Agent", version="3.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(rest_router)
app.include_router(paper_router)
app.include_router(conversation_router)
app.include_router(file_router)
app.include_router(agent_router)
app.include_router(ws_router)


@app.get("/")
async def root() -> dict:
    return {
        "name": "旅游 Agent",
        "llm_provider": settings.llm_provider,
        "llm_model": settings.llm_model,
        "llm_ready": settings.llm_ready,
        "map_ready": bool(settings.tencent_map_key),
    }


if __name__ == "__main__":
    uvicorn.run("main:app", host=settings.app_host, port=settings.app_port, reload=True)
