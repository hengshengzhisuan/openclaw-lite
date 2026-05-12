from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from core.config import AppSettings
from core.tools.base import BaseTool


def _is_under_allowed(path: Path, roots: list[str]) -> bool:
    try:
        resolved = path.resolve()
    except OSError:
        return False
    for root in roots:
        if not root.strip():
            continue
        try:
            base = Path(root).expanduser().resolve()
        except OSError:
            continue
        try:
            resolved.relative_to(base)
            return True
        except ValueError:
            continue
    return False


def _read_file_sync(path_str: str, roots: list[str], max_lines: int) -> str:
    p = Path(path_str).expanduser()
    if not _is_under_allowed(p, roots):
        raise ValueError("路径不在白名单目录内")
    if not p.is_file():
        raise ValueError("不是可读文件或不存在")
    lines: list[str] = []
    with p.open("r", encoding="utf-8", errors="replace") as f:
        for i, line in enumerate(f):
            if i >= max_lines:
                break
            lines.append(line.rstrip("\n"))
    if len(lines) >= max_lines:
        tail = f"\n…（仅读取前 {max_lines} 行）"
    else:
        tail = ""
    return "\n".join(lines) + tail


class FileReadTool(BaseTool):
    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings

    async def validate(self, params: dict[str, Any]) -> str | None:
        path = params.get("path")
        if not path or not isinstance(path, str):
            return "缺少 path（文件路径）"
        if not self._settings.file.allowed_paths:
            return "未配置 file.allowed_paths"
        return None

    async def execute(self, params: dict[str, Any]) -> str:
        return await asyncio.to_thread(
            _read_file_sync,
            str(params["path"]),
            self._settings.file.allowed_paths,
            self._settings.file.max_lines,
        )
