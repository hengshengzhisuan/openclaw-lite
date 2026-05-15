from __future__ import annotations

import time
from typing import Any

import httpx

_TOKEN_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"


class FeishuApiClient:
    def __init__(self, app_id: str, app_secret: str) -> None:
        self._app_id = app_id.strip()
        self._app_secret = app_secret.strip()
        self._token: str | None = None
        self._expire_at: float = 0.0

    async def tenant_access_token(self) -> str:
        if self._token and time.monotonic() < self._expire_at - 60:
            return self._token
        if not self._app_id or not self._app_secret:
            raise RuntimeError("FEISHU_APP_ID / FEISHU_APP_SECRET 未配置")
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(
                _TOKEN_URL,
                json={"app_id": self._app_id, "app_secret": self._app_secret},
            )
            r.raise_for_status()
            data = r.json()
        if data.get("code") != 0:
            raise RuntimeError(f"飞书 tenant_token 失败: {data}")
        self._token = str(data["tenant_access_token"])
        self._expire_at = time.monotonic() + int(data.get("expire", 7200))
        return self._token

    async def reply_text(self, message_id: str, text: str) -> None:
        import json

        token = await self.tenant_access_token()
        url = f"https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/reply"
        body = {"msg_type": "text", "content": json.dumps({"text": text}, ensure_ascii=False)}
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                url,
                headers={"Authorization": f"Bearer {token}"},
                json=body,
            )
            data = r.json()
        if r.status_code >= 400 or data.get("code", 0) != 0:
            raise RuntimeError(f"飞书回复失败 HTTP {r.status_code} body={data}")
