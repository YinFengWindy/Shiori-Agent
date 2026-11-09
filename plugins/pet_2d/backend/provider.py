"""Public model descriptors and validated private preparation payloads."""

from pathlib import Path
from typing import Any

from shiori_sdk.roles import Roles
from shiori_sdk.services import ServiceReference

from .package_archive import MAX_ARCHIVE_BYTES, SCHEMA, regular_path
from .packages import AvatarPackages, IMPORT_NAMESPACE
from .storage import model_directory

AVATAR_PROVIDER: ServiceReference = {"plugin_id": "pet_2d", "service_id": "models"}


class AvatarModels:
    """Expose format-independent selection metadata while retaining source documents."""

    reference: ServiceReference = AVATAR_PROVIDER
    label = "2.5D 形象"
    import_options: dict[str, Any] = {
        "namespace": IMPORT_NAMESPACE,
        "max_file_bytes": MAX_ARCHIVE_BYTES,
        "extensions": ["zip"],
        "label": "Prelulu 2.5D ZIP",
    }

    def __init__(self, roles: Roles, workspace: Path) -> None:
        self.packages = AvatarPackages(roles, workspace)

    def list_models(self, role_id: str) -> list[dict[str, Any]]:
        """List persisted membership without silently discarding damaged files."""
        return [
            self._describe(role_id, record)
            for record in self.packages.store.list_models(role_id)
        ]

    def get_model(self, role_id: str, model_id: str) -> dict[str, Any]:
        """Require a complete supported package before selection or presentation."""
        self.packages.load(role_id, model_id)
        return self._describe(role_id, self.packages.store.require(role_id, model_id))

    def import_model(self, role_id: str, source: str) -> dict[str, Any]:
        """Install one immutable package without enabling or selecting a role."""
        return self._describe(role_id, self.packages.import_package(role_id, source))

    def remove_model(self, role_id: str, model_id: str) -> None:
        """Delete provider-owned data; the desktop owns selection retirement."""
        self.packages.remove(role_id, model_id)

    def presentation(self, role_id: str, model_id: str) -> dict[str, Any]:
        """Prepare all source documents and explicitly granted image paths."""
        package = self.packages.load(role_id, model_id)
        root = model_directory(self.packages.workspace, role_id, model_id)
        return {
            "body": package.body,
            "actions": [],
            "model_data": {
                "schema": SCHEMA,
                "manifest": package.manifest.document,
                "binding": package.binding,
                "rig": package.rig,
                "baked": package.baked,
                "images": [
                    {"file": name, "image_path": str(regular_path(root, name))}
                    for name in package.images
                ],
            },
        }

    def _describe(self, role_id: str, record: dict[str, Any]) -> dict[str, Any]:
        root = model_directory(self.packages.workspace, role_id, record["id"])
        preview = root / "source.png"
        # Missing preview stays unavailable; no asset URL is granted through an escaped path.
        preview_abs = (
            str(preview) if preview.resolve() == preview and preview.is_file() else None
        )
        return {
            "id": record["id"],
            "display_name": record["display_name"],
            "preview_abs": preview_abs,
            "body": record["body"],
            "actions": [],
        }
