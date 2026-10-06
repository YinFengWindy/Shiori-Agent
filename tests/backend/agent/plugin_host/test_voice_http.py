"""Bounded host voice transport preserves provider URL policy on redirects."""

import urllib.error
import urllib.request
import pytest
from agent.plugin_host.voice_http import VoiceHttp, VOICE_HTTP_TIMEOUT_SECONDS
from shiori_sdk.voice import VoiceServiceError


def test_binary_download_uses_host_timeout_and_rechecks_every_redirect(monkeypatch):
    validated = []

    def validate(url):
        validated.append(url)
        if url.endswith("/private"):
            raise VoiceServiceError("invalid target")
        return url

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return b"preview"

    class Opener:
        def __init__(self, handler):
            self.handler = handler

        def open(self, request, *, timeout):
            assert timeout == VOICE_HTTP_TIMEOUT_SECONDS
            with pytest.raises(VoiceServiceError, match="invalid target"):
                self.handler.redirect_request(
                    request, None, 302, "Found", {}, "/private"
                )
            return Response()

    monkeypatch.setattr(urllib.request, "build_opener", Opener)
    assert (
        VoiceHttp().request_binary("https://provider.test/audio", validate_url=validate)
        == b"preview"
    )
    assert validated == ["https://provider.test/audio", "https://provider.test/private"]


def test_json_invalid_response_retains_structured_transport_error(monkeypatch):
    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return b"not-json"

    monkeypatch.setattr(urllib.request, "urlopen", lambda *_args, **_kwargs: Response())
    with pytest.raises(VoiceServiceError) as raised:
        VoiceHttp().request_json("https://provider.test/", {}, b"request")
    assert raised.value.error_code == "invalid_json"
