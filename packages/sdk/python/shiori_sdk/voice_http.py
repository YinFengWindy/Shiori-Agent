"""Blocking HTTP contract; transport and bounded requests remain host-owned."""

from collections.abc import Callable, Iterable
from typing import Any, Protocol

JsonRequester = Callable[[str, dict[str, str], bytes], dict[str, Any]]
StreamRequester = Callable[[str, dict[str, str], bytes], Iterable[bytes]]
MultipartRequester = Callable[
    [str, dict[str, str], dict[str, str], str, str, bytes], dict[str, Any]
]
BinaryRequester = Callable[[str], bytes]


class VoiceHttp(Protocol):
    """Synchronous speech workers share the injected host HTTP implementation."""

    def request_json(
        self, url: str, headers: dict[str, str], body: bytes
    ) -> dict[str, Any]: ...
    def request_stream(
        self, url: str, headers: dict[str, str], body: bytes
    ) -> Iterable[bytes]: ...
    def request_multipart(
        self,
        url: str,
        headers: dict[str, str],
        fields: dict[str, str],
        file_name: str,
        content_type: str,
        file_content: bytes,
    ) -> dict[str, Any]: ...
    def request_binary(
        self, url: str, *, validate_url: Callable[[str], str]
    ) -> bytes: ...
