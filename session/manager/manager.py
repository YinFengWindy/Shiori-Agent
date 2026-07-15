"""SessionManager 缓存、锁与基础入口。"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from conversation.projector import ConversationStateProjector
from conversation.store import ConversationStore
from ..store import SessionStore

from .models import Session

class _ManagerCoreMixin:
    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.session_dir = workspace / "sessions"
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = workspace / "sessions.db"
        self._store = SessionStore(self.db_path)
        self.conversation_store = ConversationStore(
            self.db_path,
            connection=self._store._conn,
            lock=self._store._lock,
        )
        self._conversation_projector = ConversationStateProjector(self.conversation_store)
        self._cache: dict[str, Session] = {}
        self._write_locks: dict[str, asyncio.Lock] = {}

    def _lock(self, key: str) -> asyncio.Lock:
        if key not in self._write_locks:
            self._write_locks[key] = asyncio.Lock()
        return self._write_locks[key]

    def get_or_create(self, key: str) -> Session:
        if key in self._cache:
            return self._cache[key]

        session = self._load(key)
        if session is None:
            session = Session(key)
            self._ensure_session_meta(session)
        self._cache[key] = session
        return session

    def peek_next_message_id(self, session_key: str) -> str:
        next_seq = self._store.next_seq(session_key)
        return f"{session_key}:{next_seq}"

    def invalidate(self, key: str) -> None:
        self._cache.pop(key, None)

    def list_sessions(self) -> list[dict[str, Any]]:
        sessions = self._store.list_sessions()
        for item in sessions:
            item["path"] = str(self.db_path)
        return sessions

    def get_channel_metadata(self, channel: str) -> list[dict[str, Any]]:
        try:
            return self._store.get_channel_metadata(channel)
        except Exception as e:
            logging.warning("Failed to read channel metadata for %s: %s", channel, e)
            return []
