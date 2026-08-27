from __future__ import annotations

import urllib.request

import pytest

from desktop_bridge.voice.voice_http import (
    VOICE_HTTP_TIMEOUT_SECONDS,
    _PreviewRedirectHandler,
    request_binary,
)
from desktop_bridge.voice.voice_models import VoiceServiceError


class _Response:
    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def read(self) -> bytes:
        return b"preview"


class _Opener:
    def open(self, request, *, timeout: int):
        assert request.full_url == "https://api.minimaxi.com/demo.mp3"
        assert timeout == VOICE_HTTP_TIMEOUT_SECONDS
        return _Response()


def test_request_binary_allows_trusted_minimax_https(monkeypatch) -> None:
    monkeypatch.setattr(
        "desktop_bridge.voice.voice_http.socket.getaddrinfo",
        lambda *_args, **_kwargs: [(2, 1, 6, "", ("93.184.216.34", 443))],
    )
    monkeypatch.setattr(urllib.request, "build_opener", lambda *_args: _Opener())

    assert request_binary("https://api.minimaxi.com/demo.mp3") == b"preview"


@pytest.mark.parametrize(
    "url",
    [
        "file:///C:/Windows/win.ini",
        "http://api.minimaxi.com/demo.mp3",
        "https://127.0.0.1/demo.mp3",
        "https://example.com/demo.mp3",
    ],
)
def test_request_binary_rejects_untrusted_or_local_urls(url: str) -> None:
    with pytest.raises(VoiceServiceError, match="试听地址"):
        request_binary(url)


def test_request_binary_rejects_private_dns_targets(monkeypatch) -> None:
    monkeypatch.setattr(
        "desktop_bridge.voice.voice_http.socket.getaddrinfo",
        lambda *_args, **_kwargs: [(2, 1, 6, "", ("10.0.0.2", 443))],
    )

    with pytest.raises(VoiceServiceError, match="试听地址不可访问"):
        request_binary("https://api.minimaxi.com/demo.mp3")


def test_preview_redirect_revalidates_the_target() -> None:
    request = urllib.request.Request("https://api.minimaxi.com/demo.mp3")

    with pytest.raises(VoiceServiceError, match="试听地址"):
        _PreviewRedirectHandler().redirect_request(
            request,
            None,
            302,
            "Found",
            {},
            "https://127.0.0.1/private.mp3",
        )
