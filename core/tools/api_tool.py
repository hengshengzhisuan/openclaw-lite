from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse

import httpx

from core.config import AppSettings
from core.tools.base import BaseTool


def _host_allowed(host: str, whitelist: list[str]) -> bool:
    h = host.lower().rstrip(".")
    for entry in whitelist:
        e = entry.lower().rstrip(".")
        if h == e or h.endswith("." + e):
            return True
    return False


class ApiTool(BaseTool):
    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings

    async def validate(self, params: dict[str, Any]) -> str | None:
        method = params.get("method")
        url = params.get("url")
        if not method or not isinstance(method, str):
            return "缺少 method（HTTP 方法）"
        if not url or not isinstance(url, str):
            return "缺少 url"
        if not self._settings.api.whitelist:
            return "未配置 api.whitelist"
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return "仅允许 http/https"
        if not parsed.hostname:
            return "URL 缺少主机名"
        if not _host_allowed(parsed.hostname, self._settings.api.whitelist):
            return f"域名不在白名单: {parsed.hostname}"
        return None

    async def execute(self, params: dict[str, Any]) -> str:
        method = str(params["method"]).upper()
        url = str(params["url"])
        body = params.get("body")
        timeout = httpx.Timeout(self._settings.api.timeout)
        headers = {"User-Agent": "OpenClaw-Lite/1.0"}
        json_body: Any = None
        content: bytes | None = None
        if body is not None and body != "":
            if isinstance(body, (dict, list)):
                json_body = body
            elif isinstance(body, str):
                content = body.encode("utf-8")
                headers["Content-Type"] = "application/json; charset=utf-8"
            else:
                content = str(body).encode("utf-8")

        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.request(
                method,
                url,
                headers=headers,
                json=json_body,
                content=content,
            )
        text = resp.text
        if len(text) > 50_000:
            text = text[:50_000] + "\n…（响应过长已截断）"
        return f"HTTP {resp.status_code}\n{text}"
