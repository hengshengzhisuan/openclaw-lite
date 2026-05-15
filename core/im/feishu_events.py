from __future__ import annotations

import logging
from typing import Any

from core.config import AppSettings
from core.execute_pipeline import run_execute_pipeline
from core.im.feishu_api import FeishuApiClient
from core.im.feishu_crypto import decrypt_feishu_event
from core.im.formatting import extract_feishu_text_from_content_json, format_im_reply_text, strip_at_mention
from core.llm_client import LLMClient
from core.schemas import ExecuteRequest

log = logging.getLogger("openclaw.im.feishu")


def _unwrap_body(raw: dict[str, Any], encrypt_key: str) -> dict[str, Any]:
    enc = raw.get("encrypt")
    if isinstance(enc, str) and enc.strip() and encrypt_key.strip():
        return decrypt_feishu_event(encrypt_key, enc)
    return raw


def _is_url_verification(payload: dict[str, Any]) -> bool:
    if payload.get("type") == "url_verification" and "challenge" in payload:
        return True
    return False


def _verify_token(payload: dict[str, Any], expected: str) -> bool:
    if not (expected or "").strip():
        return True
    token = payload.get("token")
    if token is None and isinstance(payload.get("header"), dict):
        token = payload["header"].get("token")
    return str(token or "") == expected.strip()


def build_challenge_response(payload: dict[str, Any]) -> dict[str, str]:
    return {"challenge": str(payload["challenge"])}


def parse_im_message_event(payload: dict[str, Any]) -> tuple[str, str, str] | None:
    """
    返回 (message_id, user_open_id, plain_text)；非文本消息返回 None。
    """
    header = payload.get("header") or {}
    if header.get("event_type") != "im.message.receive_v1":
        return None
    event = payload.get("event") or {}
    msg = event.get("message") or {}
    message_id = str(msg.get("message_id") or "")
    if not message_id:
        return None
    content_raw = msg.get("content")
    if not isinstance(content_raw, str):
        return None
    text = extract_feishu_text_from_content_json(content_raw)
    text = strip_at_mention(text)
    if not text:
        return None
    sender = event.get("sender") or {}
    sid = sender.get("sender_id") or {}
    user_id = str(sid.get("open_id") or sid.get("union_id") or sid.get("user_id") or "unknown")
    return message_id, user_id, text


async def handle_feishu_message_async(
    settings: AppSettings,
    llm: LLMClient,
    message_id: str,
    user_id: str,
    text: str,
) -> None:
    body = ExecuteRequest(user_id=user_id, platform="feishu", message=text)
    resp = await run_execute_pipeline(settings, llm, body)
    reply = format_im_reply_text(resp)
    client = FeishuApiClient(settings.im.feishu.app_id, settings.im.feishu.app_secret)
    await client.reply_text(message_id, reply)
    log.info("feishu_replied message_id=%s user=%s status=%s", message_id, user_id, resp.status)
