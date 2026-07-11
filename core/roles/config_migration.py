"""One-way migration from retired global role routing configuration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from infra.persistence.json_store import load_json

from .services import RoleRepository
from .store import RoleProactiveConfig


@dataclass(frozen=True)
class RoleConfigMigrationSummary:
    """Counts configuration records copied into role-owned fields."""

    bindings_migrated: int = 0
    proactive_migrated: int = 0
    unresolved_bindings: int = 0


class RoleConfigMigrator:
    """Migrates legacy bindings once without retaining them as a runtime fallback."""

    def __init__(self, workspace: Path, repository: RoleRepository) -> None:
        self._workspace = Path(workspace)
        self._repository = repository

    def migrate(self, proactive: Any | None = None) -> RoleConfigMigrationSummary:
        bindings_migrated, unresolved = self._migrate_bindings()
        proactive_migrated = self._migrate_proactive(proactive)
        return RoleConfigMigrationSummary(bindings_migrated, proactive_migrated, unresolved)

    def _migrate_bindings(self) -> tuple[int, int]:
        payload = load_json(
            self._workspace / "roles" / "channel_bindings.json",
            default={"bindings": {}},
            domain="legacy_role_bindings",
        )
        raw_bindings = payload.get("bindings", {}) if isinstance(payload, dict) else {}
        if not isinstance(raw_bindings, dict):
            return 0, 0
        migrated = 0
        unresolved = 0
        for raw in raw_bindings.values():
            if not isinstance(raw, dict):
                unresolved += 1
                continue
            role_id = str(raw.get("role_id") or "").strip()
            channel = str(raw.get("channel") or "").strip()
            chat_id = str(raw.get("chat_id") or "").strip()
            role = self._repository.store.get_role(role_id)
            if role is None or not channel or not chat_id:
                unresolved += 1
                continue
            if any(item.channel == channel and item.chat_id == chat_id for item in role.channel_bindings):
                continue
            self._repository.update_role(
                role.id,
                channel_bindings=[
                    *(item.to_dict() for item in role.channel_bindings),
                    {"channel": channel, "chat_id": chat_id, "allow_from": []},
                ],
            )
            migrated += 1
        return migrated, unresolved

    def _migrate_proactive(self, proactive: Any | None) -> int:
        role_id = str(getattr(proactive, "default_role_id", "") or "").strip()
        channel = str(getattr(proactive, "default_channel", "") or "").strip()
        chat_id = str(getattr(proactive, "default_chat_id", "") or "").strip()
        if not role_id or not channel or not chat_id:
            return 0
        role = self._repository.store.get_role(role_id)
        if role is None or role.proactive.enabled or role.proactive.target_channel or role.proactive.target_chat_id:
            return 0
        if not any(item.channel == channel and item.chat_id == chat_id for item in role.channel_bindings):
            return 0
        self._repository.update_role(
            role.id,
            proactive=RoleProactiveConfig(
                enabled=bool(getattr(proactive, "enabled", False)),
                target_channel=channel,
                target_chat_id=chat_id,
            ),
        )
        return 1
