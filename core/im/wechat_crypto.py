from __future__ import annotations

import base64
import hashlib
import struct
from urllib.parse import unquote

from Crypto.Cipher import AES


def _pkcs7_unpad(data: bytes) -> bytes:
    pad = data[-1]
    if pad < 1 or pad > 32:
        raise ValueError("invalid pkcs7 padding")
    return data[:-pad]


class WechatWorkCrypto:
    """
    企业微信回调加解密（与官方 WXBizMsgCrypt 一致）。
    文档：https://developer.work.weixin.qq.com/document/path/90930
    """

    def __init__(self, token: str, encoding_aes_key: str, corp_id: str) -> None:
        self._token = token.strip()
        self._corp_id = corp_id.strip()
        key_raw = encoding_aes_key.strip()
        if not key_raw:
            raise ValueError("encoding_aes_key 为空")
        self._aes_key = base64.b64decode(key_raw + "=")
        if len(self._aes_key) != 32:
            raise ValueError("EncodingAESKey 解码后须为 32 字节")
        self._iv = self._aes_key[:16]

    def _signature(self, timestamp: str, nonce: str, encrypt: str) -> str:
        parts = sorted([self._token, timestamp, nonce, encrypt])
        return hashlib.sha1("".join(parts).encode("utf-8")).hexdigest()

    def verify_signature(self, msg_signature: str, timestamp: str, nonce: str, encrypt: str) -> bool:
        return self._signature(timestamp, nonce, encrypt) == msg_signature

    def decrypt(self, encrypt_b64: str) -> str:
        cipher = AES.new(self._aes_key, AES.MODE_CBC, self._iv)
        plain = _pkcs7_unpad(cipher.decrypt(base64.b64decode(encrypt_b64)))
        if len(plain) < 20:
            raise ValueError("解密后明文过短")
        msg_len = struct.unpack("!I", plain[16:20])[0]
        end = 20 + msg_len
        if end > len(plain):
            raise ValueError("消息长度字段非法")
        msg = plain[20:end].decode("utf-8")
        receive_id = plain[end:].decode("utf-8")
        if receive_id != self._corp_id:
            raise ValueError("CorpID 与配置不一致")
        return msg

    def verify_url(self, msg_signature: str, timestamp: str, nonce: str, echostr: str) -> str:
        """URL 验证：验签并解密 echostr，返回须原样输出的明文 msg。"""
        encrypt = unquote(echostr)
        ts = unquote(timestamp)
        nc = unquote(nonce)
        sig = unquote(msg_signature)
        if not self.verify_signature(sig, ts, nc, encrypt):
            raise ValueError("msg_signature 校验失败")
        return self.decrypt(encrypt)
