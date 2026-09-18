from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest
from PIL import Image

from core.roles import RoleStore
from plugins.desktop_pet.backend.pet_packages import RolePetPackageService
from plugins.desktop_pet.backend import package_images
from plugins.desktop_pet.backend.pet_state import RolePetStateStore
from plugins.desktop_pet.backend.reconcile import PetStateReconciler


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
    store = RoleStore(tmp_path / "workspace")
    role = store.create_role(name="菲比", system_prompt="fixture")
    service = RolePetPackageService(store)
    monkeypatch.setattr(package_images, "validate_atlas", lambda _data: None)
    monkeypatch.setattr(package_images, "validate_preview", lambda _data: ".webp")

    package = service.import_package(role.id, archive_path)

    assert package.id == "feibi"
    assert (store.workspace / package.manifest_path).is_file()
    assert package.preview_path is not None
    assert (store.workspace / package.preview_path).read_bytes() == b"preview"
    assert package.actions == {"greeting": "waving"}


def test_cleared_plugin_assets_can_reimport_same_package_without_reviving_backup(
    tmp_path, monkeypatch
):
    import shutil

    archive_path = tmp_path / "pet.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(
            "pet.json",
            json.dumps(
                {
                    "id": "pet",
                    "displayName": "Pet",
                    "description": "test",
                    "spritesheetPath": "spritesheet.webp",
                }
            ),
        )
        archive.writestr("spritesheet.webp", b"new pet")
    roles = RoleStore(tmp_path / "workspace")
    role = roles.create_role(role_id="mira", name="Mira", system_prompt="test")
    legacy = roles.assets_dir / "mira/pets/abandoned/spritesheet.webp"
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(b"old interrupted import")
    unrelated = roles.assets_dir / "mira/portrait.png"
    unrelated.write_bytes(b"role portrait")
    PetStateReconciler(roles).reconcile()
    service = RolePetPackageService(roles)
    monkeypatch.setattr(package_images, "validate_atlas", lambda _: None)
    package = service.import_package(role.id, archive_path)
    service.select_package(role.id, package.id)
    RolePetStateStore(roles).set_enabled(role.id, True)
    # Recreate a retained upgrade backup; its completed receipt must win.
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(b"retained backup")
    shutil.rmtree(roles.workspace / "plugin-data/desktop_pet")
    PetStateReconciler(roles).reconcile()
    state = RolePetStateStore(roles).require_role(role.id)
    assert state.pet_packages == []
    assert state.selected_pet_package_id is None
    assert not state.desktop_pet_enabled
    replacement = RolePetPackageService(roles).import_package(role.id, archive_path)
    assert replacement.id == package.id
    assert (roles.workspace / replacement.spritesheet_path).read_bytes() == b"new pet"
    PetStateReconciler(roles).reconcile()
    assert unrelated.read_bytes() == b"role portrait"
    assert not (
        roles.workspace / "plugin-data/desktop_pet/pets-mira/abandoned"
    ).exists()


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
    store = RoleStore(tmp_path / "workspace")
    role = store.create_role(name="Invalid", system_prompt="fixture")
    service = RolePetPackageService(store)
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
    store = RoleStore(tmp_path / "workspace")
    role = store.create_role(name="System action", system_prompt="fixture")
    service = RolePetPackageService(store)
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
    store = RoleStore(tmp_path / "workspace")
    role = store.create_role(name="Legacy", system_prompt="fixture")
    service = RolePetPackageService(store)
    monkeypatch.setattr(package_images, "validate_atlas", lambda _data: None)

    package = service.import_package(role.id, archive_path)

    assert package.preview_path is None
    assert (store.workspace / package.manifest_path).is_file()


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
    store = RoleStore(tmp_path / "workspace")
    role = store.create_role(name="PNG preview", system_prompt="fixture")
    service = RolePetPackageService(store)
    monkeypatch.setattr(package_images, "validate_atlas", lambda _data: None)

    package = service.import_package(role.id, archive_path)

    assert package.preview_path is not None
    assert package.preview_path.endswith("/preview.png")
    assert (store.workspace / package.preview_path).read_bytes() == preview.getvalue()


def test_selecting_a_pet_package_is_role_local_and_removal_clears_selection(
    tmp_path: Path,
    monkeypatch,
) -> None:
    store = RoleStore(tmp_path / "workspace")
    role = store.create_role(name="菲比", system_prompt="fixture")
    service = RolePetPackageService(store)
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


def test_concurrent_real_package_imports_keep_both_metadata_and_assets(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    import threading

    # A real atlas with one nontransparent pixel in each required frame.
    atlas = Image.new("RGBA", (1536, 1872))
    for row, count in enumerate((6, 8, 8, 4, 5, 8, 6, 6, 6)):
        for column in range(count):
            atlas.putpixel((column * 192, row * 208), (255, 0, 0, 255))
    buffer = io.BytesIO()
    atlas.save(buffer, format="WEBP", lossless=True)
    for package_id in ("first", "second"):
        with zipfile.ZipFile(tmp_path / f"{package_id}.zip", "w") as archive:
            archive.writestr(
                "pet.json",
                json.dumps(
                    {
                        "id": package_id,
                        "displayName": package_id,
                        "description": "fixture",
                        "spritesheetPath": "spritesheet.webp",
                    }
                ),
            )
            archive.writestr("spritesheet.webp", buffer.getvalue())
    first = RoleStore(tmp_path / "workspace")
    first.create_role(role_id="mira", name="Mira", system_prompt="test")
    second = RoleStore(tmp_path / "workspace")
    barrier = threading.Barrier(2)

    def install(store, package_id):
        barrier.wait(timeout=3)
        return RolePetPackageService(store).import_package(
            "mira", tmp_path / f"{package_id}.zip"
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(install, store, package_id)
            for store, package_id in ((first, "first"), (second, "second"))
        ]
        imported = [future.result(timeout=10) for future in futures]
    state = RolePetStateStore(first).require_role("mira")
    assert {package.id for package in state.pet_packages} == {"first", "second"}
    assert all(
        (first.workspace / package.spritesheet_path).is_file() for package in imported
    )
