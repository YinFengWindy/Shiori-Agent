"""Desktop-owned model selection and atomic exclusive role visibility."""

from typing import Any
from shiori_sdk.roles import Roles
from .models import RolePetState, SelectedModel
from .storage import PLUGIN_ID


class RolePetStateStore:
    """Persist references without owning or deleting provider assets."""

    def __init__(self, role_store: Roles) -> None:
        self.roles = role_store

    def get_role(self, role_id: str) -> RolePetState | None:
        """Read one existing role's presentation intent."""
        with self.roles.read_scope():
            if self.roles.get_role(role_id) is None:
                return None
            return RolePetState.from_dict(
                role_id, self.roles.extensions.read(PLUGIN_ID).get(role_id, {})
            )

    def require_role(self, role_id: str) -> RolePetState:
        """Reject missing roles before mutations."""
        role = self.get_role(role_id)
        if role is None:
            raise KeyError(f"role 不存在: {role_id}")
        return role

    def is_enabled(self, role_id: str) -> bool:
        """The role switch is distinct from device window visibility."""
        role = self.get_role(role_id)
        return role is not None and role.desktop_pet_enabled

    def list_roles(self) -> list[RolePetState]:
        """Read a consistent role selection snapshot."""
        with self.roles.read_scope():
            data = self.roles.extensions.read(PLUGIN_ID)
            return [
                RolePetState.from_dict(role.id, data.get(role.id, {}))
                for role in self.roles.list_roles()
            ]

    def select_model(
        self, role_id: str, selection: SelectedModel | None
    ) -> RolePetState:
        """Commit a validated selection without enabling an inactive role."""
        with self.roles.read_scope():
            role = self.require_role(role_id)
            role.selected_model = selection
            if selection is None:
                role.desktop_pet_enabled = False

            def publish(data: dict[str, Any]) -> None:
                data[role_id] = {**data.get(role_id, {}), **role.to_dict()}

            self.roles.extensions.update(PLUGIN_ID, publish)
            return role

    def set_enabled(self, role_id: str, enabled: bool) -> None:
        """Commit visibility through the shared exclusive draft validator."""
        with self.roles.read_scope():
            self.require_role(role_id)
            self.roles.extensions.update(
                PLUGIN_ID,
                lambda data: self.write_draft(role_id, {"enabled": enabled}, data),
            )

    @staticmethod
    def write_draft(role_id: str, values: dict[str, Any], data: dict[str, Any]) -> None:
        """Preserve old package metadata until its provider migrates it."""
        enabled = values.get("enabled")
        if not isinstance(enabled, bool):
            raise ValueError("桌宠 enabled 必须是布尔值")
        role = RolePetState.from_dict(role_id, data.get(role_id, {}))
        if enabled and role.selected_model is None:
            raise ValueError("启用桌宠前必须在素材库选择一个桌宠素材")
        if enabled:
            for other_id, state in data.items():
                if other_id != role_id:
                    data[other_id] = {**state, "desktop_pet_enabled": False}
        role.desktop_pet_enabled = enabled
        data[role_id] = {**data.get(role_id, {}), **role.to_dict()}

    @staticmethod
    def project(role_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Project form fields without provider-specific data."""
        role = RolePetState.from_dict(role_id, data.get(role_id, {}))
        return {
            "enabled": role.desktop_pet_enabled,
            "available": role.selected_model is not None,
        }
