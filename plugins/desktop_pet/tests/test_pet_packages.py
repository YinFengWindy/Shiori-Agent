from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest
from PIL import Image

from shiori_sdk.testing.roles import FakeRoles
from shiori_sdk.testing.memory import FakeMemoryStorage
from plugins.desktop_pet.backend.pet_packages import RolePetPackageService
from plugins.desktop_pet.backend import package_images
from plugins.desktop_pet.backend.pet_state import RolePetStateStore


def test_import_pet_package_accepts_a_single_wrapper_directory(
    tmp_path: Path, monkeypatch
) -> None:
    archive_path = tmp_path / "feibi.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(
            "feibi/pet.json",
            json.dumps(
                {
                    "id": "feibi",
                    "displayName": "菲比",
                    "description": "fixture",
                    "spritesheetPath": "spritesheet.webp",
                    "previewPath": "preview.webp",
                    "actions": {"greeting": "waving"},
                }
            ),
        )
        archive.writestr("feibi/spritesheet.webp", b"fixture")
        archive.writestr("feibi/preview.webp", b"preview")
    store = FakeRoles(tmp_path / "workspace")
    role = store.create_role(role_id="mira", name="菲比", system_prompt="fixture")
    service = RolePetPackageService(store, tmp_path / "workspace", FakeMemoryStorage())
    monkeypatch.setattr(package_images, "validate_atlas", lambda _data: None)
    monkeypatch.setattr(package_images, "validate_preview", lambda _data: ".webp")

    package = service.import_package(role.id, archive_path)

    assert package.id == "feibi"
    assert ((tmp_path / "workspace") / package.manifest_path).is_file()
    assert package.preview_path is not None
    assert ((tmp_path / "workspace") / package.preview_path).read_bytes() == b"preview"
    assert package.actions == {"greeting": "waving"}


def test_import_pet_package_rejects_unknown_action_state(
    tmp_path: Path, monkeypatch
) -> None:
    archive_path = tmp_path / "invalid-actions.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(
            "pet.json",
            json.dumps(
                {
                    "id": "invalid-actions",
                    "displayName": "Invalid",
                    "description": "fixture",
                    "spritesheetPath": "spritesheet.webp",
                    "actions": {"sleep": "not-a-sprite-state"},
                }
            ),
        )
        archive.writestr("spritesheet.webp", b"fixture")
    store = FakeRoles(tmp_path / "workspace")
    role = store.create_role(role_id="mira", name="Invalid", system_prompt="fixture")
    service = RolePetPackageService(store, tmp_path / "workspace", FakeMemoryStorage())
    monkeypatch.setattr(package_images, "validate_atlas", lambda _data: None)

    with pytest.raises(ValueError, match="动作状态无效"):
        service.import_package(role.id, archive_path)


def test_import_pet_package_rejects_system_action_state(
    tmp_path: Path, monkeypatch
) -> None:
    archive_path = tmp_path / "system-action.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(
            "pet.json",
            json.dumps(
                {
                    "id": "system-action",
                    "displayName": "System action",
                    "description": "fixture",
                    "spritesheetPath": "spritesheet.webp",
                    "actions": {"broken": "failed"},
                }
            ),
        )
        archive.writestr("spritesheet.webp", b"fixture")
    store = FakeRoles(tmp_path / "workspace")
    role = store.create_role(
        role_id="mira", name="System action", system_prompt="fixture"
    )
    service = RolePetPackageService(store, tmp_path / "workspace", FakeMemoryStorage())
    monkeypatch.setattr(package_images, "validate_atlas", lambda _data: None)

    with pytest.raises(ValueError, match="动作状态无效"):
        service.import_package(role.id, archive_path)


def test_import_pet_package_accepts_a_package_without_preview(
    tmp_path: Path, monkeypatch
) -> None:
    archive_path = tmp_path / "legacy.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(
            "pet.json",
            json.dumps(
                {
                    "id": "legacy",
                    "displayName": "Legacy",
                    "description": "fixture",
                    "spritesheetPath": "spritesheet.webp",
                }
            ),
        )
        archive.writestr("spritesheet.webp", b"fixture")
    store = FakeRoles(tmp_path / "workspace")
    role = store.create_role(role_id="mira", name="Legacy", system_prompt="fixture")
    service = RolePetPackageService(store, tmp_path / "workspace", FakeMemoryStorage())
    monkeypatch.setattr(package_images, "validate_atlas", lambda _data: None)

    package = service.import_package(role.id, archive_path)

    assert package.preview_path is None
    assert ((tmp_path / "workspace") / package.manifest_path).is_file()


def test_import_pet_package_uses_the_preview_image_format_for_its_extension(
    tmp_path: Path,
    monkeypatch,
) -> None:
    preview = io.BytesIO()
    Image.new("RGBA", (64, 64), (255, 0, 0, 255)).save(preview, format="PNG")
    archive_path = tmp_path / "png-preview.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(
            "pet.json",
            json.dumps(
                {
                    "id": "png-preview",
                    "displayName": "PNG preview",
                    "description": "fixture",
                    "spritesheetPath": "spritesheet.webp",
                    "previewPath": "preview.webp",
                }
            ),
        )
        archive.writestr("spritesheet.webp", b"fixture")
        archive.writestr("preview.webp", preview.getvalue())
    store = FakeRoles(tmp_path / "workspace")
    role = store.create_role(
        role_id="mira", name="PNG preview", system_prompt="fixture"
    )
    service = RolePetPackageService(store, tmp_path / "workspace", FakeMemoryStorage())
    monkeypatch.setattr(package_images, "validate_atlas", lambda _data: None)

    package = service.import_package(role.id, archive_path)

    assert package.preview_path is not None
    assert package.preview_path.endswith("/preview.png")
    assert (
        (tmp_path / "workspace") / package.preview_path
    ).read_bytes() == preview.getvalue()


def test_selecting_a_pet_package_is_role_local_and_removal_clears_selection(
    tmp_path: Path,
    monkeypatch,
) -> None:
    store = FakeRoles(tmp_path / "workspace")
    role = store.create_role(role_id="mira", name="菲比", system_prompt="fixture")
    service = RolePetPackageService(store, tmp_path / "workspace", FakeMemoryStorage())
    monkeypatch.setattr(package_images, "validate_atlas", lambda _data: None)
    monkeypatch.setattr(package_images, "validate_preview", lambda _data: ".webp")

    for package_id in ("idle", "wave"):
        archive_path = tmp_path / f"{package_id}.zip"
        with zipfile.ZipFile(archive_path, "w") as archive:
            archive.writestr(
                "pet.json",
                json.dumps(
                    {
                        "id": package_id,
                        "displayName": package_id,
                        "description": "fixture",
                        "spritesheetPath": "spritesheet.webp",
                        "previewPath": "preview.webp",
                    }
                ),
            )
            archive.writestr("spritesheet.webp", b"fixture")
            archive.writestr("preview.webp", b"preview")
        service.import_package(role.id, archive_path)

    selected = service.select_package(role.id, "wave")

    assert selected.selected_pet_package_id == "wave"
    service.remove_package(role.id, "wave")
    assert (
        RolePetStateStore(store).require_role(role.id).selected_pet_package_id is None
    )
