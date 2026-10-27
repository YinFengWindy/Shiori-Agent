"""Session views plugins read through the ``sessions`` capability."""

from typing import Protocol


class SessionView(Protocol):
    """Read-only metadata needed by role-based plugin events."""

    @property
    def metadata(self) -> dict[str, object]: ...


class PluginSessions(Protocol):
    """Metadata, original media and atomic replacement with host-owned presentation."""

    def get_or_create(self, key: str) -> SessionView: ...
    def role_session_key(self, role_id: str) -> str: ...
    def original_media_path(self, value: str) -> str: ...
    def get_message_media(
        self, *, session_key: str, message_id: str, media_index: int
    ) -> str: ...
    async def replace_message_media(
        self,
        *,
        session_key: str,
        message_id: str,
        media_index: int,
        expected_path: str,
        new_path: str,
    ) -> dict[str, object]: ...
