from __future__ import annotations

from conversation.models import ThreadRecord
from conversation.store import ConversationStore


class ConversationStateProjector:
    """Rebuilds derived thread, contact, and role state from message facts."""

    def __init__(self, store: ConversationStore) -> None:
        self._store = store

    def project_thread(self, thread: ThreadRecord) -> None:
        """Projects current message counts after a successful fact write or migration."""
        messages = self._store.list_thread_messages(thread.id)
        last_message_at = str(messages[-1]["ts"]) if messages else ""
        message_count = len(messages)
        self._store.upsert_thread_state(
            thread.id,
            summary="",
            metadata={
                "message_count": message_count,
                "last_message_at": last_message_at,
            },
        )
        self._store.upsert_contact_state(
            thread.contact_id,
            summary="",
            metadata={"last_thread_id": thread.id, "last_message_at": last_message_at},
        )
        self._store.upsert_role_state(
            thread.role_id,
            summary="",
            metadata={"last_thread_id": thread.id, "last_message_at": last_message_at},
        )
