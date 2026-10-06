"""Voice plugin setup doubles with no host installation or network access."""

from shiori_sdk.voice import AsrProvider, TtsProvider, VoicePluginContext
from shiori_sdk.voice_http import (
    JsonRequester,
    StreamRequester,
    MultipartRequester,
    BinaryRequester,
)
from collections.abc import Callable, Iterable
from typing import Any
from .context import FakePluginContext
from .extensions import FakeConfig


class FakeVoice:
    """Records contributions and registers their cleanup on the fake plugin scope."""

    def __init__(self, context: FakePluginContext) -> None:
        self._context = context
        self.http = FakeVoiceHttp()
        self.asr: dict[str, AsrProvider] = {}
        self.tts: dict[str, TtsProvider] = {}

    def register_asr(self, provider: AsrProvider) -> None:
        """Records recognition until the plugin's context is closed."""
        if provider.info.id in self.asr:
            raise ValueError("Duplicate ASR provider")

        def remove() -> None:
            self.asr.pop(provider.info.id, None)

        self._context.effect("voice:asr", remove)
        self.asr[provider.info.id] = provider

    def register_tts(self, provider: TtsProvider) -> None:
        """Records synthesis until the plugin's context is closed."""
        if provider.info.id in self.tts:
            raise ValueError("Duplicate TTS provider")

        def remove() -> None:
            self.tts.pop(provider.info.id, None)

        self._context.effect("voice:tts", remove)
        self.tts[provider.info.id] = provider


class FakeVoiceContext(FakePluginContext):
    """Provides the same typed config and voice setup boundary as the host."""

    def __init__(
        self, plugin_id: str, *, config: dict[str, object] | None = None
    ) -> None:
        super().__init__(plugin_id, capabilities=("voice", "config"))
        self.config = FakeConfig(config)
        self.voice = FakeVoice(self)

    def as_capability(self) -> VoicePluginContext:
        """Statically checks provider setup without a host runtime."""
        return self


class FakeVoiceHttp:
    """Inject explicit responses without constructing a network transport."""

    def __init__(
        self,
        *,
        requester: JsonRequester | None = None,
        stream_requester: StreamRequester | None = None,
        upload_requester: MultipartRequester | None = None,
        binary_requester: BinaryRequester | None = None,
    ):
        self._json = requester
        self._stream = stream_requester
        self._multipart = upload_requester
        self._binary = binary_requester

    def request_json(
        self, url: str, headers: dict[str, str], body: bytes
    ) -> dict[str, Any]:
        """Invokes the supplied JSON response function."""
        if self._json is None:
            raise AssertionError("No JSON response configured")
        return self._json(url, headers, body)

    def request_stream(
        self, url: str, headers: dict[str, str], body: bytes
    ) -> Iterable[bytes]:
        """Invokes the supplied stream response function."""
        if self._stream is None:
            raise AssertionError("No stream response configured")
        return self._stream(url, headers, body)

    def request_multipart(
        self,
        url: str,
        headers: dict[str, str],
        fields: dict[str, str],
        file_name: str,
        content_type: str,
        file_content: bytes,
    ) -> dict[str, Any]:
        """Invokes the supplied upload response function."""
        if self._multipart is None:
            raise AssertionError("No multipart response configured")
        return self._multipart(
            url, headers, fields, file_name, content_type, file_content
        )

    def request_binary(self, url: str, *, validate_url: Callable[[str], str]) -> bytes:
        """Returns fake preview bytes; URL-policy DNS and transport are separate tests."""
        if self._binary is None:
            raise AssertionError("No binary response configured")
        return self._binary(url)
