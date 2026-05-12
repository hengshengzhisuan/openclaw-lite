from __future__ import annotations

import json
from typing import Any

from core.llm_client import LLMClient

# 说明书 4.1 提示词模板（docx 原文；Unicode 转义保证与 Word 弯引号等一致）。
_SYSTEM_PROMPT = (
    "\u4f60\u662f\u4e00\u4e2a\u6280\u672f\u5de5\u5177\u89e3\u6790\u52a9\u624b\u3002\u5206\u6790\u7528\u6237\u6307\u4ee4\uff0c\u63d0\u53d6\uff1a\n"
    "\u5de5\u5177\u7c7b\u578b\uff1abrowser | database | file | api\n"
    "\u64cd\u4f5c\u53c2\u6570\uff1a\u6839\u636e\u5de5\u5177\u7c7b\u578b\u63d0\u53d6\n"
    "\u98ce\u9669\u7b49\u7ea7\uff1alow | medium | high\n"
    "\u5de5\u5177\u5b9a\u4e49\uff1a - browser: \u8bbf\u95ee\u7f51\u9875\uff0c\u53c2\u6570 \u007burl\u007d - database: \u6267\u884cSQL\uff0c\u53c2\u6570 \u007bconnection, query\u007d - file: \u8bfb\u53d6\u6587\u4ef6\uff0c\u53c2\u6570 \u007bpath\u007d - api: HTTP\u8bf7\u6c42\uff0c\u53c2\u6570 \u007bmethod, url, body\u007d\n"
    "\u793a\u4f8b\uff1a \u201c\u67e5\u4e00\u4e0b\u4e3b\u5e93\u7528\u6237\u8868\u524d5\u6761\u201d \u2192 \u007b\u201ctool\u201d: \u201cdatabase\u201d, \u201cconnection\u201d: \u201cmain_db\u201d, \u201cquery\u201d: \u201cSELECT * FROM users LIMIT 5\u201d\u007d \u201c\u8bfbnginx\u65e5\u5fd7\u201d \u2192 \u007b\u201ctool\u201d: \u201cfile\u201d, \u201cpath\u201d: \u201c/var/log/nginx/access.log\u201d\u007d"
)


# 仅追加在用户消息末尾，不改动说明书中的系统提示词；便于网关把 JSON 放在 content。
_JSON_USER_SUFFIX = (
    "\n\n请仅输出一个 JSON 对象（键名用英文），对应上述工具类型与参数，不要其它说明或 markdown 围栏。"
)


async def parse_user_message(llm: LLMClient, message: str) -> dict[str, Any]:
    data = await llm.complete_json(
        system_prompt=_SYSTEM_PROMPT,
        user_message=message + _JSON_USER_SUFFIX,
    )
    if "tool" not in data:
        raise ValueError(f"LLM output missing 'tool': {json.dumps(data, ensure_ascii=False)}")
    return data
