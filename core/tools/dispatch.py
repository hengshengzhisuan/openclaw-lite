from __future__ import annotations

import logging
from typing import Any

from core.config import AppSettings
from core.tools.api_tool import ApiTool
from core.tools.base import BaseTool
from core.tools.browser_tool import BrowserTool
from core.tools.database_tool import DatabaseTool
from core.tools.file_read_tool import FileReadTool

log = logging.getLogger("openclaw.execute")

_TOOLS: dict[str, type[BaseTool]] = {
    "database": DatabaseTool,
    "file": FileReadTool,
    "api": ApiTool,
    "browser": BrowserTool,
}


async def run_tool(settings: AppSettings, name: str, params: dict[str, Any]) -> tuple[str | None, str | None]:
    """执行工具：成功返回 (output, None)，失败返回 (None, error_message)。"""
    key = (name or "").strip().lower()
    if key not in _TOOLS:
        return None, f"未知或不支持的工具类型: {name}"

    tool_cls = _TOOLS[key]
    tool: BaseTool = tool_cls(settings)
    err = await tool.validate(params)
    if err:
        return None, err
    try:
        out = await tool.execute(params)
        return out, None
    except Exception as exc:  # noqa: BLE001
        log.warning("tool_execute_failed tool=%s err=%s", key, exc)
        return None, str(exc)
