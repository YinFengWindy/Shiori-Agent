"""Reconcile plugin state and abandoned pet assets across disable/enable cycles."""

from __future__ import annotations

import shutil

from bus.events_lifecycle import RoleDeleted
from core.roles.store import RoleStore

from .pet_state import PLUGIN_ID, RolePetStateStore
from .models import RolePetState
from .storage import prepare_assets, role_asset_directory, asset_path
from agent.plugin_host.plugin_data import plugin_data_dir


class PetStateReconciler:
    """Cleans deleted roles even if their deletion happened while disabled."""

    def __init__(self, roles: RoleStore) -> None:
        self._roles = roles

    def reconcile(self) -> None:
        """Prunes missing roles and orphan package directories under one lock."""
        with self._roles.lock:
            prepare_assets(self._roles)
            roles = self._roles.list_roles()
            role_ids = {role.id for role in roles}

            def prune(data):
                for role_id in list(data):
                    if role_id not in role_ids:
                        del data[role_id]
                enabled = False
                for role in roles:
                    if role.id not in data:
                        continue
                    state = RolePetState.from_dict(role.id, data[role.id])
                    state.pet_packages = [
                        package
                        for package in state.pet_packages
                        if asset_path(
                            self._roles.workspace, package.spritesheet_path
                        ).is_file()
                    ]
                    if state.selected_pet_package_id not in {
                        package.id for package in state.pet_packages
                    }:
                        state.selected_pet_package_id = None
                        state.desktop_pet_enabled = False
                    state.desktop_pet_enabled = (
                        state.desktop_pet_enabled and not enabled
                    )
                    enabled = enabled or state.desktop_pet_enabled
                    data[role.id] = state.to_dict()

            self._roles.extensions.update(PLUGIN_ID, prune)
            states = {
                role.id: role for role in RolePetStateStore(self._roles).list_roles()
            }
            root = plugin_data_dir(self._roles.workspace, PLUGIN_ID)
            if root.exists():
                for pets in root.glob("pets-*"):
                    if not pets.is_dir() or pets.is_symlink():
                        continue
                    state = states.get(pets.name.removeprefix("pets-"))
                    if state is None:
                        shutil.rmtree(pets)
                        continue
                    installed = {package.id for package in state.pet_packages}
                    for package_dir in pets.iterdir():
                        if (
                            package_dir.name not in installed
                            and package_dir.is_dir()
                            and not package_dir.is_symlink()
                        ):
                            shutil.rmtree(package_dir)
            # Legacy pet-only folders are removed after metadata was committed.
            # Unrelated role images survive even when deletion kept role assets.
            for asset_dir in self._roles.assets_dir.iterdir():
                pets = asset_dir / "pets"
                if not pets.is_dir() or pets.is_symlink() or asset_dir.is_symlink():
                    continue
                if (
                    asset_dir.name not in role_ids
                    or role_asset_directory(
                        self._roles.workspace, asset_dir.name
                    ).exists()
                ):
                    shutil.rmtree(pets)

    async def on_role_deleted(self, _event: RoleDeleted) -> None:
        """Runs the same idempotent cleanup for live lifecycle notifications."""
        self.reconcile()
