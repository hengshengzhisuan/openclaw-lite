from __future__ import annotations

"""
企业微信「接收消息」回调需使用官方加解密（WXBizMsgCrypt：CorpID、Token、EncodingAESKey）。
此处仅占位与开发期极简校验；生产环境请使用 wechatpy 或官方示例实现 GET/POST 全链路。
"""

WEBCHAT_CRYPTO_NOTE = (
    "企业微信回调需配置 WECHAT_CALLBACK_TOKEN，并实现 EncodingAESKey 加解密；"
    "参见 https://developer.work.weixin.qq.com/document/path/90930"
)
