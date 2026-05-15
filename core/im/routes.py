from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response

from core.config import AppSettings
from core.execute_pipeline import run_execute_pipeline
from core.im.feishu_events import (
    build_challenge_response,
    handle_feishu_message_async,
    parse_im_message_event,
    _is_url_verification,
    _unwrap_body,
    _verify_token,
)
from core.im.formatting import format_im_reply_text, strip_at_mention
from core.im.wechat_stub import WEBCHAT_CRYPTO_NOTE
from core.llm_client import LLMClient
from core.schemas import ExecuteRequest

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


@router.get("/wechat/callback")
async def wechat_url_verify(
    request: Request,
    msg_signature: str = "",
    timestamp: str = "",
    nonce: str = "",
    echostr: str = "",
) -> Response:
    """
    企业微信 URL 验证（GET）。生产环境需验签并解密 echostr；未实现加解密时仅作占位。
    """
    _ = (msg_signature, timestamp, nonce)
    settings: AppSettings = request.app.state.settings
    if echostr:
        return Response(content=echostr, media_type="text/plain; charset=utf-8")
    if not (settings.im.wechat.corp_id or "").strip():
        return Response(content=WEBCHAT_CRYPTO_NOTE, status_code=501, media_type="text/plain; charset=utf-8")
    return Response(content=WEBCHAT_CRYPTO_NOTE, status_code=200, media_type="text/plain; charset=utf-8")


@router.post("/wechat/callback")
async def wechat_message(request: Request, background_tasks: BackgroundTasks) -> Response:
    """
    企业微信接收消息（POST，XML）。完整流程需解密 Encrypt 字段；此处返回 success 作为占位。
    调试 HTTP API 请仍使用 POST /execute。
    """
    settings = request.app.state.settings
    llm = request.app.state.llm
    body = await request.body()
    text = body.decode("utf-8", errors="replace")
    log.debug("wechat_raw_len=%s", len(text))

    if "<Content>" in text and "</Content>" in text:
        try:
            start = text.index("<Content>") + len("<Content>")
            end = text.index("</Content>", start)
            inner = text[start:end]
            if inner.startswith("<![CDATA[") and inner.endswith("]]>"):
                inner = inner[9:-3]
            inner = strip_at_mention(inner.strip())
            if inner:
                user_id = "wechat_user"
                if "<FromUserName>" in text:
                    s = text.index("<FromUserName>") + len("<FromUserName>")
                    e = text.index("</FromUserName>", s)
                    fu = text[s:e]
                    if fu.startswith("<![CDATA[") and fu.endswith("]]>"):
                        fu = fu[9:-3]
                    user_id = fu.strip() or user_id
                req = ExecuteRequest(user_id=user_id, platform="wechat_work", message=inner)
                background_tasks.add_task(_wechat_reply_placeholder, settings, llm, req)
        except ValueError:
            pass

    return Response(content="success", media_type="text/plain; charset=utf-8")


async def _wechat_reply_placeholder(settings: AppSettings, llm: LLMClient, req: ExecuteRequest) -> None:
    """占位：真实场景需调企业微信主动发消息 API；此处仅打日志。"""
    resp = await run_execute_pipeline(settings, llm, req)
    preview = format_im_reply_text(resp)[:500]
    log.info("wechat_message_processed user=%s status=%s preview=%s", req.user_id, resp.status, preview)
