from __future__ import annotations

import json
import zipfile
from pathlib import Path

from core.roles import RolePetPackageService, RoleStore


def test_import_pet_package_accepts_a_single_wrapper_directory(tmp_path: Path, monkeypatch) -> None:
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
                }
            ),
        )
        archive.writestr("feibi/spritesheet.webp", b"fixture")
        archive.writestr("feibi/preview.webp", b"preview")
    store = RoleStore(tmp_path / "workspace")
    role = store.create_role(name="菲比", system_prompt="fixture")
    service = RolePetPackageService(store)
    monkeypatch.setattr(service, "_validate_atlas", lambda _data: None)
    monkeypatch.setattr(service, "_validate_preview", lambda _data: None)

    package = service.import_package(role.id, archive_path)

    assert package.id == "feibi"
    assert (store.roles_dir / package.manifest_path).is_file()
    assert package.preview_path is not None
    assert (store.roles_dir / package.preview_path).read_bytes() == b"preview"


def test_selecting_a_pet_package_is_role_local_and_removal_clears_selection(
    tmp_path: Path,
    monkeypatch,
) -> None:
    store = RoleStore(tmp_path / "workspace")
    role = store.create_role(name="菲比", system_prompt="fixture")
    service = RolePetPackageService(store)
    monkeypatch.setattr(service, "_validate_atlas", lambda _data: None)
    monkeypatch.setattr(service, "_validate_preview", lambda _data: None)

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
    assert store.get_role(role.id).selected_pet_package_id is None
