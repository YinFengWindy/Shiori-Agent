"""Codex model descriptions and private sprite data for presentation."""

from pathlib import Path
from typing import Any
from shiori_sdk.roles import Roles
from shiori_sdk.services import ServiceReference
from .import_source import resolve_package_import_source
from .models import RolePetPackage
from .pet_packages import RolePetPackageService
from .pet_state import RolePetStateStore
from .storage import asset_path
from .package_archive import manifest_actions

SPRITE_PROVIDER: ServiceReference = {
    "plugin_id": "pet_codex_sprite",
    "service_id": "models",
}
SPRITE_BODY = {"width": 192, "height": 208}


class SpriteModels:
    """Serve public descriptors while keeping atlas paths and rows private."""

    reference: ServiceReference = SPRITE_PROVIDER
    label = "Codex 精灵图"
    import_options: dict[str, Any] = {
        "namespace": "pet_codex_sprite-pets",
        "max_file_bytes": 32 * 1024 * 1024,
        "extensions": ["zip"],
        "label": "Codex 精灵图 ZIP",
    }

    def __init__(self, roles: Roles, workspace: Path) -> None:
        self.workspace = workspace
        self.state = RolePetStateStore(roles)
        self.packages = RolePetPackageService(roles, workspace)

    def list_models(self, role_id: str) -> list[dict[str, Any]]:
        """List metadata even when an asset needs repair."""
        return [self.describe(p) for p in self.state.require_role(role_id).pet_packages]

    def package(self, role_id: str, model_id: str) -> RolePetPackage:
        """Find a role-owned model, refusing a cross-role lookup."""
        package = next(
            (
                p
                for p in self.state.require_role(role_id).pet_packages
                if p.id == model_id
            ),
            None,
        )
        if package is None:
            raise KeyError(f"桌宠包不存在: {model_id}")
        return package

    def get_model(self, role_id: str, model_id: str) -> dict[str, Any]:
        """Require usable assets before selecting or preparing a model."""
        package = self.package(role_id, model_id)
        if not asset_path(self.workspace, package.spritesheet_path).is_file():
            raise FileNotFoundError(f"桌宠精灵图不存在: {model_id}")
        return self.describe(package)

    def import_model(self, role_id: str, source: str) -> dict[str, Any]:
        """Adopt only native-selected private staging files."""
        path = resolve_package_import_source(self.workspace, source)
        return self.describe(self.packages.import_package(role_id, path))

    def remove_model(self, role_id: str, model_id: str) -> None:
        """Remove one installed sprite's metadata and files."""
        self.packages.remove_package(role_id, model_id)

    def describe(self, package: RolePetPackage) -> dict[str, Any]:
        """Expose semantic action names, never sprite row names."""
        return {
            "id": package.id,
            "display_name": package.display_name,
            "preview_abs": (
                str(asset_path(self.workspace, package.preview_path))
                if package.preview_path
                else None
            ),
            "body": dict(SPRITE_BODY),
            "actions": list(manifest_actions({"actions": package.actions})),
        }

    def presentation(self, role_id: str, model_id: str) -> dict[str, Any]:
        """Validated private load data sent only to this provider's background."""
        self.get_model(role_id, model_id)
        package = self.package(role_id, model_id)
        return {
            "spritesheet_abs": str(
                asset_path(self.workspace, package.spritesheet_path)
            ),
            "actions": manifest_actions({"actions": package.actions}),
            "body": dict(SPRITE_BODY),
        }
