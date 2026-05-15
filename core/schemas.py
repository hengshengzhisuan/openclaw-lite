from __future__ import annotations

from pydantic import BaseModel, Field


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
