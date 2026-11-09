"""Immutable package installation with recoverable file and metadata commits."""

import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from shiori_sdk.roles import Roles
from shiori_sdk.values import now_iso
from plugins.desktop_pet.backend.provider_files import resolve_staged_zip

from .package_archive import MAX_ARCHIVE_BYTES, stage_archive
from .package_schema import ValidatedPackage, validate_package
from .storage import ModelStore, model_directory, remove_owned_tree, role_directory

IMPORT_NAMESPACE = "pet_2d-pets"


class AvatarPackages:
    """Install validated packages without changing desktop_pet's selected model."""

    def __init__(self, roles: Roles, workspace: Path) -> None:
        self.roles, self.workspace = roles, workspace.resolve()
        self.store = ModelStore(roles)

    def import_package(self, role_id: str, source: str) -> dict[str, Any]:
        """Stage and verify first; promote files and publish the role index last."""
        source_path = resolve_staged_zip(
            self.workspace,
            source,
            namespace=IMPORT_NAMESPACE,
            max_bytes=MAX_ARCHIVE_BYTES,
        )
        with self.roles.read_scope():
            self.store.require_role(role_id)
            root = role_directory(self.workspace, role_id, create=True)
            temporary = root / (".import-" + uuid4().hex)
            promoted: Path | None = None
            try:
                manifest = stage_archive(source_path, temporary)
                validated = validate_package(temporary, manifest)
                installed = self.store.list_models(role_id)
                for previous in installed:
                    if previous["id"] == validated.model_id:
                        # Existing durable content must still match before claiming an idempotent import.
                        self.load(role_id, previous["id"])
                        return previous
                    if (
                        previous["character"] == manifest.document["character"]
                        and previous["version"] == manifest.document["version"]
                    ):
                        raise ValueError("同一形象版本包含不同内容，不能覆盖")
                destination = model_directory(
                    self.workspace, role_id, validated.model_id
                )
                if destination.exists():
                    recovered = validate_package(destination)
                    if recovered.model_id != validated.model_id:
                        raise ValueError("形象模型目标内容冲突")
                else:
                    os.rename(temporary, destination)
                    promoted = destination
                record = _record(validated)
                self.store.replace(role_id, [*installed, record])
                promoted = None
                return record
            finally:
                # A failed commit never deletes a pre-existing model or the user's source ZIP.
                if promoted is not None:
                    # An exception after a durable store write must not delete committed data.
                    try:
                        committed = any(
                            entry["id"] == promoted.name
                            for entry in self.store.list_models(role_id)
                        )
                    except Exception:
                        committed = (
                            True  # Unknown commit outcome: retain a recoverable copy.
                        )
                    if not committed:
                        remove_owned_tree(promoted, root)
                remove_owned_tree(temporary, root)

    def load(self, role_id: str, model_id: str) -> ValidatedPackage:
        """Recheck installed bytes and identity before granting any renderer assets."""
        record = self.store.require(role_id, model_id)
        result = validate_package(model_directory(self.workspace, role_id, model_id))
        if (
            result.model_id != record["manifest_sha256"]
            or result.manifest.document["character"] != record["character"]
            or result.manifest.document["version"] != record["version"]
        ):
            raise ValueError("已安装形象包身份不一致")
        return result

    def remove(self, role_id: str, model_id: str) -> None:
        """Commit removal before deleting files; startup reconciliation retries cleanup."""
        with self.roles.read_scope():
            self.store.require(role_id, model_id)
            installed = self.store.list_models(role_id)
            path = model_directory(self.workspace, role_id, model_id)
            self.store.replace(
                role_id, [entry for entry in installed if entry["id"] != model_id]
            )
            remove_owned_tree(path, role_directory(self.workspace, role_id))


def _record(package: ValidatedPackage) -> dict[str, Any]:
    return {
        "id": package.model_id,
        "manifest_sha256": package.manifest.sha256,
        "character": package.manifest.document["character"],
        "version": package.manifest.document["version"],
        "display_name": package.display_name,
        "body": package.body,
        "imported_at": now_iso(),
    }
