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
                }
            ),
        )
        archive.writestr("feibi/spritesheet.webp", b"fixture")
    store = RoleStore(tmp_path / "workspace")
    role = store.create_role(name="菲比", system_prompt="fixture")
    service = RolePetPackageService(store)
    monkeypatch.setattr(service, "_validate_atlas", lambda _data: None)

    package = service.import_package(role.id, archive_path)

    assert package.id == "feibi"
    assert (store.roles_dir / package.manifest_path).is_file()
