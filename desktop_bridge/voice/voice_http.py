from __future__ import annotations

import json
import ipaddress
import socket
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections.abc import Callable, Iterable, Iterator
from typing import Any

from desktop_bridge.voice.voice_models import VoiceServiceError

JsonRequester = Callable[[str, dict[str, str], bytes], dict[str, Any]]
StreamRequester = Callable[[str, dict[str, str], bytes], Iterable[bytes]]
MultipartRequester = Callable[
    [str, dict[str, str], dict[str, str], str, str, bytes],
    dict[str, Any],
]
BinaryRequester = Callable[[str], bytes]

_ALLOWED_PREVIEW_HOST_SUFFIXES = ("minimaxi.com", "minimax.chat")
VOICE_HTTP_TIMEOUT_SECONDS = 60


def _validate_preview_url(url: str) -> str:
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


class _PreviewRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        safe_url = _validate_preview_url(urllib.parse.urljoin(req.full_url, newurl))
        return super().redirect_request(req, fp, code, msg, headers, safe_url)


def request_json(url: str, headers: dict[str, str], body: bytes) -> dict[str, Any]:
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=VOICE_HTTP_TIMEOUT_SECONDS) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise VoiceServiceError(
            f"语音服务 HTTP {exc.code}: {detail[:500]}",
            error_code=f"http_{exc.code}",
        ) from exc
    except urllib.error.URLError as exc:
        raise VoiceServiceError(
            f"语音服务网络错误: {exc.reason}",
            error_code="network_error",
        ) from exc
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VoiceServiceError(
            "语音服务返回了无效 JSON",
            error_code="invalid_json",
        ) from exc
    if not isinstance(value, dict):
        raise VoiceServiceError("语音服务返回格式无效", error_code="invalid_response")
    return value


def request_stream(url: str, headers: dict[str, str], body: bytes) -> Iterator[bytes]:
    """Yields provider response chunks without retaining the complete response."""

    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=VOICE_HTTP_TIMEOUT_SECONDS) as response:
            for chunk in response:
                if chunk:
                    yield bytes(chunk)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise VoiceServiceError(
            f"语音服务 HTTP {exc.code}: {detail[:500]}",
            error_code=f"http_{exc.code}",
        ) from exc
    except urllib.error.URLError as exc:
        raise VoiceServiceError(
            f"语音服务网络错误: {exc.reason}",
            error_code="network_error",
        ) from exc


def request_multipart(
    url: str,
    headers: dict[str, str],
    fields: dict[str, str],
    file_name: str,
    content_type: str,
    file_content: bytes,
) -> dict[str, Any]:
    """Uploads one transient file without persisting it in the bridge."""

    boundary = f"----ShioriVoice{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                str(value).encode("utf-8"),
                b"\r\n",
            ]
        )
    chunks.extend(
        [
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="file"; filename="{file_name}"\r\n'.encode(),
            f"Content-Type: {content_type}\r\n\r\n".encode(),
            file_content,
            b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
    )
    request_headers = {
        **headers,
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    }
    return request_json(url, request_headers, b"".join(chunks))


def request_binary(url: str) -> bytes:
    """Downloads provider-generated preview audio without writing a local file."""

    request = urllib.request.Request(_validate_preview_url(url), method="GET")
    opener = urllib.request.build_opener(_PreviewRedirectHandler())
    try:
        with opener.open(request, timeout=VOICE_HTTP_TIMEOUT_SECONDS) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        raise VoiceServiceError(
            f"语音试听 HTTP {exc.code}",
            error_code=f"http_{exc.code}",
        ) from exc
    except urllib.error.URLError as exc:
        raise VoiceServiceError(
            f"语音试听网络错误: {exc.reason}",
            error_code="network_error",
        ) from exc
