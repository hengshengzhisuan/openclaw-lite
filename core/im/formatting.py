from __future__ import annotations

import re

from core.schemas import ExecuteResponse


def format_im_reply_text(resp: ExecuteResponse, *, max_chars: int = 3500) -> str:
    """飞书单条文本约 20k 上限，此处保守截断；企业微信类似。"""
    if resp.error:
        lines = [f"状态: {resp.status}", f"错误: {resp.error}"]
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
