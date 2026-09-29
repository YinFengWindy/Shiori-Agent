from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from conversation.context_scope import desktop_view_thread_ids, in_desktop_view
from desktop_bridge.tool_call_preview import truncate_desktop_tool_result
from session.manager import Session
from session.manager.helpers import ROLE_SESSION_PREFIX, is_role_session_key
from session.manager.models import message_thread_id

# The chat list shows one line; the renderer strips Markdown from this prefix.
_PREVIEW_MAX_CHARS = 200


class DesktopSessionPresenter:
    """Builds desktop session payloads from formal thread and runtime state.

    A role session also stores the role's channel threads; every read here
    shows only the desktop conversation (``in_desktop_view``).
    """

    def __init__(
        self,
        conversation_service,
        relationship_runtime: Any | None = None,
    ) -> None:
        self._conversation_service = conversation_service
        self._relationship_runtime = relationship_runtime

    def serialize(self, session: Session) -> dict[str, Any]:
        """Returns the desktop-compatible role session snapshot."""
        payload = self.serialize_summary(session)
        payload["messages"] = [
            self.serialize_message(message) for message in session.messages
        ]
        return payload

    def serialize_summary(self, session: Session) -> dict[str, Any]:
        """Returns session metadata without the full message history."""
        return {
            "key": session.key,
            "created_at": session.created_at.isoformat(),
            "updated_at": session.updated_at.isoformat(),
            "last_consolidated": session.last_consolidated,
            "metadata": self._enrich_metadata(dict(session.metadata)),
        }

    def serialize_message(self, message: dict[str, Any]) -> dict[str, Any]:
        """Serializes one message using the same desktop sanitization contract."""
        serialized = self._serialize_message(message)
        if message.get("seq") is not None:
            serialized["seq"] = int(message["seq"])
        if message.get("session_key"):
            serialized["session_key"] = str(message["session_key"])
        if message.get("is_target") is not None:
            serialized["is_target"] = bool(message["is_target"])
        return serialized

    def serialize_page(
        self,
        session: Session,
        *,
        before_seq: int | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """Reads a bounded message page directly from the session store."""
        store = self._session_store()
        page = store.fetch_messages_page(
            session.key,
            before_seq=before_seq,
            limit=limit,
            thread_ids=self._desktop_thread_ids(session.key),
        )
        page["messages"] = [
            self.serialize_message(message) for message in page["messages"]
        ]
        return page

    def serialize_around(
        self,
        message_id: str,
        *,
        context: int = 5,
    ) -> dict[str, Any]:
        """Serializes a message and nearby messages for search navigation.

        A message outside the desktop conversation is not found.
        """
        store = self._session_store()
        target = store.get_message(message_id)
        result = store.fetch_message_around(
            message_id,
            context=context,
            thread_ids=(
                self._desktop_thread_ids(str(target["session_key"]))
                if target is not None
                else None
            ),
        )
        result["messages"] = [
            self.serialize_message(message) for message in result["messages"]
        ]
        return result

    def serialize_search(
        self,
        query: str,
        *,
        session_key: str | None = None,
        role: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Returns lightweight search results suitable for the renderer.

        Hits are limited to desktop conversations; without ``session_key`` every
        role session is searched.
        """
        store = self._session_store()
        if session_key:
            thread_ids = self._desktop_thread_ids(session_key)
            session_prefix = None
        else:
            thread_ids = frozenset(
                thread_id
                for key, threads in store.thread_ids_by_session(
                    ROLE_SESSION_PREFIX
                ).items()
                for thread_id in desktop_view_thread_ids(_role_id(key), threads)
            )
            session_prefix = ROLE_SESSION_PREFIX
        results, total = store.search_message_previews(
            query,
            session_key=session_key,
            role=role,
            limit=limit,
            offset=offset,
            thread_ids=thread_ids,
            session_prefix=session_prefix,
        )
        safe_limit = max(1, min(int(limit), 100))
        safe_offset = max(0, int(offset))
        return {
            "results": results,
            "total_count": total,
            "query": query,
            "limit": safe_limit,
            "offset": safe_offset,
            "has_more": safe_offset + len(results) < total,
        }

    def serialize_image_history(self, session_key: str) -> dict[str, Any]:
        """Returns media-only history without expanding the chat message window."""
        return {
            "session_key": session_key,
            "messages": self._session_store().fetch_image_history(
                session_key, thread_ids=self._desktop_thread_ids(session_key)
            ),
        }

    def last_message_preview(self, session_key: str) -> dict[str, Any] | None:
        """Returns the newest desktop message as a light chat-list preview."""
        messages = self._session_store().fetch_messages_page(
            session_key,
            limit=1,
            thread_ids=self._desktop_thread_ids(session_key),
        )["messages"]
        if not messages:
            return None
        message = messages[-1]
        return {
            "role": str(message.get("role") or ""),
            "content": str(message.get("content") or "")[:_PREVIEW_MAX_CHARS],
            "timestamp": str(message.get("timestamp") or ""),
            "has_media": bool(message.get("media")),
        }

    def desktop_messages(
        self, session_key: str, messages: Iterable[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Keeps the messages the desktop chat shows; other sessions keep all."""
        if not is_role_session_key(session_key):
            return list(messages)
        role_id = _role_id(session_key)
        return [
            message
            for message in messages
            if in_desktop_view(role_id, message_thread_id(message))
        ]

    def _desktop_thread_ids(self, session_key: str) -> frozenset[str] | None:
        """The threads of a role session the desktop chat shows; None elsewhere."""
        if not is_role_session_key(session_key):
            return None
        return desktop_view_thread_ids(
            _role_id(session_key), self._session_store().session_thread_ids(session_key)
        )

    def _session_store(self):
        manager = getattr(self._conversation_service, "_session_manager", None)
        store = getattr(manager, "_store", None)
        if store is None:
            raise RuntimeError("session store unavailable for desktop pagination")
        return store

    def _enrich_metadata(self, metadata: dict[str, Any]) -> dict[str, Any]:
        if self._relationship_runtime is None:
            return metadata
        return self._relationship_runtime.enrich_session_metadata(metadata)

    @staticmethod
    def _serialize_message(message: dict[str, Any]) -> dict[str, Any]:
        metadata = message.get("metadata")
        merged_metadata = dict(metadata) if isinstance(metadata, dict) else {}
        raw_turn_metrics = merged_metadata.get("turn_metrics")
        if isinstance(raw_turn_metrics, dict):
            turn_metrics = {
                key: value
                for key in ("total_tokens", "thinking_duration_ms")
                if isinstance((value := raw_turn_metrics.get(key)), int) and value >= 0
            }
            if turn_metrics:
                merged_metadata["turn_metrics"] = turn_metrics
            else:
                merged_metadata.pop("turn_metrics", None)
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
            "is_target",
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
            "tool_chain": DesktopSessionPresenter._sanitize_tool_chain(
                message.get("tool_chain")
            ),
            "media": list(message.get("media") or []),
            "metadata": merged_metadata,
        }

    @staticmethod
    def _sanitize_tool_chain(value: object) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        groups: list[dict[str, Any]] = []
        for raw_group in value:
            if not isinstance(raw_group, dict):
                continue
            calls: list[dict[str, Any]] = []
            for raw_call in raw_group.get("calls") or []:
                if not isinstance(raw_call, dict):
                    continue
                call_id = str(raw_call.get("call_id") or "").strip()
                tool_name = str(raw_call.get("name") or "").strip()
                if not call_id or not tool_name:
                    continue
                calls.append(
                    {
                        "call_id": call_id,
                        "name": tool_name,
                        "status": str(raw_call.get("status") or "success"),
                        "arguments": (
                            raw_call.get("arguments")
                            if isinstance(raw_call.get("arguments"), dict)
                            else {}
                        ),
                        "final_arguments": (
                            raw_call.get("final_arguments")
                            if isinstance(raw_call.get("final_arguments"), dict)
                            else {}
                        ),
                        "result": truncate_desktop_tool_result(raw_call.get("result")),
                    }
                )
            if calls:
                groups.append(
                    {
                        "text": str(raw_group.get("text") or ""),
                        "reasoning_content": str(
                            raw_group.get("reasoning_content") or ""
                        ),
                        "calls": calls,
                    }
                )
        return groups


def _role_id(session_key: str) -> str:
    return session_key.removeprefix(ROLE_SESSION_PREFIX)
