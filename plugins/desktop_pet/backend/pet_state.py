"""Desktop-pet persistence and atomic per-role draft validation."""

from __future__ import annotations

from typing import Any

from shiori_sdk.roles import Roles

from .models import RolePetPackage, RolePetState
from .storage import PLUGIN_ID


class RolePetStateStore:
    """Owns package membership and the single enabled role across all instances."""

    def __init__(self, role_store: Roles) -> None:
        self.roles = role_store

    def get_role(self, role_id: str) -> RolePetState | None:
        """Reads plugin state only for a role which still exists."""
        with self.roles.read_scope():
            if self.roles.get_role(role_id) is None:
                return None
            return RolePetState.from_dict(
                role_id, self.roles.extensions.read(PLUGIN_ID).get(role_id, {})
            )

    def list_roles(self) -> list[RolePetState]:
        """Reads one consistent cross-role plugin snapshot."""
        with self.roles.read_scope():
            data = self.roles.extensions.read(PLUGIN_ID)
            return [
                RolePetState.from_dict(role.id, data.get(role.id, {}))
                for role in self.roles.list_roles()
            ]

    def require_role(self, role_id: str) -> RolePetState:
        """Rejects a missing role before any package or draft mutation."""
        role = self.get_role(role_id)
        if role is None:
            raise KeyError(f"role 不存在: {role_id}")
        return role

    def replace_packages(
        self, role_id: str, packages: list[RolePetPackage]
    ) -> RolePetState:
        """Replaces packages and clears visibility if their selection disappeared."""
        with self.roles.read_scope():
            role = self.require_role(role_id)
            role.pet_packages = list(packages)
            if role.selected_pet_package_id not in {package.id for package in packages}:
                role.selected_pet_package_id = None
                role.desktop_pet_enabled = False
            self.roles.extensions.update(
                PLUGIN_ID, lambda data: data.update({role_id: role.to_dict()})
            )
            return role

    def select_package(self, role_id: str, package_id: str) -> RolePetState:
        """Selects an installed package without enabling it."""
        with self.roles.read_scope():
            role = self.require_role(role_id)
            if package_id not in {package.id for package in role.pet_packages}:
                raise KeyError(f"桌宠包不存在: {package_id}")
            role.selected_pet_package_id = package_id
            self.roles.extensions.update(
                PLUGIN_ID, lambda data: data.update({role_id: role.to_dict()})
            )
            return role

    def set_enabled(self, role_id: str, enabled: bool) -> None:
        """Commits plugin visibility for non-form callers using the same validator."""
        with self.roles.read_scope():
            self.require_role(role_id)
            self.roles.extensions.update(
                PLUGIN_ID,
                lambda data: self.write_draft(role_id, {"enabled": enabled}, data),
            )

    @staticmethod
    def write_draft(role_id: str, values: dict[str, Any], data: dict[str, Any]) -> None:
        """Validates a draft in the role save's detached transaction namespace."""
        enabled = values.get("enabled")
        if not isinstance(enabled, bool):
            raise ValueError("桌宠 enabled 必须是布尔值")
        role = RolePetState.from_dict(role_id, data.get(role_id, {}))
        if enabled and role.selected_pet_package_id is None:
            raise ValueError("启用桌宠前必须在素材库选择一个桌宠素材")
        role.desktop_pet_enabled = enabled
        if enabled:
            for other_id, state in list(data.items()):
                if other_id != role_id:
                    data[other_id] = {**state, "desktop_pet_enabled": False}
        data[role_id] = role.to_dict()

    @staticmethod
    def project(role_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Exposes form state without leaking package metadata into roles.list."""
        role = RolePetState.from_dict(role_id, data.get(role_id, {}))
        return {
            "enabled": role.desktop_pet_enabled,
            "available": role.selected_pet_package_id is not None,
        }
