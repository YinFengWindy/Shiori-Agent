"""角色会话打开、迁移与显示状态。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .models import Session

from .helpers import (
    _ROLE_SESSION_PREFIX,
    _timestamp_at_or_before,
)

class _RoleSessionsMixin:
    def role_session_key(self, role_id: str) -> str:
        clean_role_id = str(role_id).strip()
        if not clean_role_id:
            raise ValueError("role_id 不能为空")
        return f"{_ROLE_SESSION_PREFIX}{clean_role_id}"

    def record_role_deleted(self, role_id: str) -> None:
        """Records a role tombstone so legacy transport history cannot resurrect it."""

        clean_role_id = str(role_id or "").strip()
        if not clean_role_id:
            raise ValueError("role_id 不能为空")
        state = self.conversation_store.get_role_state(clean_role_id)
        metadata = dict(state.metadata) if state is not None else {}
        metadata["deleted_at"] = datetime.now().astimezone().isoformat()
        self.conversation_store.upsert_role_state(
            clean_role_id,
            summary=state.summary if state is not None else "",
            metadata=metadata,
        )

    def open_role_session(
        self,
        role_id: str,
        *,
        role_name: str | None = None,
        role_runtime_config: dict[str, Any] | None = None,
    ) -> Session:
        session_key = self.role_session_key(role_id)
        session = self.get_or_create(session_key)
        self._clear_shared_session_transport_metadata(session)
        if session.metadata.get("role_id") != role_id:
            session.metadata["role_id"] = role_id
        if role_name:
            session.metadata["role_name"] = str(role_name)
        if role_runtime_config is not None:
            session.metadata["role_runtime_config"] = dict(role_runtime_config)
        self.save(session)
        return session
    def update_role_session_display_state(
        self,
        role_id: str,
        *,
        active_illustration: str | None = None,
    ) -> Session:
        session = self.get_or_create(self.role_session_key(role_id))
        if active_illustration is None:
            session.metadata.pop("active_illustration", None)
        else:
            session.metadata["active_illustration"] = str(active_illustration)
        self.save(session)
        return session

    def delete_role_session(self, role_id: str) -> bool:
        session_key = self.role_session_key(role_id)
        self.invalidate(session_key)
        return self._store.delete_session(session_key, cascade=True)

    def sync_role_session_metadata(
        self,
        role_id: str,
        *,
        role_name: str,
        role_prompt: str,
        role_runtime_config: dict[str, Any] | None = None,
        valid_illustrations: list[str] | None = None,
    ) -> Session:
        session = self.get_or_create(self.role_session_key(role_id))
        self._clear_shared_session_transport_metadata(session)
        session.metadata["role_id"] = role_id
        session.metadata["role_name"] = role_name
        session.metadata["role_prompt"] = role_prompt
        if role_runtime_config is not None:
            session.metadata["role_runtime_config"] = dict(role_runtime_config)
        if valid_illustrations is not None:
            active = str(session.metadata.get("active_illustration") or "").strip()
            if active and active not in valid_illustrations:
                session.metadata.pop("active_illustration", None)
        self.save(session)
        return session

    @staticmethod
    def _clear_shared_session_transport_metadata(session: Session) -> None:
        """Keeps mutable channel targets out of the shared role Session metadata."""

        for key in (
            "thread_id",
            "context_channel",
            "context_chat_id",
            "transport_channel",
            "transport_chat_id",
            "session_key_override",
        ):
            session.metadata.pop(key, None)

    def merge_legacy_messages_into_role_session(
        self,
        source_session_key: str,
        target_session: Session,
        *,
        thread_id: str,
        cleared_at: str = "",
    ) -> int:
        """Merges one legacy transport history into the authoritative role session."""

        clean_source_key = str(source_session_key or "").strip()
        clean_thread_id = str(thread_id or "").strip()
        if not clean_source_key or not clean_thread_id:
            raise ValueError("legacy session key 和 thread_id 不能为空")
        if not target_session.key.startswith(_ROLE_SESSION_PREFIX):
            raise ValueError("legacy transport history 只能合并到 role session")

        copied_source_ids = {
            str(message.get("migration_source_message_id") or "").strip()
            for message in target_session.messages
        }
        copies: list[dict[str, Any]] = []
        for source in self._store.fetch_session_messages(clean_source_key):
            source_id = str(source.get("id") or "").strip()
            if not source_id or source_id in copied_source_ids:
                continue
            timestamp = str(source.get("timestamp") or "").strip()
            if cleared_at and _timestamp_at_or_before(timestamp, cleared_at):
                continue
            copied = {
                key: value
                for key, value in source.items()
                if key not in {"id", "session_key", "seq"}
            }
            copied["thread_id"] = clean_thread_id
            copied.setdefault("sender_role", str(copied.get("role") or ""))
            copied["migration_source_session_key"] = clean_source_key
            copied["migration_source_message_id"] = source_id
            copies.append(copied)
            copied_source_ids.add(source_id)

        if not copies:
            return 0

        messages = list(target_session.messages) + copies
        messages.sort(key=lambda message: str(message.get("timestamp") or ""))
        rows: list[dict[str, Any]] = []
        for seq, message in enumerate(messages):
            timestamp = str(
                message.get("timestamp") or datetime.now().astimezone().isoformat()
            )
            message_id = f"{target_session.key}:{seq}"
            message.update(
                {
                    "id": message_id,
                    "session_key": target_session.key,
                    "seq": seq,
                    "timestamp": timestamp,
                }
            )
            rows.append(
                {
                    "id": message_id,
                    "seq": seq,
                    "role": str(message.get("role") or "assistant"),
                    "content": message.get("content", ""),
                    "timestamp": timestamp,
                    "tool_chain": message.get("tool_chain"),
                    "extra": self._extract_extra(message),
                    "thread_id": str(message.get("thread_id") or ""),
                    "sender_role": str(message.get("sender_role") or ""),
                    "media": list(message.get("media") or []),
                    "external_message_id": str(
                        message.get("external_message_id") or ""
                    ),
                    "delivery_status": str(message.get("delivery_status") or ""),
                }
            )

        target_session.messages = messages
        target_session.last_consolidated = 0
        target_session.updated_at = datetime.now()
        self._store.replace_session_messages(
            target_session.key,
            rows=rows,
            updated_at=target_session.updated_at.isoformat(),
            last_consolidated=target_session.last_consolidated,
            next_seq=len(rows),
        )
        self._cache[target_session.key] = target_session
        return len(copies)

    def normalize_role_session_display_state(
        self,
        role_id: str,
        *,
        valid_illustrations: list[str],
    ) -> Session:
        session = self.get_or_create(self.role_session_key(role_id))
        active = str(session.metadata.get("active_illustration") or "").strip()
        if active and active not in valid_illustrations:
            session.metadata.pop("active_illustration", None)
        self.save(session)
        return session
