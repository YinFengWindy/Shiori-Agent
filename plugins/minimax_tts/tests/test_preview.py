import pytest
from plugins.minimax_tts.backend.preview import validate_preview_url
from shiori_sdk.voice import VoiceServiceError


def test_preview_url_allows_trusted_minimax_https(monkeypatch):
    monkeypatch.setattr(
        "plugins.minimax_tts.backend.preview.socket.getaddrinfo",
        lambda *_args, **_kwargs: [(2, 1, 6, "", ("93.184.216.34", 443))],
    )
    assert (
        validate_preview_url("https://api.minimaxi.com/demo.mp3")
        == "https://api.minimaxi.com/demo.mp3"
    )


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
        validate_preview_url(url)


def test_request_binary_rejects_private_dns_targets(monkeypatch) -> None:
    monkeypatch.setattr(
        "plugins.minimax_tts.backend.preview.socket.getaddrinfo",
        lambda *_args, **_kwargs: [(2, 1, 6, "", ("10.0.0.2", 443))],
    )

    with pytest.raises(VoiceServiceError, match="试听地址不可访问"):
        validate_preview_url("https://api.minimaxi.com/demo.mp3")
