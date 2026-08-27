"""角色会话打开、迁移与显示状态。"""

from __future__ import annotations

from typing import Any

from .models import Session

from .helpers import _ROLE_SESSION_PREFIX

class _RoleSessionsMixin:
    def role_session_key(self, role_id: str) -> str:
        clean_role_id = str(role_id).strip()
        if not clean_role_id:
            raise ValueError("role_id 不能为空")
        return f"{_ROLE_SESSION_PREFIX}{clean_role_id}"

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
