from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response

from core.config import AppSettings
from core.im.feishu_events import (
    build_challenge_response,
    handle_feishu_message_async,
    parse_im_message_event,
    _is_url_verification,
    _unwrap_body,
    _verify_token,
)
from core.im.wechat_events import (
    decrypt_post_body,
    handle_wechat_message_async,
    parse_incoming_text,
    verify_callback_url,
)
from core.llm_client import LLMClient

log = logging.getLogger("openclaw.im")

router = APIRouter(prefix="/im", tags=["IM"])


@router.post("/feishu/events")
async def feishu_events(request: Request, background_tasks: BackgroundTasks) -> dict[str, Any]:
    """
    飞书事件订阅回调地址（Request URL）。
    支持：加密 / 明文；URL 验证；im.message.receive_v1 文本消息（异步回复）。
    """
    settings = request.app.state.settings
    llm = request.app.state.llm
    try:
        raw = await request.json()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"invalid json: {exc}") from exc

    if not isinstance(raw, dict):
        raise HTTPException(status_code=400, detail="body must be object")

    try:
        payload = _unwrap_body(raw, settings.im.feishu.encrypt_key)
    except Exception as exc:  # noqa: BLE001
        log.exception("feishu_decrypt_failed")
        raise HTTPException(status_code=400, detail=f"decrypt failed: {exc}") from exc

    if not _verify_token(payload, settings.im.feishu.verification_token):
        raise HTTPException(status_code=403, detail="verification token mismatch")

    if _is_url_verification(payload):
        return build_challenge_response(payload)

    parsed_msg = parse_im_message_event(payload)
    if parsed_msg:
        message_id, user_id, text = parsed_msg
        background_tasks.add_task(handle_feishu_message_async, settings, llm, message_id, user_id, text)

    return {}


@router.get("/wechat/ping")
async def wechat_ping() -> dict[str, str]:
    """连通性探测：浏览器/curl 可访问即说明域名与路由正确（无需企微加解密）。"""
    return {
        "status": "ok",
        "callback_path": "/im/wechat/callback",
        "hint": "企微后台 URL 须为 https://<与飞书相同域名>/im/wechat/callback",
    }


@router.get("/wechat/callback")
async def wechat_url_verify(
    request: Request,
    msg_signature: str = "",
    timestamp: str = "",
    nonce: str = "",
    echostr: str = "",
) -> Response:
    """
    企业微信 URL 验证（GET）：验签并解密 echostr，原样返回明文 msg。
    """
    client = request.client.host if request.client else "?"
    log.info(
        "wechat_url_verify_request client=%s echostr_len=%s has_sig=%s",
        client,
        len(echostr),
        bool(msg_signature),
    )
    settings: AppSettings = request.app.state.settings
    if not echostr:
        raise HTTPException(status_code=400, detail="missing echostr")
    try:
        plain = verify_callback_url(
            settings,
            msg_signature=msg_signature,
            timestamp=timestamp,
            nonce=nonce,
            echostr=echostr,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("wechat_url_verify_failed: %s", exc)
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    log.info("wechat_url_verify_ok client=%s plain_len=%s", client, len(plain))
    return Response(content=plain, media_type="text/plain; charset=utf-8")


@router.post("/wechat/callback")
async def wechat_message(
    request: Request,
    background_tasks: BackgroundTasks,
    msg_signature: str = "",
    timestamp: str = "",
    nonce: str = "",
) -> Response:
    """企业微信接收消息（POST，加密 XML）。"""
    settings: AppSettings = request.app.state.settings
    llm: LLMClient = request.app.state.llm
    body = (await request.body()).decode("utf-8", errors="replace")

    try:
        plain_xml = decrypt_post_body(
            settings,
            msg_signature=msg_signature,
            timestamp=timestamp,
            nonce=nonce,
            body=body,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("wechat_post_decrypt_failed: %s", exc)
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    parsed = parse_incoming_text(plain_xml)
    if parsed:
        from_user, text = parsed
        background_tasks.add_task(handle_wechat_message_async, settings, llm, from_user, text)

    return Response(content="success", media_type="text/plain; charset=utf-8")
