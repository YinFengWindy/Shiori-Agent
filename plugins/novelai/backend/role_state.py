"""NovelAI role preferences participating in the host's single role commit."""

from typing import Any

from core.roles.store import RoleStore
from bus.events_lifecycle import RoleDeleted

PLUGIN_ID = "novelai"


class NovelAIRoleState:
    """Own the CG preference schema without storing plugin fields in roles."""

    def __init__(self, roles: RoleStore) -> None:
        self._roles = roles

    def enabled(self, role_id: str) -> bool:
        """Read the persisted plugin namespace for a still-existing role."""
        with self._roles.lock:
            if self._roles.get_role(role_id) is None:
                return False
            return self.project(role_id, self._roles.extensions.read(PLUGIN_ID))[
                "autoSceneCgEnabled"
            ]

    def reconcile(self) -> None:
        """Prune deleted-role preferences, including deletions while disabled."""
        with self._roles.lock:
            role_ids = {role.id for role in self._roles.list_roles()}
            data = self._roles.extensions.read(PLUGIN_ID)
            deleted_ids = set(data) - role_ids
            if deleted_ids:

                def prune(namespace):
                    for role_id in deleted_ids:
                        namespace.pop(role_id, None)

                self._roles.extensions.update(PLUGIN_ID, prune)

    async def on_role_deleted(self, _event: RoleDeleted) -> None:
        """Apply the same reconciliation after a live role deletion."""
        self.reconcile()

    @staticmethod
    def write_draft(role_id: str, values: dict[str, Any], data: dict[str, Any]) -> None:
        """Validate a detached draft before the shared atomic manifest save."""
        enabled = values.get("autoSceneCgEnabled")
        if not isinstance(enabled, bool):
            raise ValueError("NovelAI autoSceneCgEnabled 必须是布尔值")
        data[role_id] = {**data.get(role_id, {}), "auto_scene_cg_enabled": enabled}

    @staticmethod
    def project(role_id: str, data: dict[str, Any]) -> dict[str, bool]:
        """Expose the plugin's editable projection separately from RoleRecord."""
        return {
            "autoSceneCgEnabled": bool(
                data.get(role_id, {}).get("auto_scene_cg_enabled", False)
            )
        }
