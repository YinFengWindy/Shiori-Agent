"""Session operations whose persistence and desktop projection belong to the host."""

from __future__ import annotations


from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from desktop_bridge.session_presenter import DesktopSessionPresenter
from session.manager import SessionManager
from session.media_assets import original_media_path
from shiori_sdk.sessions import PluginSessions


class HostPluginSessions:
    """Allow media regeneration without exporting session storage/presenter internals."""

    def __init__(
        self,
        manager: SessionManager,
        workspace: Path,
        presenter: DesktopSessionPresenter,
    ):
        self._manager, self._workspace, self._presenter = manager, workspace, presenter

    def get_or_create(self, key: str):
        """Read the session metadata through its owning manager."""
        return self._manager.get_or_create(key)

    def role_session_key(self, role_id: str) -> str:
        """Resolve the canonical role session key."""
        return self._manager.role_session_key(role_id)

    def original_media_path(self, value: str) -> str:
        """Resolve provenance of a session-owned copy."""
        return original_media_path(self._workspace, value)

    def get_message_media(
        self, *, session_key: str, message_id: str, media_index: int
    ) -> str:
        """Read the media selected for an atomic replacement."""
        return self._manager.get_message_media(
            session_key=session_key, message_id=message_id, media_index=media_index
        )

    async def replace_message_media(
        self,
        *,
        session_key: str,
        message_id: str,
        media_index: int,
        expected_path: str,
        new_path: str,
    ) -> dict[str, object]:
        """Atomically replace media then project the updated session and message."""
        session = await self._manager.replace_message_media(
            session_key=session_key,
            message_id=message_id,
            media_index=media_index,
            expected_path=expected_path,
            new_path=new_path,
        )
        message = next(
            item for item in session.messages if str(item.get("id") or "") == message_id
        )
        return {
            "session": self._presenter.serialize_summary(session),
            "message": self._presenter.serialize_message(message),
        }

    def as_capability(self) -> PluginSessions:
        """Check the real owner adapter against the plugin contract."""
        return self
