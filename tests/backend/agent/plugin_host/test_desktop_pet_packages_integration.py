from __future__ import annotations

import io
import json
import zipfile

from PIL import Image

from core.roles import RoleStore
from agent.plugin_host.roles import HostRoles
from agent.plugin_host.storage import PluginStorage
from plugins.desktop_pet.backend.pet_packages import RolePetPackageService
from plugins.desktop_pet.backend import package_images
from plugins.desktop_pet.backend.pet_state import RolePetStateStore
from plugins.desktop_pet.backend.reconcile import PetStateReconciler


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
    PetStateReconciler(HostRoles(roles), roles.workspace, PluginStorage()).reconcile()
    service = RolePetPackageService(HostRoles(roles), roles.workspace, PluginStorage())
    monkeypatch.setattr(package_images, "validate_atlas", lambda _: None)
    package = service.import_package(role.id, archive_path)
    service.select_package(role.id, package.id)
    RolePetStateStore(HostRoles(roles)).set_enabled(role.id, True)
    # Recreate a retained upgrade backup; its completed receipt must win.
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(b"retained backup")
    shutil.rmtree(roles.workspace / "plugin-data/desktop_pet")
    PetStateReconciler(HostRoles(roles), roles.workspace, PluginStorage()).reconcile()
    state = RolePetStateStore(HostRoles(roles)).require_role(role.id)
    assert state.pet_packages == []
    assert state.selected_pet_package_id is None
    assert not state.desktop_pet_enabled
    replacement = RolePetPackageService(
        HostRoles(roles), roles.workspace, PluginStorage()
    ).import_package(role.id, archive_path)
    assert replacement.id == package.id
    assert (roles.workspace / replacement.spritesheet_path).read_bytes() == b"new pet"
    PetStateReconciler(HostRoles(roles), roles.workspace, PluginStorage()).reconcile()
    assert unrelated.read_bytes() == b"role portrait"
    assert not (
        roles.workspace / "plugin-data/desktop_pet/pets-mira/abandoned"
    ).exists()


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
        return RolePetPackageService(
            HostRoles(store), store.workspace, PluginStorage()
        ).import_package("mira", tmp_path / f"{package_id}.zip")

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(install, store, package_id)
            for store, package_id in ((first, "first"), (second, "second"))
        ]
        imported = [future.result(timeout=10) for future in futures]
    state = RolePetStateStore(HostRoles(first)).require_role("mira")
    assert {package.id for package in state.pet_packages} == {"first", "second"}
    assert all(
        (first.workspace / package.spritesheet_path).is_file() for package in imported
    )
