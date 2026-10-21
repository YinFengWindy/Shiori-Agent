"""Natural chat's per-role preference participates in the shared role save."""

from shiori_sdk.roles import Roles
from shiori_sdk.role_events import RoleDeleted

PLUGIN_ID = "natural_chat"


class NaturalChatRoleState:
    """Read and validate this plugin's opaque role namespace."""

    def __init__(self, roles: Roles) -> None:
        self._roles = roles

    def enabled(self, role_id: str) -> bool:
        """Missing roles and unsaved preferences are disabled."""
        with self._roles.read_scope():
            return (
                self._roles.get_role(role_id) is not None
                and self.project(role_id, self._roles.extensions.read(PLUGIN_ID))[
                    "enabled"
                ]
            )

    def reconcile(self) -> None:
        """Remove preferences for roles deleted while the plugin was disabled."""
        with self._roles.read_scope():
            existing = {role.id for role in self._roles.list_roles()}
            removed = set(self._roles.extensions.read(PLUGIN_ID)) - existing
            if removed:

                def prune(namespace: dict[str, object]) -> None:
                    for role_id in removed:
                        namespace.pop(role_id, None)

                self._roles.extensions.update(PLUGIN_ID, prune)

    async def on_role_deleted(self, _event: RoleDeleted) -> None:
        """Prune the namespace after a live role deletion."""
        self.reconcile()

    @staticmethod
    def write_draft(
        role_id: str, values: dict[str, object], data: dict[str, object]
    ) -> None:
        """Validate the draft before the host's atomic role commit."""
        enabled = values.get("enabled")
        if not isinstance(enabled, bool):
            raise ValueError("自然聊天 enabled 必须是布尔值")
        data[role_id] = {"enabled": enabled}

    @staticmethod
    def project(role_id: str, data: dict[str, object]) -> dict[str, bool]:
        """Expose only the editable role toggle; old roles default to off."""
        value = data.get(role_id, {})
        if not isinstance(value, dict):
            raise ValueError("自然聊天角色设置必须是对象")
        return {"enabled": value.get("enabled") is True}
