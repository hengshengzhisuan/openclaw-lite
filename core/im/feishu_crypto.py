from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from Crypto.Cipher import AES


def _pkcs7_unpad(data: bytes) -> bytes:
    if not data:
        return data
    pad = data[-1]
    if pad < 1 or pad > 32:
        return data
    return data[:-pad]


def decrypt_feishu_event(encrypt_key: str, encrypt_b64: str) -> dict[str, Any]:
    """
    飞书事件订阅「加密」模式：POST body 为 {"encrypt": "..."}。
    算法见开放平台文档（SHA256(encrypt_key) 作 AES-256 密钥，前 16 字节为 IV）。
    """
    if not encrypt_key or not encrypt_b64:
        raise ValueError("encrypt_key 或 encrypt 为空")
    key = hashlib.sha256(encrypt_key.encode("utf-8")).digest()
    raw = base64.b64decode(encrypt_b64)
    if len(raw) < 16:
        raise ValueError("密文过短")
    iv, cipher_bytes = raw[:16], raw[16:]
    cipher = AES.new(key, AES.MODE_CBC, iv)
    plain = _pkcs7_unpad(cipher.decrypt(cipher_bytes))
    return json.loads(plain.decode("utf-8"))
