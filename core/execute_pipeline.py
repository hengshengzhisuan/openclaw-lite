from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from core.config import AppSettings
from core.llm_client import LLMClient
from core.parser import parse_user_message
from core.schemas import ExecuteRequest, ExecuteResponse
from core.tools import run_tool

log = logging.getLogger("openclaw.execute")


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


async def run_execute_pipeline(
    settings: AppSettings,
    llm: LLMClient,
    body: ExecuteRequest,
) -> ExecuteResponse:
    t0 = time.perf_counter()
    task_id = f"task_{time.strftime('%Y%m%d')}_{uuid.uuid4().hex[:8]}"

    if not settings.llm.api_key:
        return ExecuteResponse(
            task_id=task_id,
            status="error",
            tool=None,
            result=None,
            duration=round(time.perf_counter() - t0, 3),
            error="OPENAI_API_KEY is not configured",
        )

    try:
        parsed = await parse_user_message(llm, body.message, parser_cfg=settings.parser)
        tool = str(parsed.get("tool", "")).strip().lower()
        tool_out, tool_err = await run_tool(settings, tool, parsed)
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
    except Exception as exc:  # noqa: BLE001
        return ExecuteResponse(
            task_id=task_id,
            status="error",
            tool=None,
            result=None,
            duration=round(time.perf_counter() - t0, 3),
            error=str(exc),
        )
