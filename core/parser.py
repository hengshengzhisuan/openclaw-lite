from __future__ import annotations

import json
from typing import Any

from core.config import ParserConfig
from core.llm_client import LLMClient
from core.parser_database_fixup import correct_database_parse

# 说明书 4.1 提示词模板（docx 原文；Unicode 转义保证与 Word 弯引号等一致）。
_SYSTEM_PROMPT = (
    "\u4f60\u662f\u4e00\u4e2a\u6280\u672f\u5de5\u5177\u89e3\u6790\u52a9\u624b\u3002\u5206\u6790\u7528\u6237\u6307\u4ee4\uff0c\u63d0\u53d6\uff1a\n"
    "\u5de5\u5177\u7c7b\u578b\uff1abrowser | database | file | api\n"
    "\u64cd\u4f5c\u53c2\u6570\uff1a\u6839\u636e\u5de5\u5177\u7c7b\u578b\u63d0\u53d6\n"
    "\u98ce\u9669\u7b49\u7ea7\uff1alow | medium | high\n"
    "\u5de5\u5177\u5b9a\u4e49\uff1a - browser: \u8bbf\u95ee\u7f51\u9875\uff0c\u53c2\u6570 \u007burl\u007d - database: \u6267\u884cSQL\uff0c\u53c2\u6570 \u007bconnection, query\u007d - file: \u8bfb\u53d6\u6587\u4ef6\uff0c\u53c2\u6570 \u007bpath\u007d - api: HTTP\u8bf7\u6c42\uff0c\u53c2\u6570 \u007bmethod, url, body\u007d\n"
    "\u793a\u4f8b\uff1a \u201c\u67e5\u4e00\u4e0b\u4e3b\u5e93\u7528\u6237\u8868\u524d5\u6761\u201d \u2192 \u007b\u201ctool\u201d: \u201cdatabase\u201d, \u201cconnection\u201d: \u201cmain_db\u201d, \u201cquery\u201d: \u201cSELECT * FROM users LIMIT 5\u201d\u007d \u201c\u8bfbnginx\u65e5\u5fd7\u201d \u2192 \u007b\u201ctool\u201d: \u201cfile\u201d, \u201cpath\u201d: \u201c/var/log/nginx/access.log\u201d\u007d"
)


def _build_user_suffix(parser_cfg: ParserConfig | None) -> str:
    """说明书 4.1 系统提示词保持不变；此处对齐 3.1 流程（时间条件→SQL）并抑制臆造列名。"""
    parts: list[str] = []
    if parser_cfg is not None:
        col = (parser_cfg.database_default_time_column or "created_at").strip()
        if not col.replace("_", "").isalnum():  # 简单防注入列名
            col = "created_at"
        parts.append(
            "\n\n【解析补充规则·对齐说明书 3.1 database】\n"
            "1) query 中的列名必须与真实表一致，禁止臆造未在用户话里出现的列名（例如不要随意使用 date）。\n"
            "2) 用户若明确给出时间列名（如 record_time、gmt_create），必须使用该列名。\n"
            f"3) 用户未给出时间列名且涉及「昨天/昨日/今天」等日期范围时，使用列 `{col}`（MySQL 示例）：\n"
            f"   - 昨天整天：`WHERE {col} >= DATE_SUB(CURDATE(), INTERVAL 1 DAY) AND {col} < CURDATE()`\n"
            f"   - 与说明书示例一致的可比形式：`WHERE {col} >= CONCAT(DATE_SUB(CURDATE(), INTERVAL 1 DAY), ' 00:00:00')` 等，但禁止编造列名。\n"
            f"4) 「最近一小时/过去一小时」且用户未给时间列名：仍优先用 `{col}`，MySQL 示例：`WHERE {col} >= NOW() - INTERVAL 1 HOUR`。\n"
            "5) 「主库」「日志库」：connection 必须填本应用 config.yaml 里 `database` 下已存在的键名"
            "（常见为 main_db、log_db、recording 等，以实际配置为准）；勿发明不存在的 connection。\n"
            "6) 「error 级别」等：使用真实表里级别字段名（如 level、severity），与用户表述一致；不得臆造列名。\n"
            "7) 仅输出一条合法 SELECT（与执行层规则一致）。\n"
            "8) **用户数据 vs 录音数据**：出现「用户数据/用户信息/用户表/users/项目用户/账号」等时，"
            "query 必须用 `FROM users`；仅当用户明确要「录音数据/录音内容/录音记录」时才用 `FROM recordings`。"
            "「录音笔」是产品/项目名，不等于查录音表；例如「录音笔项目用户数据」→ `SELECT * FROM users LIMIT n`。\n"
            "9) **天气查询**（新增工具 weather，不影响 browser/database/file/api）：\n"
            "   - 用户问天气、气温、下雨、冷不冷、湿度、风力等 → "
            '`{"tool":"weather","city":"城市名"}`\n'
            "   - city 用中文或英文地名；未指定城市时使用配置默认城市。\n"
            "   - 示例：「北京今天天气怎么样」→ `{\"tool\":\"weather\",\"city\":\"北京\"}`"
        )
        extra = (parser_cfg.database_extra_hints or "").strip()
        if extra:
            parts.append("\n【业务表结构提示】\n" + extra)
    parts.append("\n\n请仅输出一个 JSON 对象（键名用英文），对应上述工具类型与参数，不要其它说明或 markdown 围栏。")
    return "".join(parts)


async def parse_user_message(
    llm: LLMClient,
    message: str,
    *,
    parser_cfg: ParserConfig | None = None,
) -> dict[str, Any]:
    data = await llm.complete_json(
        system_prompt=_SYSTEM_PROMPT,
        user_message=message + _build_user_suffix(parser_cfg),
    )
    if "tool" not in data:
        raise ValueError(f"LLM output missing 'tool': {json.dumps(data, ensure_ascii=False)}")
    return correct_database_parse(message, data)
