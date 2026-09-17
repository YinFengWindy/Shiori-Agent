"""Session conversation thread 投影。"""

from __future__ import annotations

from typing import Any

from .models import Session


class _ProjectionMixin:
    def _project_session_threads(self, session: Session) -> None:
        """Refreshes formal thread projections from immutable message source fields."""

        thread_ids = {
            str(message.get("thread_id") or "").strip()
            for message in session.messages
            if str(message.get("thread_id") or "").strip()
        }
        for thread_id in thread_ids:
            thread = self.conversation_store.get_thread(thread_id)
            if thread is not None:
                self._conversation_projector.project_thread(thread)

    def mark_message_delivery(
        self,
        session_key: str,
        *,
        message_id: str,
        thread_id: str,
        delivery_status: str,
        external_message_id: str = "",
    ) -> dict[str, Any] | None:
        """Writes delivery bookkeeping to exactly the committed message it belongs to.

        This never falls back to "the thread's newest assistant message": if
        ``message_id`` is missing or does not belong to this session/thread,
        nothing is written.
        """
        updated = self._store.update_message_delivery(
            message_id,
            session_key=session_key,
            thread_id=thread_id,
            delivery_status=delivery_status,
            external_message_id=external_message_id,
        )
        return self._sync_cached_message_delivery(session_key, updated)

    def _sync_cached_message_delivery(
        self, session_key: str, updated: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        if updated is None:
            return None
        session = self._cache.get(session_key)
        if session is None:
            return updated
        updated_id = str(updated.get("id") or "").strip()
        for message in reversed(session.messages):
            if str(message.get("id") or "").strip() != updated_id:
                continue
            if "delivery_status" in updated:
                message["delivery_status"] = updated["delivery_status"]
            if updated.get("external_message_id"):
                message["external_message_id"] = updated["external_message_id"]
            break
        return updated
