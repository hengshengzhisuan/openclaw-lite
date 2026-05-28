from __future__ import annotations

import re
from typing import Any

import httpx

from core.config import AppSettings
from core.tools.base import BaseTool

_CITY_PATTERN = re.compile(r"^[\w\u4e00-\u9fff\s·\-]{1,64}$")

# Open-Meteo WMO weather code → 简短中文
_WMO_ZH: dict[int, str] = {
    0: "晴",
    1: "大部晴朗",
    2: "局部多云",
    3: "阴",
    45: "雾",
    48: "雾凇",
    51: "小毛毛雨",
    53: "毛毛雨",
    55: "大毛毛雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    80: "小阵雨",
    81: "阵雨",
    82: "大阵雨",
    95: "雷暴",
    96: "雷暴伴小冰雹",
    99: "雷暴伴大冰雹",
}


def _weather_desc(code: int | None) -> str:
    if code is None:
        return "未知"
    return _WMO_ZH.get(code, f"代码 {code}")


def _resolve_city(params: dict[str, Any], default: str) -> str:
    raw = params.get("city")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return default.strip() or "北京"


class WeatherTool(BaseTool):
    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings

    async def validate(self, params: dict[str, Any]) -> str | None:
        city = _resolve_city(params, self._settings.weather.default_city)
        if not _CITY_PATTERN.match(city):
            return "城市名格式无效（仅允许中英文、数字、空格、·、-）"
        return None

    async def execute(self, params: dict[str, Any]) -> str:
        cfg = self._settings.weather
        city = _resolve_city(params, cfg.default_city)
        timeout = httpx.Timeout(cfg.timeout)

        async with httpx.AsyncClient(timeout=timeout) as client:
            geo_resp = await client.get(
                cfg.geocoding_url,
                params={"name": city, "count": 1, "language": "zh", "format": "json"},
            )
            geo_resp.raise_for_status()
            geo = geo_resp.json()
            results = geo.get("results") or []
            if not results:
                return f"未找到城市「{city}」，请换一个更具体的地名（如「北京」「上海浦东」）。"

            hit = results[0]
            name = hit.get("name", city)
            admin1 = hit.get("admin1") or ""
            country = hit.get("country") or ""
            lat = hit["latitude"]
            lon = hit["longitude"]

            wx_resp = await client.get(
                cfg.forecast_url,
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": "temperature_2m,relative_humidity_2m,apparent_temperature,"
                    "weather_code,wind_speed_10m",
                    "timezone": "auto",
                },
            )
            wx_resp.raise_for_status()
            wx = wx_resp.json()

        current = wx.get("current") or {}
        temp = current.get("temperature_2m")
        feels = current.get("apparent_temperature")
        humidity = current.get("relative_humidity_2m")
        wind = current.get("wind_speed_10m")
        code = current.get("weather_code")
        time_str = current.get("time", "")

        place = name
        if admin1 and admin1 not in name:
            place = f"{name}（{admin1}）"
        if country:
            place = f"{place}，{country}"

        lines = [
            f"【{place} 当前天气】",
            f"状况：{_weather_desc(code if isinstance(code, int) else None)}",
        ]
        if temp is not None:
            lines.append(f"气温：{temp}°C")
        if feels is not None:
            lines.append(f"体感：{feels}°C")
        if humidity is not None:
            lines.append(f"湿度：{humidity}%")
        if wind is not None:
            lines.append(f"风速：{wind} km/h")
        if time_str:
            lines.append(f"观测时间：{time_str}")
        lines.append("数据来源：Open-Meteo")
        return "\n".join(lines)
