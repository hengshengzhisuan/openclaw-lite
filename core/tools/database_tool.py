from __future__ import annotations

import asyncio
import re
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from core.config import AppSettings
from core.tools.base import BaseTool

_FORBIDDEN = re.compile(
    r"\b(DROP|DELETE|INSERT|UPDATE|ALTER|TRUNCATE|CREATE|GRANT|REVOKE|REPLACE|MERGE|CALL|EXECUTE)\b",
    re.IGNORECASE,
)


def _normalize_query(raw: str) -> str:
    q = raw.strip()
    if q.endswith(";"):
        q = q[:-1].rstrip()
    return q


def _validate_sql(query: str) -> str | None:
    q = _normalize_query(query)
    if not q:
        return "SQL 为空"
    if ";" in q:
        return "禁止多语句 SQL（检测到分号）"
    if not re.match(r"^\s*SELECT\b", q, re.IGNORECASE):
        return "仅允许 SELECT 查询"
    if _FORBIDDEN.search(q):
        return "SQL 包含被禁止的关键字"
    return None


def _run_select_sync(url: str, query: str, max_rows: int, timeout_sec: int) -> str:
    q = _normalize_query(query)
    err = _validate_sql(q)
    if err:
        raise ValueError(err)

    parsed = make_url(url)
    connect_args: dict[str, Any] = {}
    driver = parsed.drivername or ""
    if driver.startswith("postgresql"):
        connect_args = {
            "connect_timeout": timeout_sec,
            "options": f"-c statement_timeout={max(1, timeout_sec) * 1000}",
        }
    elif driver.startswith("mysql"):
        connect_args = {
            "connect_timeout": timeout_sec,
            "read_timeout": timeout_sec,
            "write_timeout": timeout_sec,
        }

    engine = create_engine(url, pool_pre_ping=True, connect_args=connect_args)
    with engine.connect() as conn:
        result = conn.execute(text(q))
        cols = list(result.keys())
        rows = result.fetchmany(max_rows + 1)
    if len(rows) > max_rows:
        rows = rows[:max_rows]
        tail = f"\n…（仅展示前 {max_rows} 行，说明书限制）"
    else:
        tail = ""
    if not cols:
        return f"（无列信息）{tail}"
    lines = [" | ".join(cols), "-" * min(80, max(20, 8 * len(cols)))]
    for row in rows:
        cells = ["" if v is None else str(v) for v in row]
        lines.append(" | ".join(cells))
    return "\n".join(lines) + tail


class DatabaseTool(BaseTool):
    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings

    def _resolve(self, conn: str) -> str:
        return self._settings.resolve_database_connection(conn)

    async def validate(self, params: dict[str, Any]) -> str | None:
        conn = params.get("connection")
        query = params.get("query")
        if not conn or not isinstance(conn, str):
            return "缺少 connection（数据库配置名）"
        resolved = self._resolve(conn)
        if resolved not in self._settings.database:
            known = ", ".join(sorted(self._settings.database.keys()))
            return f"未知的数据库连接: {conn}（解析为 {resolved}；已配置: {known}）"
        cfg = self._settings.database[resolved]
        if not (cfg.url or "").strip():
            return f"连接 {conn} 的 URL 未配置"
        if not query or not isinstance(query, str):
            return "缺少 query（SQL）"
        return _validate_sql(query)

    async def execute(self, params: dict[str, Any]) -> str:
        conn_name = self._resolve(str(params["connection"]))
        query = str(params["query"])
        cfg = self._settings.database[conn_name]
        if not cfg.url.strip():
            raise ValueError("数据库 URL 未配置")
        return await asyncio.to_thread(
            _run_select_sync,
            cfg.url,
            query,
            cfg.max_rows,
            cfg.timeout,
        )
