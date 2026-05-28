from __future__ import annotations

import re

from core.schemas import ExecuteResponse


def _simplify_error_for_im(err: str) -> str:
    """IM 里展示过长的驱动异常时做简短说明。"""
    if "1129" in err and "flush-hosts" in err.lower():
        return (
            "数据库拒绝连接：来源 IP 因多次连接失败被 MySQL 临时封禁。\n"
            "请在数据库服务器执行：mysqladmin flush-hosts  或  FLUSH HOSTS;\n"
            "（本机查库需经 VPN/内网，且 MySQL 需允许你的出口 IP。）"
        )
    if len(err) > 800:
        return err[:800] + "\n…（错误信息已截断）"
    return err


def format_im_reply_text(resp: ExecuteResponse, *, max_chars: int = 3500) -> str:
    """飞书单条文本约 20k 上限，此处保守截断；企业微信类似。"""
    if resp.error:
        lines = [f"状态: {resp.status}", f"错误: {_simplify_error_for_im(resp.error)}"]
        if resp.result:
            lines.extend(["", resp.result])
        text = "\n".join(lines)
    else:
        text = resp.result or "（无输出）"
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 20] + "\n…（输出过长已截断）"


def extract_feishu_text_from_content_json(content_raw: str) -> str:
    """message.content 为 JSON 字符串，如 {\"text\":\"hello\"}。"""
    import json

    try:
        obj = json.loads(content_raw)
    except json.JSONDecodeError:
        return content_raw.strip()
    if isinstance(obj, dict) and "text" in obj:
        return str(obj["text"]).strip()
    return content_raw.strip()


def strip_at_mention(text: str) -> str:
    """去掉群聊里 @机器人 前缀（简单规则）。"""
    t = text.strip()
    t = re.sub(r"^@[\w\u4e00-\u9fff]+\s+", "", t)
    return t.strip()
