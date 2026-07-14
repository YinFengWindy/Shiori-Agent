"""One-way migration from retired global role routing configuration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from infra.persistence.json_store import atomic_save_json, load_json

from .services import RoleRepository
from .store import RoleProactiveConfig

_CONFIG_MIGRATION_STATE_VERSION = 1


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
        self._state_path = self._workspace / "roles" / "config_migration_state.json"

    def migrate(self, proactive: Any | None = None) -> RoleConfigMigrationSummary:
        bindings_migrated, unresolved = self._migrate_bindings()
        proactive_migrated = self._migrate_proactive(proactive)
        return RoleConfigMigrationSummary(bindings_migrated, proactive_migrated, unresolved)

    def _migrate_bindings(self) -> tuple[int, int]:
        if self._bindings_imported():
            return 0, 0
        legacy_path = self._workspace / "roles" / "channel_bindings.json"
        if not legacy_path.exists():
            return 0, 0
        payload = load_json(
            legacy_path,
            default={"bindings": {}},
            domain="legacy_role_bindings",
        )
        raw_bindings = payload.get("bindings", {}) if isinstance(payload, dict) else {}
        if not isinstance(raw_bindings, dict):
            self._mark_bindings_imported()
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
        self._mark_bindings_imported()
        return migrated, unresolved

    def _bindings_imported(self) -> bool:
        state = load_json(
            self._state_path,
            default={"version": _CONFIG_MIGRATION_STATE_VERSION},
            domain="role_config_migration",
        )
        return bool(
            isinstance(state, dict) and state.get("legacy_bindings_imported")
        )

    def _mark_bindings_imported(self) -> None:
        atomic_save_json(
            self._state_path,
            {
                "version": _CONFIG_MIGRATION_STATE_VERSION,
                "legacy_bindings_imported": True,
            },
            domain="role_config_migration",
        )

    def _migrate_proactive(self, proactive: Any | None) -> int:
        if proactive is None:
            return 0
        migrated_role_ids = self._migrate_proactive_policies(proactive)
        role_id = str(getattr(proactive, "default_role_id", "") or "").strip()
        channel = str(getattr(proactive, "default_channel", "") or "").strip()
        chat_id = str(getattr(proactive, "default_chat_id", "") or "").strip()
        if not role_id or not channel or not chat_id:
            return len(migrated_role_ids)
        role = self._repository.store.get_role(role_id)
        if role is None or role.proactive.enabled or role.proactive.target_channel or role.proactive.target_chat_id:
            return len(migrated_role_ids)
        if not any(item.channel == channel and item.chat_id == chat_id for item in role.channel_bindings):
            return len(migrated_role_ids)
        self._repository.update_role(
            role.id,
            proactive=RoleProactiveConfig(
                enabled=bool(getattr(proactive, "enabled", False)),
                target_channel=channel,
                target_chat_id=chat_id,
                profile=role.proactive.profile,
                overrides=role.proactive.overrides,
                agent=role.proactive.agent,
                drift=role.proactive.drift,
                policy_configured=role.proactive.policy_configured,
            ),
        )
        migrated_role_ids.add(role.id)
        return len(migrated_role_ids)

    def _migrate_proactive_policies(self, proactive: Any) -> set[str]:
        migrated: set[str] = set()
        for role in self._repository.store.list_roles():
            current = role.proactive
            if current.policy_configured:
                continue
            self._repository.update_role(
                role.id,
                proactive=RoleProactiveConfig(
                    enabled=current.enabled,
                    target_channel=current.target_channel,
                    target_chat_id=current.target_chat_id,
                    profile=str(getattr(proactive, "profile", "daily") or "daily"),
                    overrides=dict(getattr(proactive, "overrides", {}) or {}),
                    agent={
                        "model": str(getattr(proactive, "agent_tick_model", "") or ""),
                        "max_steps": int(getattr(proactive, "agent_tick_max_steps", 35)),
                        "content_limit": int(getattr(proactive, "agent_tick_content_limit", 5)),
                        "web_fetch_max_chars": int(
                            getattr(proactive, "agent_tick_web_fetch_max_chars", 8_000)
                        ),
                    },
                    drift={
                        "enabled": bool(getattr(proactive, "drift_enabled", False)),
                        "max_steps": int(getattr(proactive, "drift_max_steps", 20)),
                        "min_interval_hours": int(
                            getattr(proactive, "drift_min_interval_hours", 3)
                        ),
                    },
                    policy_configured=True,
                ),
            )
            migrated.add(role.id)
        return migrated
