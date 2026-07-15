"""Session 消息持久化与同步。"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from .models import Session

class _PersistenceMixin:
    def _load(self, key: str) -> Session | None:
        meta = self._store.get_session_meta(key)
        messages = self._store.fetch_session_messages(key)
        if meta is None and not messages:
            return None

        created_at = (
            datetime.fromisoformat(meta["created_at"])
            if meta and meta.get("created_at")
            else datetime.now()
        )
        updated_at = (
            datetime.fromisoformat(meta["updated_at"])
            if meta and meta.get("updated_at")
            else datetime.now()
        )
        metadata = meta.get("metadata", {}) if meta else {}
        last_consolidated = int(meta.get("last_consolidated", 0)) if meta else 0
        return Session(
            key=key,
            messages=messages,
            created_at=created_at,
            updated_at=updated_at,
            metadata=metadata,
            last_consolidated=last_consolidated,
        )

    def _ensure_session_meta(self, session: Session) -> None:
        self._store.upsert_session(
            session.key,
            created_at=session.created_at.isoformat(),
            updated_at=session.updated_at.isoformat(),
            last_consolidated=session.last_consolidated,
            metadata=session.metadata,
        )

    def _extract_extra(self, msg: dict[str, Any]) -> dict[str, Any]:
        skip = {
            "id",
            "session_key",
            "seq",
            "role",
            "content",
            "timestamp",
            "tool_chain",
            "thread_id",
            "sender_role",
            "media",
            "external_message_id",
            "delivery_status",
        }
        return {k: v for k, v in msg.items() if k not in skip}

    def _conversation_fields(self, msg: dict[str, Any]) -> dict[str, Any]:
        metadata = msg.get("metadata")
        typed_metadata = metadata if isinstance(metadata, dict) else {}
        fields: dict[str, Any] = {}
        thread_id = str(
            msg.get("thread_id") or typed_metadata.get("thread_id") or ""
        ).strip()
        if thread_id:
            fields["thread_id"] = thread_id
        sender_role = str(msg.get("sender_role") or "").strip()
        if sender_role:
            fields["sender_role"] = sender_role
        media = msg.get("media")
        if isinstance(media, list) and media:
            fields["media"] = list(media)
        external_message_id = str(
            msg.get("external_message_id")
            or typed_metadata.get("external_message_id")
            or ""
        ).strip()
        if external_message_id:
            fields["external_message_id"] = external_message_id
        delivery_status = str(
            msg.get("delivery_status") or typed_metadata.get("delivery_status") or ""
        ).strip()
        if delivery_status:
            fields["delivery_status"] = delivery_status
        return fields

    def _message_seq(self, session_key: str, msg: dict[str, Any]) -> int | None:
        raw_seq = msg.get("seq")
        if raw_seq is not None:
            try:
                return int(raw_seq)
            except (TypeError, ValueError):
                return None
        raw_id = str(msg.get("id") or "").strip()
        prefix = f"{session_key}:"
        if not raw_id.startswith(prefix):
            return None
        try:
            return int(raw_id[len(prefix) :])
        except ValueError:
            return None

    def _message_snapshot(
        self,
        session_key: str,
        msg: dict[str, Any],
    ) -> dict[str, Any]:
        content = msg.get("content", "")
        if not isinstance(content, str):
            content = json.dumps(content, ensure_ascii=False)
        timestamp = str(msg.get("timestamp") or "")
        return {
            "id": str(msg.get("id") or ""),
            "session_key": session_key,
            "seq": self._message_seq(session_key, msg),
            "role": str(msg.get("role") or "assistant"),
            "content": content,
            "timestamp": timestamp,
            "tool_chain": msg.get("tool_chain"),
            "extra": self._extract_extra(msg),
            **self._conversation_fields(msg),
        }

    def _requires_full_message_sync(self, session: Session) -> bool:
        persisted = self._store.fetch_session_messages(session.key)
        persisted_ids = [str(msg.get("id") or "") for msg in persisted]
        current_persisted = [
            msg for msg in session.messages if str(msg.get("id") or "").strip()
        ]
        current_persisted_ids = [str(msg.get("id") or "") for msg in current_persisted]
        if len(current_persisted_ids) != len(persisted_ids):
            return True
        if current_persisted_ids != persisted_ids:
            return True
        seen_unpersisted = False
        for msg in session.messages:
            if str(msg.get("id") or "").strip():
                if seen_unpersisted:
                    return True
                continue
            seen_unpersisted = True
        persisted_by_id = {
            str(msg.get("id") or ""): self._message_snapshot(session.key, msg)
            for msg in persisted
        }
        for msg in current_persisted:
            message_id = str(msg.get("id") or "")
            if self._message_snapshot(session.key, msg) != persisted_by_id.get(
                message_id
            ):
                return True
        return False

    def _replace_persisted_messages(self, session: Session) -> None:
        next_seq = self._store.next_seq(session.key)
        rows: list[dict[str, Any]] = []
        for msg in session.messages:
            timestamp = str(
                msg.get("timestamp") or datetime.now().astimezone().isoformat()
            )
            msg["timestamp"] = timestamp
            seq = self._message_seq(session.key, msg)
            if seq is None:
                seq = next_seq
            message_id = str(msg.get("id") or "").strip() or f"{session.key}:{seq}"
            next_seq = max(next_seq, seq + 1)
            row = {
                "id": message_id,
                "session_key": session.key,
                "seq": seq,
                "role": str(msg.get("role") or "assistant"),
                "content": msg.get("content", ""),
                "timestamp": timestamp,
                "tool_chain": msg.get("tool_chain"),
                "extra": self._extract_extra(msg),
                **self._conversation_fields(msg),
            }
            if not isinstance(row["content"], str):
                row["content"] = json.dumps(row["content"], ensure_ascii=False)
            msg.update(
                {
                    "id": message_id,
                    "session_key": session.key,
                    "seq": seq,
                    "timestamp": timestamp,
                }
            )
            rows.append(row)
        self._store.replace_session_messages(
            session.key,
            rows=rows,
            updated_at=session.updated_at.isoformat(),
            last_consolidated=session.last_consolidated,
            next_seq=next_seq,
        )

    def _persist_messages(
        self, session: Session, messages: list[dict[str, Any]]
    ) -> int:
        next_seq = self._store.next_seq(session.key)
        inserted = 0

        # 1. 只写入尚未持久化（没有 id）的消息。
        for msg in messages:
            if msg.get("id"):
                continue
            ts = str(msg.get("timestamp") or datetime.now().astimezone().isoformat())
            content = msg.get("content", "")
            if not isinstance(content, str):
                content = json.dumps(content, ensure_ascii=False)
            row = self._store.insert_message(
                session.key,
                role=str(msg.get("role") or "assistant"),
                content=content,
                ts=ts,
                seq=next_seq,
                tool_chain=msg.get("tool_chain"),
                extra=self._extract_extra(msg),
                **self._conversation_fields(msg),
            )
            msg.update(row)
            next_seq += 1
            inserted += 1

        # 2. 保持会话消息缓存里的时间字段完整。
        for msg in messages:
            if "timestamp" not in msg:
                msg["timestamp"] = datetime.now().astimezone().isoformat()

        return inserted

    def save(self, session: Session) -> None:
        session.updated_at = datetime.now()
        self._ensure_session_meta(session)
        if self._requires_full_message_sync(session):
            self._replace_persisted_messages(session)
        else:
            self._persist_messages(session, session.messages)
        self._store.upsert_session(
            session.key,
            created_at=session.created_at.isoformat(),
            updated_at=session.updated_at.isoformat(),
            last_consolidated=session.last_consolidated,
            metadata=session.metadata,
        )
        self._project_session_threads(session)
        self._cache[session.key] = session

    async def save_async(self, session: Session) -> None:
        session.updated_at = datetime.now()
        async with self._lock(session.key):
            self.save(session)

    async def append_messages(self, session: Session, messages: list[dict]) -> None:
        session.updated_at = datetime.now()
        msgs_copy = list(messages)
        async with self._lock(session.key):
            # 1. 确保 session 元数据存在并刷新 updated_at。
            self._ensure_session_meta(session)
            # 2. 追加写入本次新增消息，并补齐稳定 id。
            self._persist_messages(session, msgs_copy)
            # 3. 回写 session 元数据（含 last_consolidated / metadata）。
            self._store.upsert_session(
                session.key,
                created_at=session.created_at.isoformat(),
                updated_at=session.updated_at.isoformat(),
                last_consolidated=session.last_consolidated,
                metadata=session.metadata,
            )
            self._project_session_threads(session)
            self._cache[session.key] = session
