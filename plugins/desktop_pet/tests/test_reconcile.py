"""Restart reconciliation repairs legacy visibility and retries orphan cleanup."""

import shutil

import pytest

from core.roles.store import RoleStore
from plugins.desktop_pet.backend.models import RolePetPackage
from plugins.desktop_pet.backend.pet_state import RolePetStateStore
from plugins.desktop_pet.backend.reconcile import PetStateReconciler


def test_reconcile_keeps_newest_enabled_role_and_retries_failed_asset_cleanup(
    tmp_path, monkeypatch
):
    roles = RoleStore(tmp_path)
    for role_id in ("older", "newer"):
        roles.create_role(role_id=role_id, name=role_id, system_prompt="test")
    payload = roles._load_payload()
    for role in payload["roles"]:
        role["updated_at"] = "2026-01-01" if role["id"] == "older" else "2026-01-02"
    roles._repository.save_payload(payload["roles"])

    def seed(data):
        for role_id in ("older", "newer"):
            package = RolePetPackage(
                "pet",
                "codex-sprite@1",
                "Pet",
                f"assets/{role_id}/pets/pet/pet.json",
                f"assets/{role_id}/pets/pet/spritesheet.webp",
                "today",
            )
            sprite = roles.roles_dir / package.spritesheet_path
            sprite.parent.mkdir(parents=True)
            sprite.write_bytes(b"pet")
            data[role_id] = {
                "pet_packages": [package.to_dict()],
                "selected_pet_package_id": "pet",
                "desktop_pet_enabled": True,
            }

    roles.extensions.update("desktop_pet", seed)
    orphan = roles.assets_dir / "deleted" / "pets"
    orphan.mkdir(parents=True)
    (orphan / "leftover.tmp").write_text("interrupted import", encoding="utf-8")
    reconcile = PetStateReconciler(roles)
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
