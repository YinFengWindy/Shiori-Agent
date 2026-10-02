"""Identity lookup views backed by the host session metadata owner."""

from collections.abc import Callable
from typing import Protocol


class SessionIdentityIndex(Protocol):
    """Normalize, resolve and remember one channel's private delivery identities."""

    @property
    def mapping(self) -> dict[str, str]: ...
    def rebuild(self) -> dict[str, str]: ...
    def resolve(self, identity: str) -> str | None: ...
    async def remember(self, identity: str, chat_id: str) -> None: ...


class IdentityIndexes(Protocol):
    """Create a metadata-backed view with plugin-selected normalization and admission."""

    def identity_index(
        self,
        *,
        channel: str,
        metadata_key: str,
        normalizer: Callable[[str], str] | None = None,
        accepts_chat_id: Callable[[str], bool] | None = None,
    ) -> SessionIdentityIndex: ...
