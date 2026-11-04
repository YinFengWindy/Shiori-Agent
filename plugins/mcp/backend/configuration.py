"""Validate connection edits before committing any private material."""

import re
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from pydantic import TypeAdapter
from .models import LaunchCredentials, McpConfigError, StdioTransport, Transport

_TRANSPORT = TypeAdapter(Transport)
_HEADER_NAME = re.compile(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+")
_RESERVED_HEADERS = {
    "accept",
    "content-type",
    "content-length",
    "host",
    "connection",
    "transfer-encoding",
    "upgrade",
    "cookie",
    "proxy-authorization",
    "last-event-id",
    "origin",
}


def secret_values(credentials: LaunchCredentials) -> list[str]:
    """Known private values, including individual query values in a private URL."""
    return [
        *credentials.env.values(),
        *credentials.command[1:],
        *credentials.headers.values(),
        credentials.bearer or "",
        credentials.url or "",
        *(value for _, value in parse_qsl(urlsplit(credentials.url or "").query)),
    ]


def edit_value(edit: dict[str, Any], old: object) -> object:
    """Apply explicit keep/replace/delete without interpreting empty inputs."""
    if edit.get("op") == "keep":
        return old
    if edit.get("op") == "replace":
        return edit["value"]
    if edit.get("op") == "delete":
        return None
    raise McpConfigError("凭据编辑方式无效")


def connection_edit(raw: object, edits: dict[str, Any], old: LaunchCredentials | None):
    """Return a validated transport and private record; never echo invalid input."""
    transport = _TRANSPORT.validate_python(raw)
    values = (old or LaunchCredentials()).model_dump()
    for name, previous in values.items():
        value = edit_value(edits.get(name, {"op": "keep"}), previous)
        values[name] = (
            value
            if value is not None
            else (
                [] if name == "command" else {} if name in {"env", "headers"} else None
            )
        )
    credentials = LaunchCredentials.model_validate(values)
    validate_connection(transport, credentials)
    return transport, credentials


def validate_connection(transport: Transport, credentials: LaunchCredentials) -> None:
    """Enforce URL/header/launch boundaries for both saved data and new edits."""
    if isinstance(transport, StdioTransport):
        if not credentials.command or any(
            not part or "\x00" in part for part in credentials.command
        ):
            raise McpConfigError("启动命令需要非空的 JSON 字符串数组")
        if any(
            not key or "=" in key or "\x00" in key + value
            for key, value in credentials.env.items()
        ):
            raise McpConfigError("环境变量名称或值无效")
        return
    url = credentials.url
    if not url or any(ord(char) <= 32 or ord(char) == 127 for char in url):
        raise McpConfigError("HTTP 地址不能为空或包含空白字符")
    try:
        parsed = urlsplit(url)
        port = parsed.port
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or port == 0:
            raise ValueError
        if parsed.username is not None or parsed.password is not None or "#" in url:
            raise ValueError
    except ValueError:
        raise McpConfigError(
            "HTTP 地址必须使用 http(s)，且不能包含账号或 fragment"
        ) from None
    seen: set[str] = set()
    for name, value in credentials.headers.items():
        lowered = name.lower()
        if not _HEADER_NAME.fullmatch(name) or lowered in seen:
            raise McpConfigError("请求头名称无效或重复")
        if lowered in _RESERVED_HEADERS or lowered.startswith("mcp-"):
            raise McpConfigError("不能覆盖 MCP 或 HTTP 协议保留请求头")
        if any(ord(char) < 32 or ord(char) > 126 for char in value):
            raise McpConfigError("请求头值不能包含换行、控制字符或非 ASCII 字符")
        seen.add(lowered)
    if "authorization" in seen and transport.auth != "headers":
        raise McpConfigError(
            "Authorization 请求头只能用于自定义请求头认证，不能与 Bearer 混用"
        )
    if transport.auth == "bearer" and (
        not credentials.bearer
        or not re.fullmatch(r"[A-Za-z0-9._~+/=-]+", credentials.bearer)
    ):
        raise McpConfigError("Bearer token 不能为空或包含空白、控制字符")
