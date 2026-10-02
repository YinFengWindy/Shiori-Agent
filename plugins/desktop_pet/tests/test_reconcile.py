"""Plugin reconciliation clears unavailable packages and orphan private assets."""

import shutil
import pytest
from shiori_sdk.testing.roles import FakeRoles
from shiori_sdk.testing.memory import FakeMemoryStorage
from plugins.desktop_pet.backend.models import RolePetPackage
from plugins.desktop_pet.backend.pet_state import RolePetStateStore
from plugins.desktop_pet.backend.reconcile import PetStateReconciler


def test_reconcile_clears_missing_packages_and_deleted_roles(tmp_path):
    roles = FakeRoles(tmp_path)
    roles.create_role(role_id="mira", name="Mira", system_prompt="test")
    state = RolePetStateStore(roles)
    state.replace_packages(
        "mira",
        [
            RolePetPackage(
                "pet",
                "codex-sprite@1",
                "Pet",
                "plugin-data/desktop_pet/pets-mira/pet.json",
                "plugin-data/desktop_pet/pets-mira/sprite.webp",
                "today",
            )
        ],
    )
    state.select_package("mira", "pet")
    state.set_enabled("mira", True)
    orphan = tmp_path / "plugin-data/desktop_pet/pets-deleted"
    orphan.mkdir(parents=True)
    roles.extensions.values["desktop_pet"]["deleted"] = {}
    reconciler = PetStateReconciler(roles, tmp_path, FakeMemoryStorage())
    reconciler.reconcile()
    assert not orphan.exists()
    assert "deleted" not in roles.extensions.read("desktop_pet")
    assert not state.require_role("mira").desktop_pet_enabled
    assert not state.require_role("mira").pet_packages


def test_reconcile_keeps_newest_enabled_role_and_retries_failed_asset_cleanup(
    tmp_path, monkeypatch
):
    roles = FakeRoles(tmp_path)
    for role_id in ("newer", "older"):
        roles.create_role(role_id=role_id, name=role_id, system_prompt="test")

    def seed(data):
        for role_id in ("newer", "older"):
            package = RolePetPackage(
                "pet",
                "codex-sprite@1",
                "Pet",
                f"plugin-data/desktop_pet/pets-{role_id}/pet/pet.json",
                f"plugin-data/desktop_pet/pets-{role_id}/pet/spritesheet.webp",
                "today",
            )
            sprite = tmp_path / package.spritesheet_path
            sprite.parent.mkdir(parents=True)
            sprite.write_bytes(b"pet")
            data[role_id] = {
                "pet_packages": [package.to_dict()],
                "selected_pet_package_id": "pet",
                "desktop_pet_enabled": True,
            }

    roles.extensions.update("desktop_pet", seed)
    orphan = tmp_path / "plugin-data/desktop_pet/pets-deleted"
    orphan.mkdir(parents=True)
    (orphan / "leftover.tmp").write_text("interrupted import", encoding="utf-8")
    reconcile = PetStateReconciler(roles, tmp_path, FakeMemoryStorage())
    with monkeypatch.context() as patch:

        def fail(_path):
            raise OSError("asset locked")

        patch.setattr(shutil, "rmtree", fail)
        with pytest.raises(OSError, match="asset locked"):
            reconcile.reconcile()
    assert orphan.exists()
    reconcile.reconcile()
    assert not orphan.exists()
    state = RolePetStateStore(roles)
    assert state.require_role("newer").desktop_pet_enabled is True
    assert state.require_role("older").desktop_pet_enabled is False
    before = roles.extensions.read("desktop_pet")
    reconcile.reconcile()
    assert roles.extensions.read("desktop_pet") == before
