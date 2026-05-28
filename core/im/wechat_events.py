from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET

from core.config import AppSettings
from core.execute_pipeline import run_execute_pipeline
from core.im.formatting import format_im_reply_text, strip_at_mention
from core.im.wechat_api import WechatWorkApiClient
from core.im.wechat_crypto import WechatWorkCrypto
from core.llm_client import LLMClient
from core.schemas import ExecuteRequest

log = logging.getLogger("openclaw.im.wechat")

_CDATA_RE = re.compile(r"^<!\[CDATA\[(.*)]]>$", re.DOTALL)


def _xml_text(elem: ET.Element | None) -> str:
    if elem is None or elem.text is None:
        return ""
    raw = elem.text.strip()
    m = _CDATA_RE.match(raw)
    return (m.group(1) if m else raw).strip()


def _build_crypto(settings: AppSettings) -> WechatWorkCrypto:
    cfg = settings.im.wechat
    if not (cfg.callback_token and cfg.encoding_aes_key and cfg.corp_id):
        raise RuntimeError(
            "企微回调未配置完整：需 WECHAT_CALLBACK_TOKEN、WECHAT_ENCODING_AES_KEY、WECHAT_CORP_ID"
        )
    return WechatWorkCrypto(cfg.callback_token, cfg.encoding_aes_key, cfg.corp_id)


def verify_callback_url(
    settings: AppSettings,
    *,
    msg_signature: str,
    timestamp: str,
    nonce: str,
    echostr: str,
) -> str:
    crypto = _build_crypto(settings)
    plain = crypto.verify_url(msg_signature, timestamp, nonce, echostr)
    return plain.strip("\n\r")


def decrypt_post_body(
    settings: AppSettings,
    *,
    msg_signature: str,
    timestamp: str,
    nonce: str,
    body: str,
) -> str:
    crypto = _build_crypto(settings)
    root = ET.fromstring(body)
    encrypt_node = root.find("Encrypt")
    if encrypt_node is None or not (encrypt_node.text or "").strip():
        raise ValueError("POST body 缺少 Encrypt")
    encrypt = encrypt_node.text.strip()
    if not crypto.verify_signature(msg_signature, timestamp, nonce, encrypt):
        raise ValueError("msg_signature 校验失败")
    return crypto.decrypt(encrypt)


def parse_incoming_text(plain_xml: str) -> tuple[str, str] | None:
    """返回 (from_user, text) 或 None（非文本消息）。"""
    root = ET.fromstring(plain_xml)
    msg_type = _xml_text(root.find("MsgType"))
    if msg_type != "text":
        return None
    content = strip_at_mention(_xml_text(root.find("Content")))
    if not content:
        return None
    from_user = _xml_text(root.find("FromUserName"))
    return from_user or "wechat_user", content


async def handle_wechat_message_async(
    settings: AppSettings,
    llm: LLMClient,
    from_user: str,
    text: str,
) -> None:
    req = ExecuteRequest(user_id=from_user, platform="wechat_work", message=text)
    resp = await run_execute_pipeline(settings, llm, req)
    reply = format_im_reply_text(resp)
    cfg = settings.im.wechat
    client = WechatWorkApiClient(cfg.corp_id, cfg.secret, cfg.agent_id)
    try:
        await client.send_text(from_user, reply)
    except Exception as exc:  # noqa: BLE001
        preview = reply[:400].replace("\n", " ")
        log.error(
            "wechat_reply_failed user=%s send_err=%s reply_preview=%s",
            from_user,
            exc,
            preview,
        )
        if "60020" in str(exc):
            log.error(
                "wechat_hint: 企微未收到回复是因为「企业可信IP」未包含本机出口 IP，"
                "请在管理后台添加当前公网 IP 后重试"
            )
        return
    log.info("wechat_reply_sent user=%s status=%s", from_user, resp.status)
