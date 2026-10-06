"""MiniMax preview downloads enforce trusted HTTPS hosts and redirect targets."""

from __future__ import annotations
import ipaddress
import socket
import urllib.parse
from shiori_sdk.voice import VoiceServiceError

_ALLOWED_PREVIEW_HOST_SUFFIXES = ("minimaxi.com", "minimax.chat")


def validate_preview_url(url: str) -> str:
    """Rejects local addresses and non-MiniMax preview hosts before transport."""
    parsed = urllib.parse.urlsplit(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme != "https" or not host or parsed.username or parsed.password:
        raise VoiceServiceError("语音试听地址无效", error_code="invalid_preview_url")
    if parsed.port not in (None, 443):
        raise VoiceServiceError(
            "语音试听地址端口无效", error_code="invalid_preview_url"
        )
    try:
        addresses = [ipaddress.ip_address(host)]
    except ValueError:
        try:
            addresses = [
                ipaddress.ip_address(sockaddr[4][0])
                for sockaddr in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
            ]
        except (OSError, ValueError) as exc:
            raise VoiceServiceError(
                "语音试听地址不可解析", error_code="invalid_preview_url"
            ) from exc
        if not addresses:
            raise VoiceServiceError(
                "语音试听地址不可解析", error_code="invalid_preview_url"
            )
    if any(
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_unspecified
        for address in addresses
    ):
        raise VoiceServiceError(
            "语音试听地址不可访问", error_code="invalid_preview_url"
        )
    if not any(
        host == suffix or host.endswith(f".{suffix}")
        for suffix in _ALLOWED_PREVIEW_HOST_SUFFIXES
    ):
        raise VoiceServiceError(
            "语音试听地址不受信任", error_code="invalid_preview_url"
        )
    return urllib.parse.urlunsplit(parsed)
