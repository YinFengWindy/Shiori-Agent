"""Asset paths reject traversal and migration honors the storage capability."""

import pytest
from shiori_sdk.testing.roles import FakeRoles
from plugins.desktop_pet.backend.storage import (
    prepare_assets,
    asset_path,
    role_asset_directory,
)


def test_prepare_uses_granted_asset_source_and_storage_destination(tmp_path):
    roles = FakeRoles(tmp_path)
    roles.create_role(role_id="mira", name="Mira", system_prompt="test")
    roles.extensions.values["desktop_pet"] = {
        "mira": {
            "pet_packages": [{"spritesheet_path": "assets/mira/pets/pet/sprite.webp"}]
        }
    }
    target = tmp_path / "plugin-data/desktop_pet/pets-mira"
    calls = []

    class Storage:
        def migrate_data(self, workspace, plugin_id, name, source):
            calls.append((workspace, plugin_id, name, source))
            return target

    prepare_assets(roles, tmp_path, Storage())
    assert calls == [
        (tmp_path, "desktop_pet", "pets-mira", roles.asset_path("assets/mira/pets"))
    ]
    assert roles.extensions.read("desktop_pet") == {
        "mira": {
            "pet_packages": [
                {
                    "spritesheet_path": "plugin-data/desktop_pet/pets-mira/pet/sprite.webp"
                }
            ]
        }
    }
    with pytest.raises(ValueError):
        asset_path(tmp_path, "../outside")
    with pytest.raises(ValueError):
        role_asset_directory(tmp_path, "../mira")


def test_prepare_migrates_every_role_even_without_registered_packages(tmp_path):
    roles = FakeRoles(tmp_path)
    for role_id in ("mira", "orphaned"):
        roles.create_role(role_id=role_id, name=role_id, system_prompt="test")
    migrated = []

    class Storage:
        def migrate_data(self, workspace, plugin_id, name, source):
            migrated.append((name, source))
            return tmp_path / "plugin-data" / plugin_id / name

    prepare_assets(roles, tmp_path, Storage())
    assert sorted(migrated) == [
        ("pets-mira", roles.asset_path("assets/mira/pets")),
        ("pets-orphaned", roles.asset_path("assets/orphaned/pets")),
    ]
    assert roles.extensions.read("desktop_pet") == {}
