from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from playwright.async_api import async_playwright

from core.config import AppSettings
from core.tools.base import BaseTool


class BrowserTool(BaseTool):
    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings

    async def validate(self, params: dict[str, Any]) -> str | None:
        url = params.get("url")
        if not url or not isinstance(url, str):
            return "缺少 url"
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return "仅允许 http/https URL"
        if not parsed.hostname:
            return "URL 缺少主机名"
        return None

    async def execute(self, params: dict[str, Any]) -> str:
        url = str(params["url"])
        timeout_ms = max(1000, int(self._settings.browser.navigation_timeout_seconds) * 1000)
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                page = await browser.new_page()
                await page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
                text = await page.inner_text("body")
            finally:
                await browser.close()
        text = text.strip()
        if len(text) > 80_000:
            text = text[:80_000] + "\n…（页面文本过长已截断）"
        return text or "（页面无可见文本）"
