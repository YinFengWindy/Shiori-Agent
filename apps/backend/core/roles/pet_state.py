from __future__ import annotations

from .manifest import RoleManifestRepository
from .models import RolePetPackage, RoleRecord, now_iso


class RolePetStateStore:
    """Owns persisted pet package selection and single-active-pet state."""

    def __init__(self, repository: RoleManifestRepository) -> None:
        self._repository = repository

    def replace_packages(
        self,
        role_id: str,
        packages: list[RolePetPackage],
    ) -> RoleRecord:
        with self._repository.lock:
            roles = self._repository.list_roles()
            for index, role in enumerate(roles):
                if role.id != role_id:
                    continue
                role.pet_packages = list(packages)
                if role.selected_pet_package_id not in {
                    package.id for package in packages
                }:
                    role.selected_pet_package_id = None
                    role.desktop_pet_enabled = False
                role.updated_at = now_iso()
                roles[index] = role
                self._repository.save_roles(roles)
                return role
        raise KeyError(f"role 不存在: {role_id}")

    def select_package(self, role_id: str, package_id: str) -> RoleRecord:
        with self._repository.lock:
            roles = self._repository.list_roles()
            for index, role in enumerate(roles):
                if role.id != role_id:
                    continue
                if package_id not in {package.id for package in role.pet_packages}:
                    raise KeyError(f"桌宠包不存在: {package_id}")
                if role.selected_pet_package_id == package_id:
                    return role
                role.selected_pet_package_id = package_id
                role.updated_at = now_iso()
                roles[index] = role
                self._repository.save_roles(roles)
                return role
        raise KeyError(f"role 不存在: {role_id}")

    @staticmethod
    def set_enabled(roles: list[RoleRecord], role: RoleRecord, enabled: bool) -> None:
        if enabled and role.selected_pet_package_id is None:
            raise ValueError("启用桌宠前必须在素材库选择一个桌宠素材")
        role.desktop_pet_enabled = enabled
        if enabled:
            for other in roles:
                if other.id != role.id and other.desktop_pet_enabled:
                    other.desktop_pet_enabled = False
                    other.updated_at = now_iso()
