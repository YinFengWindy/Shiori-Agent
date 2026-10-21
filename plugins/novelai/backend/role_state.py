"""NovelAI role preferences and independently saved CG prompt instructions."""

from shiori_sdk.roles import Roles
from shiori_sdk.role_events import RoleDeleted

PLUGIN_ID = "novelai"


class NovelAIRoleState:
    """Own the CG preference schema without storing plugin fields in roles."""

    def __init__(self, roles: Roles) -> None:
        self._roles = roles

    def enabled(self, role_id: str) -> bool:
        """Read the persisted plugin namespace for a still-existing role."""
        with self._roles.read_scope():
            if self._roles.get_role(role_id) is None:
                return False
            return self.project(role_id, self._roles.extensions.read(PLUGIN_ID))[
                "autoSceneCgEnabled"
            ]

    def prompt_instructions(self, role_id: str) -> str:
        """Read a role's user-authored instructions for the CG prompt model."""
        with self._roles.read_scope():
            self._require_role(role_id)
            value = _role_preferences(
                role_id, self._roles.extensions.read(PLUGIN_ID)
            ).get("auto_scene_cg_prompt_instructions", "")
            if not isinstance(value, str):
                raise ValueError("自动场景 CG 补充要求必须是文本")
            return value

    def save_prompt_instructions(self, role_id: str, instructions: str) -> None:
        """Save only the private prompt field, preserving the role's switch draft."""
        with self._roles.read_scope():
            self._require_role(role_id)

            def save(data: dict[str, object]) -> None:
                data[role_id] = {
                    **_role_preferences(role_id, data),
                    "auto_scene_cg_prompt_instructions": instructions,
                }

            self._roles.extensions.update(PLUGIN_ID, save)

    def _require_role(self, role_id: str) -> None:
        if self._roles.get_role(role_id) is None:
            raise ValueError("角色不存在")

    def reconcile(self) -> None:
        """Prune deleted-role preferences, including deletions while disabled."""
        with self._roles.read_scope():
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
    def write_draft(
        role_id: str, values: dict[str, object], data: dict[str, object]
    ) -> None:
        """Validate a detached draft before the shared atomic manifest save."""
        enabled = values.get("autoSceneCgEnabled")
        if not isinstance(enabled, bool):
            raise ValueError("NovelAI autoSceneCgEnabled 必须是布尔值")
        data[role_id] = {
            **_role_preferences(role_id, data),
            "auto_scene_cg_enabled": enabled,
        }

    @staticmethod
    def project(role_id: str, data: dict[str, object]) -> dict[str, bool]:
        """Expose the plugin's editable projection separately from RoleRecord."""
        return {
            "autoSceneCgEnabled": bool(
                _role_preferences(role_id, data).get("auto_scene_cg_enabled", False)
            )
        }


def _role_preferences(role_id: str, data: dict[str, object]) -> dict[str, object]:
    preferences = data.get(role_id, {})
    if not isinstance(preferences, dict):
        raise ValueError("NovelAI 角色设置必须是对象")
    return preferences
