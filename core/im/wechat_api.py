from __future__ import annotations

import time

import httpx


class WechatWorkApiClient:
    """企业微信应用：access_token + 发送文本消息。"""

    def __init__(self, corp_id: str, secret: str, agent_id: str) -> None:
        self._corp_id = corp_id.strip()
        self._secret = secret.strip()
        self._agent_id = agent_id.strip()
        self._token: str | None = None
        self._expire_at: float = 0.0

    async def access_token(self) -> str:
        if self._token and time.monotonic() < self._expire_at - 60:
            return self._token
        if not self._corp_id or not self._secret:
            raise RuntimeError("WECHAT_CORP_ID / WECHAT_SECRET 未配置")
        url = "https://qyapi.weixin.qq.com/cgi-bin/gettoken"
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(
                url,
                params={"corpid": self._corp_id, "corpsecret": self._secret},
            )
            r.raise_for_status()
            data = r.json()
        if data.get("errcode", 0) != 0:
            raise RuntimeError(f"企微 gettoken 失败: {data}")
        self._token = str(data["access_token"])
        self._expire_at = time.monotonic() + int(data.get("expires_in", 7200))
        return self._token

    async def send_text(self, touser: str, content: str) -> None:
        if not self._agent_id:
            raise RuntimeError("WECHAT_AGENT_ID 未配置")
        token = await self.access_token()
        url = "https://qyapi.weixin.qq.com/cgi-bin/message/send"
        body = {
            "touser": touser,
            "msgtype": "text",
            "agentid": int(self._agent_id),
            "text": {"content": content},
            "safe": 0,
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(url, params={"access_token": token}, json=body)
            data = r.json()
        if data.get("errcode", 0) != 0:
            raise RuntimeError(f"企微发消息失败: {data}")
