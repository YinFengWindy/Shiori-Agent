from __future__ import annotations

from collections.abc import Callable
from typing import Any

from core.roles.affection_access import current_affection


class DesktopRolePresenter:
    """Builds desktop-safe role payloads without owning role operations."""

    def __init__(
        self,
        role_store: Any,
        relationship_runtime: Any | None = None,
        *,
        last_message_for_role: Callable[[str], dict[str, Any] | None] | None = None,
    ) -> None:
        self._role_store = role_store
        self._relationship_runtime = relationship_runtime
        self._last_message_for_role = last_message_for_role

    def serialize(self, role: Any) -> dict[str, Any]:
        """Returns role fields plus desktop asset and runtime state views."""
        payload = role.to_dict()
        # Stage guidance has its own bridge method (roles.affection.stagePrompts.*).
        payload.pop("affection_stage_prompts", None)
        avatar = payload.get("avatar")
        illustrations = payload.get("illustrations") or []
        payload["avatar_abs"] = (
            str((self._role_store.roles_dir / avatar).resolve())
            if isinstance(avatar, str) and avatar
            else None
        )
        chat_background = payload.get("chat_background")
        payload["chat_background_abs"] = (
            str((self._role_store.roles_dir / chat_background).resolve())
            if isinstance(chat_background, str) and chat_background
            else None
        )
        payload["illustrations_abs"] = [
            str((self._role_store.roles_dir / relative_path).resolve())
            for relative_path in illustrations
            if isinstance(relative_path, str) and relative_path
        ]
        payload["plugin_state"] = self._role_store.extensions.project(role.id)
        affection = current_affection(self._relationship_runtime)
        if affection is not None:
            snapshot = affection.read_snapshot(role.id)
            runtime = affection.current_loneliness_runtime(role.id)
            if snapshot is not None:
                payload["relationship_snapshot"] = snapshot
            if runtime is not None:
                payload["loneliness_runtime"] = runtime
            summary = affection.affection.current_summary(role.id)
            if summary is not None:
                payload["affection"] = summary
        if self._last_message_for_role is not None:
            # Chat list preview: the newest message of the role's single session.
            payload["last_message"] = self._last_message_for_role(role.id)
        return payload
