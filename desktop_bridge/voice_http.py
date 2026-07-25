from __future__ import annotations

import json
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable, Iterable, Iterator
from typing import Any

from desktop_bridge.voice_models import VoiceServiceError

JsonRequester = Callable[[str, dict[str, str], bytes], dict[str, Any]]
StreamRequester = Callable[[str, dict[str, str], bytes], Iterable[bytes]]
MultipartRequester = Callable[
    [str, dict[str, str], dict[str, str], str, str, bytes],
    dict[str, Any],
]
BinaryRequester = Callable[[str], bytes]


def request_json(url: str, headers: dict[str, str], body: bytes) -> dict[str, Any]:
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
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
        with urllib.request.urlopen(request, timeout=60) as response:
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

    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
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
