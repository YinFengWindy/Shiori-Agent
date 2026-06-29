from __future__ import annotations

import logging
from datetime import datetime

from core.common.timekit import parse_iso as _parse_iso, utcnow as _utcnow
from session.store import SessionStore

logger = logging.getLogger(__name__)


class PresenceStore:
    """跨 session 的用户心跳持久化，底层直接复用 sessions.db。"""

    def __init__(self, store: SessionStore) -> None:
        self._store = store
        logger.info("[presence] 初始化完成 db=%s", self._store.db_path)

    def record_user_message(
        self, session_key: str, now: datetime | None = None
    ) -> None:
        ts = (now or _utcnow()).isoformat()
        target_key = self._role_key_for_presence(session_key)
        self._store.update_presence(target_key, last_user_at=ts)
        logger.debug("[presence] 心跳更新 session=%s presence=%s ts=%s", session_key, target_key, ts)

    def record_proactive_sent(
        self, session_key: str, now: datetime | None = None
    ) -> None:
        ts = (now or _utcnow()).isoformat()
        target_key = self._role_key_for_presence(session_key)
        self._store.update_presence(target_key, last_proactive_at=ts)
        logger.debug("[presence] 主动消息记录 session=%s presence=%s ts=%s", session_key, target_key, ts)

    def record_user_message_by_role(
        self,
        role_id: str,
        now: datetime | None = None,
    ) -> None:
        ts = (now or _utcnow()).isoformat()
        target_key = self._presence_key_from_role_id(role_id)
        self._store.update_presence(target_key, last_user_at=ts)
        logger.debug("[presence] 心跳更新 role=%s ts=%s", role_id, ts)

    def record_proactive_sent_by_role(
        self,
        role_id: str,
        now: datetime | None = None,
    ) -> None:
        ts = (now or _utcnow()).isoformat()
        target_key = self._presence_key_from_role_id(role_id)
        self._store.update_presence(target_key, last_proactive_at=ts)
        logger.debug("[presence] 主动消息记录 role=%s ts=%s", role_id, ts)

    def get_last_user_at(self, session_key: str) -> datetime | None:
        row = self._store.get_presence(self._role_key_for_presence(session_key)) or {}
        return _parse_iso(row.get("last_user_at"))

    def get_last_proactive_at(self, session_key: str) -> datetime | None:
        row = self._store.get_presence(self._role_key_for_presence(session_key)) or {}
        return _parse_iso(row.get("last_proactive_at"))

    def most_recent_user_at(self) -> datetime | None:
        return _parse_iso(self._store.most_recent_user_at())

    def get_all_sessions(self) -> dict[str, dict[str, datetime | None]]:
        rows = self._store.list_presence()
        return {
            key: {
                "last_user_at": _parse_iso(item.get("last_user_at")),
                "last_proactive_at": _parse_iso(item.get("last_proactive_at")),
            }
            for key, item in rows.items()
        }

    def _role_key_for_presence(self, session_key: str) -> str:
        clean_key = str(session_key or "").strip()
        if not clean_key:
            return clean_key
        if clean_key.startswith("role:"):
            return clean_key
        meta = self._store.get_session_meta(clean_key) or {}
        metadata = meta.get("metadata") if isinstance(meta, dict) else {}
        if isinstance(metadata, dict):
            role_id = str(metadata.get("role_id") or "").strip()
            if role_id:
                return self._presence_key_from_role_id(role_id)
        return clean_key

    @staticmethod
    def _presence_key_from_role_id(role_id: str) -> str:
        clean_role_id = str(role_id or "").strip()
        if not clean_role_id:
            raise ValueError("role_id 不能为空")
        return f"role:{clean_role_id}"
