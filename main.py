from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from core.config import AppSettings, load_settings
from core.llm_client import LLMClient
from core.parser import parse_user_message
from core.tools import run_tool

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(name)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("openclaw")

_started_at: float = 0.0
_settings: AppSettings | None = None
_llm: LLMClient | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _settings, _llm, _started_at
    _started_at = time.monotonic()
    _settings = load_settings()
    _llm = LLMClient(_settings.llm)
    yield
    _llm = None
    _settings = None


app = FastAPI(title="OpenClaw Lite", lifespan=lifespan)


class ExecuteRequest(BaseModel):
    user_id: str
    platform: str
    message: str


class ExecuteResponse(BaseModel):
    task_id: str
    status: str
    tool: str | None = None
    result: str | None = None
    duration: float
    error: str | None = None


class HealthResponse(BaseModel):
    status: str
    version: str
    uptime: int


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    uptime = int(time.monotonic() - _started_at)
    return HealthResponse(status="ok", version="1.0.0", uptime=uptime)


@app.post("/execute", response_model=ExecuteResponse)
async def execute(body: ExecuteRequest) -> ExecuteResponse:
    if _settings is None or _llm is None:
        raise HTTPException(status_code=503, detail="Service not ready")

    t0 = time.perf_counter()
    task_id = f"task_{time.strftime('%Y%m%d')}_{uuid.uuid4().hex[:8]}"

    if not _settings.llm.api_key:
        return ExecuteResponse(
            task_id=task_id,
            status="error",
            tool=None,
            result=None,
            duration=round(time.perf_counter() - t0, 3),
            error="OPENAI_API_KEY is not configured",
        )

    try:
        parsed = await parse_user_message(_llm, body.message)
        tool = str(parsed.get("tool", "")).strip().lower()
        tool_out, tool_err = await run_tool(_settings, tool, parsed)
        duration = round(time.perf_counter() - t0, 3)
        if tool_err:
            log.warning(
                "user=%s platform=%s tool=%s status=error duration=%ss err=%s",
                body.user_id,
                body.platform,
                tool,
                duration,
                tool_err,
            )
            return ExecuteResponse(
                task_id=task_id,
                status="error",
                tool=tool or None,
                result=_format_parse_only(parsed),
                duration=duration,
                error=tool_err,
            )
        log.info(
            "user=%s platform=%s tool=%s status=success duration=%ss",
            body.user_id,
            body.platform,
            tool,
            duration,
        )
        return ExecuteResponse(
            task_id=task_id,
            status="success",
            tool=tool or None,
            result=_format_tool_success(tool, parsed, tool_out or ""),
            duration=duration,
            error=None,
        )
    except Exception as exc:  # noqa: BLE001 — 接入层统一兜底
        return ExecuteResponse(
            task_id=task_id,
            status="error",
            tool=None,
            result=None,
            duration=round(time.perf_counter() - t0, 3),
            error=str(exc),
        )


def _format_parse_only(parsed: dict[str, Any]) -> str:
    lines = ["【解析参数】"]
    for k, v in parsed.items():
        lines.append(f"- {k}: {v}")
    return "\n".join(lines)


def _format_tool_success(tool: str, parsed: dict[str, Any], output: str) -> str:
    lines = [f"【工具: {tool}】", ""]
    lines.append("【执行输出】")
    lines.append(output.strip())
    lines.extend(["", "【解析参数摘要】"])
    for k, v in parsed.items():
        lines.append(f"- {k}: {v}")
    return "\n".join(lines)
