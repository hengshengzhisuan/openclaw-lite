from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, model_validator


class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000


class LLMConfig(BaseModel):
    provider: str = "openai"
    model: str = "gpt-3.5-turbo"
    api_key: str = ""
    base_url: str = ""
    timeout: int = 10
    max_tokens: int = 2048
    cache_ttl_seconds: int = 3600
    # 部分自建 OpenAI 兼容网关不支持 response_format=json_object，可设为 false
    json_response_format: bool = True

    @model_validator(mode="after")
    def _coalesce_model(self) -> LLMConfig:
        if not (self.model or "").strip():
            self.model = "gpt-3.5-turbo"
        return self


class DatabaseConnectionConfig(BaseModel):
    url: str
    max_rows: int = 10
    timeout: int = 5


class FileAccessConfig(BaseModel):
    allowed_paths: list[str] = Field(default_factory=list)
    max_lines: int = 100


class ApiAccessConfig(BaseModel):
    whitelist: list[str] = Field(default_factory=list)
    timeout: int = 5


class BrowserConfig(BaseModel):
    """说明书未单独列 browser 段；导航超时单独配置，不限制外网 URL（仅允许 http/https）。"""

    navigation_timeout_seconds: int = 30


class ParserConfig(BaseModel):
    """说明书 3.1 一句话执行：在不动 4.1 系统提示词的前提下，用用户消息后缀补强 database 的日期/SQL 规则。"""

    # 「昨天/今日/新增」等且用户未给出时间列名时，query 里使用的默认列名（与说明书示例 orders.created_at 一致）
    database_default_time_column: str = "created_at"
    # 业务表结构提示，拼进解析后缀（如：recordings 表时间列为 xxx）
    database_extra_hints: str = ""


class ImFeishuConfig(BaseModel):
    app_id: str = ""
    app_secret: str = ""
    encrypt_key: str = ""
    # 与飞书事件订阅「Verification Token」一致时校验 header.token / token 字段；空则不校验
    verification_token: str = ""


class ImWechatConfig(BaseModel):
    corp_id: str = ""
    secret: str = ""
    agent_id: str = ""
    # 回调 URL 校验用（企业微信管理后台「Token」）；完整加解密需 EncodingAESKey，见 core/im/wechat_stub.py 说明
    callback_token: str = ""


class ImConfig(BaseModel):
    feishu: ImFeishuConfig = Field(default_factory=ImFeishuConfig)
    wechat: ImWechatConfig = Field(default_factory=ImWechatConfig)


class AppSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    server: ServerConfig = Field(default_factory=ServerConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    database: dict[str, DatabaseConnectionConfig] = Field(default_factory=dict)
    # LLM 可能输出 default_db / primary_db 等别名，映射到 config.database 下真实键名
    database_connection_aliases: dict[str, str] = Field(default_factory=dict)
    file: FileAccessConfig = Field(default_factory=FileAccessConfig)
    api: ApiAccessConfig = Field(default_factory=ApiAccessConfig)
    browser: BrowserConfig = Field(default_factory=BrowserConfig)
    im: ImConfig = Field(default_factory=ImConfig)
    parser: ParserConfig = Field(default_factory=ParserConfig)

    def resolve_database_connection(self, raw: str) -> str:
        name = (raw or "").strip()
        if not name:
            return name
        seen: set[str] = set()
        aliases = self.database_connection_aliases
        while name in aliases and name not in seen:
            seen.add(name)
            name = aliases[name].strip()
            if len(seen) > 20:
                break
        return name


_ENV_PATTERN = re.compile(r"\$\{([^}]+)\}")


def _substitute_env(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _substitute_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute_env(v) for v in value]
    if isinstance(value, str):

        def repl(m: re.Match[str]) -> str:
            key = m.group(1)
            return os.environ.get(key, "")

        return _ENV_PATTERN.sub(repl, value)
    return value


def load_settings(
    config_path: str | Path | None = None,
    *,
    dotenv_path: str | Path | None = None,
) -> AppSettings:
    # override=True：避免 shell 里残留的旧 DATABASE_* 覆盖 .env 中的修改
    load_dotenv(dotenv_path or Path(".env"), override=True)
    path = Path(config_path or os.environ.get("OPENCLAW_CONFIG", "config.yaml"))
    if not path.is_file():
        raise FileNotFoundError(f"Config file not found: {path.resolve()}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    merged = _substitute_env(raw)
    return AppSettings.model_validate(merged)
