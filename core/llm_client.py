from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any

from openai import AsyncOpenAI

from core.config import LLMConfig


def _assistant_text(message: object) -> str:
    """兼容部分网关：正文在 content，思考链在 reasoning_content（content 可能为空）。"""
    content = getattr(message, "content", None)
    if isinstance(content, str) and content.strip():
        return content.strip()
    rc = getattr(message, "reasoning_content", None)
    if isinstance(rc, str) and rc.strip():
        return rc.strip()
    extra = getattr(message, "__pydantic_extra__", None)
    if isinstance(extra, dict):
        rc = extra.get("reasoning_content")
        if isinstance(rc, str) and rc.strip():
            return rc.strip()
    return ""


def loads_json_object(text: str) -> dict[str, Any]:
    """解析模型输出：整段 JSON，或从文本中截取第一个 {...} 对象。"""
    raw = text.strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        lo, hi = raw.find("{"), raw.rfind("}")
        if lo == -1 or hi <= lo:
            raise
        data = json.loads(raw[lo : hi + 1])
    if not isinstance(data, dict):
        raise ValueError("LLM output must be a JSON object")
    return data


@dataclass
class _CacheEntry:
    value: str
    expires_at: float


class LLMClient:
    """OpenAI 兼容 Chat Completions，带进程内 TTL 缓存。"""

    def __init__(self, llm: LLMConfig) -> None:
        self._llm = llm
        self._cache: dict[str, _CacheEntry] = {}
        self._client: AsyncOpenAI | None = None
        if llm.provider == "openai" and llm.api_key:
            kwargs: dict[str, Any] = {"api_key": llm.api_key, "timeout": llm.timeout}
            if llm.base_url.strip():
                kwargs["base_url"] = llm.base_url.strip().rstrip("/")
            self._client = AsyncOpenAI(**kwargs)

    def _cache_key(self, system_prompt: str, user_message: str) -> str:
        raw = f"{self._llm.provider}:{self._llm.base_url}:{self._llm.model}:{system_prompt}:{user_message}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _get_cached(self, key: str) -> str | None:
        entry = self._cache.get(key)
        if not entry:
            return None
        if time.monotonic() >= entry.expires_at:
            del self._cache[key]
            return None
        return entry.value

    def _set_cached(self, key: str, text: str) -> None:
        ttl = max(0, int(self._llm.cache_ttl_seconds))
        if ttl <= 0:
            return
        self._cache[key] = _CacheEntry(value=text, expires_at=time.monotonic() + ttl)

    async def complete_json_text(
        self,
        *,
        system_prompt: str,
        user_message: str,
    ) -> str:
        key = self._cache_key(system_prompt, user_message)
        hit = self._get_cached(key)
        if hit is not None:
            return hit

        if self._llm.provider != "openai":
            raise NotImplementedError(f"LLM provider not supported yet: {self._llm.provider}")
        if not self._client:
            raise RuntimeError("OPENAI_API_KEY is missing or client not initialized")

        assert self._client is not None
        create_kwargs: dict[str, Any] = {
            "model": self._llm.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "temperature": 0.2,
        }
        if self._llm.json_response_format:
            create_kwargs["response_format"] = {"type": "json_object"}
        create_kwargs["max_tokens"] = max(1, int(self._llm.max_tokens))
        resp = await self._client.chat.completions.create(**create_kwargs)
        text = _assistant_text(resp.choices[0].message)
        if not text:
            text = "{}"
        self._set_cached(key, text)
        return text

    async def complete_json(self, *, system_prompt: str, user_message: str) -> dict[str, Any]:
        text = await self.complete_json_text(system_prompt=system_prompt, user_message=user_message)
        return loads_json_object(text)
