from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from core.config import AppSettings, load_settings
from core.execute_pipeline import run_execute_pipeline
from core.im.routes import router as im_router
from core.llm_client import LLMClient
from core.schemas import ExecuteRequest, ExecuteResponse, HealthResponse

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(name)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

_started_at: float = 0.0
_settings: AppSettings | None = None
_llm: LLMClient | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _settings, _llm, _started_at
    _started_at = time.monotonic()
    _settings = load_settings()
    _llm = LLMClient(_settings.llm)
    app.state.settings = _settings
    app.state.llm = _llm
    yield
    _llm = None
    _settings = None
    app.state.settings = None
    app.state.llm = None


app = FastAPI(title="OpenClaw Lite", lifespan=lifespan)
app.include_router(im_router)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    uptime = int(time.monotonic() - _started_at)
    return HealthResponse(status="ok", version="1.0.0", uptime=uptime)


@app.post("/execute", response_model=ExecuteResponse)
async def execute(body: ExecuteRequest) -> ExecuteResponse:
    if _settings is None or _llm is None:
        raise HTTPException(status_code=503, detail="Service not ready")
    return await run_execute_pipeline(_settings, _llm, body)
