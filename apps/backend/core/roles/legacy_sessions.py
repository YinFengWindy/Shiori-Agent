"""Historical channel session ownership retained after binding retirement."""

from __future__ import annotations

from pathlib import Path

from core.common.channel_identifiers import chat_ids_equal
from infra.persistence.json_store import atomic_save_json, load_json

from .models import RoleRecord


class LegacySessionOwners:
    """Resolve old session keys for lazy history projection, never live routing."""

    def __init__(self, workspace: Path) -> None:
        self._path = workspace / "roles" / "legacy-session-owners.json"

    def retain(self, roles: list[RoleRecord], platforms: set[str]) -> None:
        """Persist historical owners before old bindings are removed."""
        rows = self._load()
        known = {(row["channel"], row["chat_id"]) for row in rows}
        for role in roles:
            for binding in role.channel_bindings:
                key = (binding.channel, binding.chat_id)
                if binding.channel in platforms and key not in known:
                    rows.append(
                        {
                            "channel": binding.channel,
                            "chat_id": binding.chat_id,
                            "role_id": role.id,
                        }
                    )
                    known.add(key)
        if rows != self._load():
            atomic_save_json(self._path, rows, domain="legacy session owners")

    def resolve(self, channel: str, chat_id: str) -> str:
        """Find the role originally assigned to an old external session."""
        for row in self._load():
            if row["channel"] == channel and chat_ids_equal(
                channel, row["chat_id"], chat_id
            ):
                return row["role_id"]
        raise KeyError(f"旧会话没有角色: {channel}:{chat_id}")

    def _load(self) -> list[dict[str, str]]:
        rows = load_json(self._path, default=[], domain="legacy session owners")
        if not isinstance(rows, list) or any(
            not isinstance(row, dict)
            or not all(
                isinstance(row.get(key), str) and row[key]
                for key in ("channel", "chat_id", "role_id")
            )
            for row in rows
        ):
            raise ValueError("旧会话归属格式无效")
        return rows
