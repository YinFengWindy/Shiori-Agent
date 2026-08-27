"""Shell 命令、网络目标与受限目录校验。"""

from __future__ import annotations

import ipaddress
import os
import shlex
from pathlib import Path, PureWindowsPath
from urllib.parse import urlparse

from .constants import (
    _IS_WINDOWS,
    _NETWORK_CMDS,
    _NET_WRITE_FLAGS,
    _RESTRICTED_META_CHARS,
    _RESTRICTED_SHELL_RUNNERS,
)


def _validate_command(
    command: str,
    *,
    allow_network: bool,
    restricted_dir: Path | None,
    cwd: Path | None = None,
) -> str | None:
    try:
        tokens = _split_command(command)
    except ValueError:
        return "命令解析失败，请检查引号是否匹配"
    if not tokens:
        return None

    cmd = tokens[0].lower()
    if not allow_network and cmd in _NETWORK_CMDS:
        return "当前 shell 配置禁止网络访问"

    if restricted_dir is not None:
        cwd_err = _validate_restricted_cwd(cwd, restricted_dir)
        if cwd_err:
            return cwd_err
        restricted_err = _validate_restricted_command(tokens, restricted_dir)
        if restricted_err:
            return restricted_err

    return _validate_network_command(command)


def _validate_network_command(command: str) -> str | None:
    """网络命令护栏：仅允许 HTTP(S) 且禁止内网目标与写入类参数。"""
    try:
        tokens = _split_command(command)
    except ValueError:
        return "命令解析失败，请检查引号是否匹配"
    if not tokens:
        return None

    cmd = tokens[0].lower()
    if cmd not in _NETWORK_CMDS:
        return None

    # 阻止文件写入/上传相关参数
    for t in tokens[1:]:
        low = t.lower()
        if low in _NET_WRITE_FLAGS:
            return f"网络命令参数 '{t}' 不被允许（禁止上传/写文件）"
        if any(low.startswith(flag + "=") for flag in _NET_WRITE_FLAGS):
            return f"网络命令参数 '{t}' 不被允许（禁止上传/写文件）"
        # httpie/xh 支持 field=@file 语法上传文件
        if "=@" in t or t.startswith("@"):
            return f"网络命令参数 '{t}' 不被允许（禁止本地文件上传）"

    # 提取 URL 并校验
    urls = [t for t in tokens[1:] if t.startswith(("http://", "https://"))]
    if not urls:
        return "网络命令必须显式提供 http:// 或 https:// URL"

    for u in urls:
        err = _validate_url_target(u)
        if err:
            return err
    return None


def _validate_url_target(url: str) -> str | None:
    """校验 URL 目标是否为合法的公网地址。"""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return "仅允许 http:// 或 https:// URL"
    host = (parsed.hostname or "").strip().lower()
    if not host:
        return "URL 缺少主机名"

    try:
        # IP 地址：禁止回环、私有、链路本地、保留地址
        ip = ipaddress.ip_address(host)
        if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_reserved:
            return f"禁止访问内网/本地地址：{host}"
    except ValueError:
        # 域名：阻断常见本地域名后缀
        if host.endswith(".local") or host.endswith(".localhost"):
            return f"禁止访问本地域名：{host}"
    return None


def _validate_restricted_command(tokens: list[str], restricted_dir: Path) -> str | None:
    command = " ".join(tokens)
    if any(marker in command for marker in _RESTRICTED_META_CHARS):
        return "受限 shell 禁止管道、重定向或串联命令"

    base_cmd = tokens[0].lower()
    if base_cmd in _RESTRICTED_SHELL_RUNNERS:
        return f"受限 shell 禁止启动解释器或二级 shell：{base_cmd}"

    for token in tokens[1:]:
        if token.startswith("-") or token == "--":
            continue
        err = _validate_restricted_token(token, restricted_dir)
        if err:
            return err
    return None


def _validate_restricted_cwd(cwd: Path | None, restricted_dir: Path) -> str | None:
    if cwd is None:
        return None
    try:
        resolved = cwd.resolve()
    except OSError:
        resolved = cwd
    if resolved != restricted_dir and restricted_dir not in resolved.parents:
        return f"受限 shell 禁止使用任务目录外工作目录：{cwd}"
    return None


def _validate_restricted_token(token: str, restricted_dir: Path) -> str | None:
    token = _strip_shell_quotes(token)
    if token.startswith("~"):
        return f"受限 shell 禁止访问任务目录外路径：{token}"

    if not _looks_like_path(token):
        return None

    parts = PureWindowsPath(token).parts if _IS_WINDOWS else Path(token).parts
    if any(part == ".." for part in parts):
        return f"受限 shell 禁止访问父级路径：{token}"

    win_path = PureWindowsPath(token)
    if _IS_WINDOWS and (win_path.drive or win_path.root):
        return _validate_restricted_absolute_path(token, restricted_dir)

    path = Path(token)
    if path.is_absolute():
        return _validate_restricted_absolute_path(token, restricted_dir)
    return None


def _split_command(command: str) -> list[str]:
    return [
        _strip_shell_quotes(token)
        for token in shlex.split(command, posix=not _IS_WINDOWS)
    ]


def _strip_shell_quotes(token: str) -> str:
    if len(token) >= 2 and token[0] == token[-1] and token[0] in {'"', "'"}:
        return token[1:-1]
    return token


def _validate_restricted_absolute_path(token: str, restricted_dir: Path) -> str | None:
    if _IS_WINDOWS and os.name != "nt":
        return f"受限 shell 禁止访问任务目录外路径：{token}"
    path = Path(token)
    win_path = PureWindowsPath(token)
    if _IS_WINDOWS and (win_path.drive or win_path.root) and not path.is_absolute():
        return f"受限 shell 禁止访问任务目录外路径：{token}"
    if path.is_absolute():
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        try:
            restricted_resolved = restricted_dir.resolve()
        except OSError:
            restricted_resolved = restricted_dir
        if resolved != restricted_resolved and restricted_resolved not in resolved.parents:
            return f"受限 shell 禁止访问任务目录外路径：{token}"
    return None


def _looks_like_path(token: str) -> bool:
    if token in {".", ".."}:
        return True
    if _IS_WINDOWS:
        win_path = PureWindowsPath(token)
        return (
            "\\" in token
            or "/" in token
            or bool(win_path.drive)
            or token.startswith((".", "~"))
        )
    return "/" in token or token.startswith((".", "~"))
