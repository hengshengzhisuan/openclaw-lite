from __future__ import annotations

import logging
import re
from typing import Any

log = logging.getLogger("openclaw.parser")

_USER_TABLE_HINT = re.compile(
    r"用户(?:数据|信息|表|账号|列表|记录|资料)?|users?\s*表|账号数据|项目用户",
    re.IGNORECASE,
)
_RECORDING_TABLE_HINT = re.compile(
    r"录音(?!笔)(?:数据|内容|记录|文件)|recordings?\s*表|(?:前|最近)\s*\d*\s*条\s*录音(?!笔)|查.{0,12}录音(?!笔)",
    re.IGNORECASE,
)
_FROM_RECORDINGS = re.compile(r"\bFROM\s+recordings\b", re.IGNORECASE)
_FROM_USERS = re.compile(r"\bFROM\s+users\b", re.IGNORECASE)
_LIMIT_IN_QUERY = re.compile(r"\bLIMIT\s+(\d+)\b", re.IGNORECASE)
_LIMIT_IN_MESSAGE = re.compile(r"前\s*(\d+)\s*条")
_CN_LIMIT = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def _wants_user_table(message: str) -> bool:
    return bool(_USER_TABLE_HINT.search(message))


def _wants_recording_table(message: str) -> bool:
    return bool(_RECORDING_TABLE_HINT.search(message))


def _limit_from_message(message: str) -> int | None:
    m = _LIMIT_IN_MESSAGE.search(message)
    if m:
        return int(m.group(1))
    m_cn = re.search(r"前\s*([一二三四五])\s*条", message)
    if m_cn:
        return _CN_LIMIT.get(m_cn.group(1))
    return None


def _ensure_limit(query: str, limit: int) -> str:
    if _LIMIT_IN_QUERY.search(query):
        return query
    q = query.rstrip()
    return f"{q} LIMIT {limit}"


def correct_database_parse(message: str, parsed: dict[str, Any]) -> dict[str, Any]:
    """在 LLM 解析后按用户意图校正 users / recordings 表选择。"""
    if str(parsed.get("tool", "")).strip().lower() != "database":
        return parsed

    query = str(parsed.get("query", "")).strip()
    if not query:
        return parsed

    wants_user = _wants_user_table(message)
    wants_recording = _wants_recording_table(message)

    if wants_user and not wants_recording and _FROM_RECORDINGS.search(query):
        new_query = _FROM_RECORDINGS.sub("FROM users", query, count=1)
        limit = _limit_from_message(message)
        if limit is not None:
            new_query = _ensure_limit(new_query, limit)
        log.info(
            "database parse fixup: recordings -> users (message=%r)",
            message[:80],
        )
        return {**parsed, "query": new_query}

    if wants_recording and not wants_user and _FROM_USERS.search(query):
        new_query = _FROM_USERS.sub("FROM recordings", query, count=1)
        limit = _limit_from_message(message)
        if limit is not None:
            new_query = _ensure_limit(new_query, limit)
        log.info(
            "database parse fixup: users -> recordings (message=%r)",
            message[:80],
        )
        return {**parsed, "query": new_query}

    return parsed
