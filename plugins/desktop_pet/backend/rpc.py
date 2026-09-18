"""Plugin-owned pet package and binding RPC projections."""

from __future__ import annotations

from typing import Any

from .import_source import resolve_package_import_source
from .models import RolePetPackage, RolePetState
from .pet_packages import RolePetPackageService
from .pet_state import RolePetStateStore
from .storage import asset_path
from core.roles.store import RoleStore


class DesktopPetRpcHandlers:
    """Owns request/response shaping for every ``plugin.desktop_pet.*`` method."""

    def __init__(self, *, role_store: RoleStore) -> None:
        self._role_store = role_store
        self._packages = RolePetPackageService(role_store)
        self._state = RolePetStateStore(role_store)

    async def pets_list(self, payload: dict[str, Any]) -> dict[str, Any]:
        """``plugin.desktop_pet.pets.list``: one role's pet packages.

        The same rows ``roles.list`` used to carry on every role payload. They
        move here because the desktop's package manager UI is becoming this
        plugin's (#181-D), and a plugin's UI can only reach its own
        ``plugin.<id>.*`` namespace — it has no way to ask a core method.
        """
        role = self._require_role(payload)
        return {
            "selected_package_id": role.selected_pet_package_id,
            "packages": [self._serialize(package) for package in role.pet_packages],
        }

    async def pets_import(self, payload: dict[str, Any]) -> dict[str, Any]:
        """``plugin.desktop_pet.pets.import``: validate and install one ZIP."""
        role_id = _require_role_id(payload)
        source = str(payload.get("source") or "").strip()
        if not source:
            raise ValueError("缺少桌宠包路径")
        staged_source = resolve_package_import_source(
            self._role_store.workspace, source
        )
        package = self._packages.import_package(role_id, staged_source)
        return {"package": self._serialize(package), **await self.pets_list(payload)}

    async def pets_remove(self, payload: dict[str, Any]) -> dict[str, Any]:
        """``plugin.desktop_pet.pets.remove``: delete one package and its files."""
        self._packages.remove_package(
            _require_role_id(payload), _require_package_id(payload)
        )
        return await self.pets_list(payload)

    async def pets_select(self, payload: dict[str, Any]) -> dict[str, Any]:
        """``plugin.desktop_pet.pets.select``: choose which package renders."""
        self._packages.select_package(
            _require_role_id(payload), _require_package_id(payload)
        )
        return await self.pets_list(payload)

    def _require_role(self, payload: dict[str, Any]) -> RolePetState:
        role_id = _require_role_id(payload)
        role = self._state.get_role(role_id)
        if role is None:
            raise KeyError(f"role 不存在: {role_id}")
        return role

    def _serialize(self, package: RolePetPackage) -> dict[str, Any]:
        """Adds the two absolute paths the desktop grants asset URLs for.

        ``spritesheet_abs`` and ``preview_abs`` are declared trusted fields in
        ``apps/desktop/src/assets/localAssetPolicy.ts``; the names are the
        contract, not the shape, so they match what ``role_presenter`` emitted.
        """
        workspace = self._role_store.workspace
        preview = package.preview_path
        return {
            **package.to_dict(),
            "spritesheet_abs": str(asset_path(workspace, package.spritesheet_path)),
            "preview_abs": str(asset_path(workspace, preview)) if preview else None,
        }

    async def binding_get(self, _payload: dict[str, Any]) -> dict[str, Any]:
        """``plugin.desktop_pet.binding.get``: the role/package pair to render.

        Takes no arguments: the answer is "whichever role has its pet switched
        on", and at most one can — ``pet_state.set_enabled`` clears the others
        on write. (The pre-#181-C main-process version accepted an optional
        role id, but no caller ever passed one; it is not carried over. If
        #181-D needs a by-id lookup for the role form, it can add one then,
        with a caller.)

        Returns ``{"binding": None}`` rather than raising when nothing is
        bound: "no role has a pet package selected" is the ordinary state of a
        fresh install, not a failure the caller should surface as an error.
        """
        role = self._resolve_role()
        if role is None:
            return {"binding": None}
        package = self._selected_package(role)
        if package is None:
            return {"binding": None}
        spritesheet = asset_path(self._role_store.workspace, package.spritesheet_path)
        if not spritesheet.is_file():
            return {"binding": None}
        return {
            "binding": {
                "role_id": role.id,
                "package": {
                    "id": package.id,
                    "display_name": package.display_name,
                    "spritesheet_abs": str(spritesheet.resolve()),
                },
                "actions": dict(package.actions),
            }
        }

    def _resolve_role(self) -> RolePetState | None:
        return next(
            (role for role in self._state.list_roles() if role.desktop_pet_enabled),
            None,
        )

    @staticmethod
    def _selected_package(role: RolePetState) -> RolePetPackage | None:
        if not role.selected_pet_package_id:
            return None
        return next(
            (
                item
                for item in role.pet_packages
                if item.id == role.selected_pet_package_id
            ),
            None,
        )


def _require_role_id(payload: dict[str, Any]) -> str:
    role_id = str(payload.get("role_id") or "").strip()
    if not role_id:
        raise ValueError("缺少 role_id")
    return role_id


def _require_package_id(payload: dict[str, Any]) -> str:
    package_id = str(payload.get("package_id") or "").strip()
    if not package_id:
        raise ValueError("缺少 package_id")
    return package_id
