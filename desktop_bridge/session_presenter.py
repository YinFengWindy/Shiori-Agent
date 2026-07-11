from __future__ import annotations

from typing import Any

from conversation.service import ConversationService
from session.manager import Session


class DesktopSessionPresenter:
    """Builds desktop session payloads from formal thread and runtime state."""

    def __init__(
        self,
        conversation_service: ConversationService,
        relationship_runtime: Any | None = None,
    ) -> None:
        self._conversation_service = conversation_service
        self._relationship_runtime = relationship_runtime

    def serialize(self, session: Session) -> dict[str, Any]:
        """Returns the desktop-compatible view of a thread runtime adapter."""
        thread = self._conversation_service.get_thread_for_runtime(
            session.key,
            thread_id=str(session.metadata.get("thread_id") or ""),
        )
        return {
            "key": session.key,
            "created_at": session.created_at.isoformat(),
            "updated_at": session.updated_at.isoformat(),
            "last_consolidated": session.last_consolidated,
            "metadata": self._enrich_metadata(dict(session.metadata)),
            "thread": (
                self._conversation_service.serialize_thread(thread)
                if thread is not None
                else None
            ),
            "messages": [self._serialize_message(message) for message in session.messages],
        }

    def _enrich_metadata(self, metadata: dict[str, Any]) -> dict[str, Any]:
        if self._relationship_runtime is None:
            return metadata
        return self._relationship_runtime.enrich_session_metadata(metadata)

    @staticmethod
    def _serialize_message(message: dict[str, Any]) -> dict[str, Any]:
        metadata = message.get("metadata")
        merged_metadata = dict(metadata) if isinstance(metadata, dict) else {}
        skip_keys = {
            "id",
            "session_key",
            "seq",
            "role",
            "content",
            "timestamp",
            "reasoning_content",
            "tool_chain",
            "media",
            "metadata",
        }
        for key, value in message.items():
            if key not in skip_keys:
                merged_metadata[key] = value
        return {
            "id": message.get("id"),
            "role": message.get("role"),
            "content": message.get("content"),
            "timestamp": message.get("timestamp"),
            "reasoning_content": message.get("reasoning_content"),
            "media": list(message.get("media") or []),
            "metadata": merged_metadata,
        }
