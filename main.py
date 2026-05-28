from __future__ import annotations

import logging
import os
import threading
import time
import webbrowser
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from core.config import AppSettings, load_settings
from core.execute_pipeline import run_execute_pipeline
from core.im.routes import router as im_router
from core.llm_client import LLMClient
from core.schemas import ExecuteRequest, ExecuteResponse, HealthResponse
from core.ui.routes import router as ui_router

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(name)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

_started_at: float = 0.0
_settings: AppSettings | None = None
_llm: LLMClient | None = None

log = logging.getLogger("openclaw.main")


def _should_open_chat_on_startup(settings: AppSettings) -> bool:
    env = os.environ.get("OPENCLAW_OPEN_CHAT_ON_START", "").strip().lower()
    if env in ("0", "false", "no", "off"):
        return False
    if env in ("1", "true", "yes", "on"):
        return True
    return settings.server.open_chat_on_startup


def _schedule_open_chat(port: int) -> None:
    url = f"http://127.0.0.1:{port}/"
    try:
        webbrowser.open(url)
        log.info("Opened chat UI at %s", url)
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not open chat UI in browser: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _settings, _llm, _started_at
    _started_at = time.monotonic()
    _settings = load_settings()
    _llm = LLMClient(_settings.llm)
    app.state.settings = _settings
    app.state.llm = _llm
    if _should_open_chat_on_startup(_settings):
        threading.Timer(0.8, _schedule_open_chat, args=(_settings.server.port,)).start()
    yield
    _llm = None
    _settings = None
    app.state.settings = None
    app.state.llm = None


app = FastAPI(title="OpenClaw Lite", lifespan=lifespan)
app.include_router(ui_router)
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
