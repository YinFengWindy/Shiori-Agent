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

    def mark_latest_assistant_delivery(
        self,
        session_key: str,
        *,
        thread_id: str = "",
        delivery_status: str,
        external_message_id: str = "",
    ) -> dict[str, Any] | None:
        updated = self._store.update_latest_assistant_delivery(
            session_key,
            thread_id=thread_id,
            delivery_status=delivery_status,
            external_message_id=external_message_id,
        )
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
