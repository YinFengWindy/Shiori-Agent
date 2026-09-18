"""Pet migration publishes paths only after bytes and survives explicit clearing."""

import shutil
from pathlib import Path

import pytest

from core.roles.store import RoleStore
from plugins.desktop_pet.backend.storage import prepare_assets, role_asset_directory


def _legacy(roles: RoleStore):
    roles.create_role(role_id="mira", name="Mira", system_prompt="test")
    source = roles.assets_dir / "mira/pets/pet/spritesheet.webp"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"legacy pet")
    roles.extensions.update(
        "desktop_pet",
        lambda data: data.update(
            {
                "mira": {
                    "pet_packages": [
                        {
                            "spritesheet_path": "assets/mira/pets/pet/spritesheet.webp",
                            "manifest_path": "assets/mira/pets/pet/pet.json",
                        }
                    ]
                }
            }
        ),
    )
    return source


def test_failed_metadata_publish_preserves_source_and_retry_completes(
    tmp_path, monkeypatch
):
    roles = RoleStore(tmp_path)
    source = _legacy(roles)
    before = roles.manifest_path.read_bytes()
    replace = Path.replace

    def fail(path, target):
        if target == roles.manifest_path:
            raise OSError("manifest locked")
        return replace(path, target)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "replace", fail)
        with pytest.raises(OSError, match="manifest locked"):
            prepare_assets(roles)
    assert source.read_bytes() == b"legacy pet"
    assert roles.manifest_path.read_bytes() == before
    prepare_assets(roles)
    package = roles.extensions.read("desktop_pet")["mira"]["pet_packages"][0]
    target = roles.workspace / package["spritesheet_path"]
    assert target == role_asset_directory(tmp_path, "mira") / "pet/spritesheet.webp"
    assert target.read_bytes() == b"legacy pet"
    shutil.rmtree(role_asset_directory(tmp_path, "mira"))
    prepare_assets(roles)
    assert source.exists()
    assert not target.exists(), "an explicit clear must not replay a legacy backup"


def test_legacy_unregistered_assets_are_prepared_before_new_imports(tmp_path):
    roles = RoleStore(tmp_path)
    roles.create_role(role_id="mira", name="Mira", system_prompt="test")
    source = roles.assets_dir / "mira/pets/orphan/spritesheet.webp"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"interrupted import")
    prepare_assets(roles)
    root = role_asset_directory(tmp_path, "mira")
    assert (root / "orphan/spritesheet.webp").read_bytes() == b"interrupted import"
    (root / "new-pet").mkdir()
    roles.extensions.update(
        "desktop_pet", lambda data: data.update({"mira": {"pet_packages": []}})
    )
    prepare_assets(roles)
    assert (root / "new-pet").exists()
