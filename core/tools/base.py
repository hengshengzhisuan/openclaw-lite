from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseTool(ABC):
    @abstractmethod
    async def validate(self, params: dict[str, Any]) -> str | None:
        """返回错误信息字符串；无错误返回 None。"""

    @abstractmethod
    async def execute(self, params: dict[str, Any]) -> str:
        raise NotImplementedError
