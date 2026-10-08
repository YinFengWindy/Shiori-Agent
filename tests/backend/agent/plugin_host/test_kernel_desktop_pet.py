"""desktop_pet loaded through the real kernel against host roles and storage.

Every test reaches the plugin only through public entry points: the staged
package loaded by ``PluginKernel``, its ``plugin.desktop_pet.*`` RPCs, the
registered tool, ``RoleDeleted`` events and the host ``RoleStore`` draft and
projection protocol. Pet business rules live in ``plugins/desktop_pet/tests``.
"""

from __future__ import annotations

import asyncio
import io
import json
import shutil
import tempfile
import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor
from functools import cache
from pathlib import Path
from typing import Any

import pytest
from PIL import Image
from shiori_sdk.role_events import RoleDeleted
from shiori_sdk.storage import plugin_data_dir
from shiori_sdk.testing.external_turns import FakeExternalTurns
from shiori_sdk.testing.packages import plugin_directory, stage_plugin_package

from agent.plugin_host import HostServices, PluginKernel
from agent.tools.registry import ToolRegistry
from bus.event_bus import EventBus
from core.roles.store import RoleStore
from session.manager import SessionManager

PLUGIN_ID = "desktop_pet"
PLUGIN_DIR = plugin_directory(PLUGIN_ID)
PET_METHODS = ("binding.get", "pets.list", "pets.import", "pets.remove", "pets.select")
# Where the desktop's native file picker stages selections for this plugin.
IMPORT_STAGING = Path("private_runtime/imports/desktop_pet-pets")


def _services(store: RoleStore) -> HostServices:
    return HostServices(
        event_bus=EventBus(),
        tool_registry=ToolRegistry(),
        workspace=store.workspace,
        role_store=store,
        session_manager=SessionManager(store.workspace),
        # The live engine declares external_turns; nothing here submits a turn.
        external_turns=FakeExternalTurns(),
    )


def _load(services: HostServices) -> PluginKernel:
    """Loads a fresh staged copy so every kernel owns its own plugin root.

    The copy lives under the test's workspace (a pytest ``tmp_path``), so it
    stays on disk for the kernel's whole lifetime, including later reloads.
    """
    assert services.workspace is not None
    staging = services.workspace / "staged-plugins"
    staging.mkdir(exist_ok=True)
    root = Path(tempfile.mkdtemp(dir=staging))
    stage_plugin_package(PLUGIN_DIR, root / PLUGIN_ID)
    kernel = PluginKernel([root], services=services)
    asyncio.run(kernel.load_all())
    return kernel


def _call(kernel: PluginKernel, method: str, payload: dict[str, Any]) -> Any:
    resolved = kernel.rpc.resolve(f"plugin.{PLUGIN_ID}.{method}")
    assert resolved is not None, method
    return asyncio.run(resolved[1](payload))


def _enable_draft(enabled: bool) -> dict[str, dict[str, bool]]:
    return {PLUGIN_ID: {"enabled": enabled}}


def _seed_legacy_pet(store: RoleStore, role_id: str = "mira", *, enabled=True):
    """Writes the pre-migration disk shape: pet bytes under shared role assets."""
    store.create_role(role_id=role_id, name=role_id, system_prompt="test")
    root = f"assets/{role_id}/pets/pet-1"
    spritesheet = store.assets_dir / role_id / "pets/pet-1/spritesheet.webp"
    spritesheet.parent.mkdir(parents=True)
    spritesheet.write_bytes(b"legacy pet")
    package = {
        "id": "pet-1",
        "format": "codex-sprite@1",
        "display_name": "Pet",
        "manifest_path": f"{root}/pet.json",
        "spritesheet_path": f"{root}/spritesheet.webp",
        "imported_at": "2026-07-25T00:00:00+08:00",
        "actions": {"greeting": "waving"},
    }
    state = {
        "pet_packages": [package],
        "selected_pet_package_id": "pet-1",
        "desktop_pet_enabled": enabled,
    }
    store.extensions.update(PLUGIN_ID, lambda data: data.update({role_id: state}))
    return spritesheet


@cache
def _atlas() -> bytes:
    """A real atlas with one nontransparent pixel in each required frame."""
    atlas = Image.new("RGBA", (1536, 1872))
    for row, count in enumerate((6, 8, 8, 4, 5, 8, 6, 6, 6)):
        for column in range(count):
            atlas.putpixel((column * 192, row * 208), (255, 0, 0, 255))
    buffer = io.BytesIO()
    atlas.save(buffer, format="WEBP", lossless=True)
    return buffer.getvalue()


def _stage_package(workspace: Path, package_id: str) -> Path:
    archive_path = workspace / IMPORT_STAGING / f"{package_id}.zip"
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "id": package_id,
        "displayName": package_id,
        "description": "fixture",
        "spritesheetPath": "spritesheet.webp",
    }
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("pet.json", json.dumps(manifest))
        archive.writestr("spritesheet.webp", _atlas())
    return archive_path


def _import(kernel: PluginKernel, role_id: str, archive: Path) -> dict[str, Any]:
    payload = {"role_id": role_id, "source": str(archive)}
    return _call(kernel, "pets.import", payload)["package"]


def _pets_root(package: dict[str, Any]) -> Path:
    """One role's private pet directory, derived from the RPC's absolute path."""
    return Path(package["spritesheet_abs"]).parents[1]


def test_tool_and_every_pet_method_disappear_on_unload(tmp_path: Path) -> None:
    store = RoleStore(tmp_path)
    _seed_legacy_pet(store)
    services = _services(store)
    kernel = _load(services)
    assert services.tool_registry is not None
    assert services.tool_registry.has_tool("pet_action") is True
    for method in PET_METHODS:
        assert kernel.rpc.resolve(f"plugin.{PLUGIN_ID}.{method}") is not None, method

    asyncio.run(kernel.unload(PLUGIN_ID))

    assert services.tool_registry.has_tool("pet_action") is False
    for method in PET_METHODS:
        assert kernel.rpc.resolve(f"plugin.{PLUGIN_ID}.{method}") is None, method


def test_a_plugin_write_waits_on_the_host_role_lock(tmp_path: Path) -> None:
    """Plugin mutations participate in the canonical role persistence lock."""
    store = RoleStore(tmp_path)
    _seed_legacy_pet(store)
    kernel = _load(_services(store))
    finished = threading.Event()

    def run_plugin_write() -> None:
        _call(kernel, "pets.select", {"role_id": "mira", "package_id": "pet-1"})
        finished.set()

    # Held from *this* thread: `RLock` is reentrant per thread, so the worker
    # below only blocks if it is genuinely the same lock object.
    with store.lock:
        worker = threading.Thread(target=run_plugin_write, daemon=True)
        worker.start()
        assert not finished.wait(timeout=0.3), (
            "the plugin wrote roles.json without waiting for the host's lock; "
            "it is holding its own RoleStore instance"
        )

    worker.join(timeout=5)
    assert finished.is_set(), "the plugin write never completed after the lock"
    asyncio.run(kernel.unload(PLUGIN_ID))


def test_disabled_upgrade_then_ordinary_save_restores_binding_on_enable(tmp_path):
    store = RoleStore(tmp_path)
    _seed_legacy_pet(store)
    # Actual v3 disk shape: the plugin is not loaded during the upgrade/save.
    payload = json.loads(store.manifest_path.read_text(encoding="utf-8"))
    payload["version"] = 3
    legacy_state = payload.pop("plugin_data")[PLUGIN_ID]["mira"]
    payload["roles"][0].update(legacy_state)
    store.manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    store.update_role("mira", name="Edited while disabled")
    assert "pet_packages" not in store.get_role("mira").to_dict()
    kernel = _load(_services(store))
    binding = _call(kernel, "binding.get", {})["binding"]
    assert binding["role_id"] == "mira"
    assert binding["package"]["id"] == "pet-1"
    asyncio.run(kernel.unload(PLUGIN_ID))


@pytest.mark.parametrize("migrated", [False, True])
def test_role_deleted_while_disabled_prunes_pet_data_and_whole_asset_root(
    tmp_path, migrated
):
    store = RoleStore(tmp_path)
    pets = _seed_legacy_pet(store).parents[1]
    if migrated:
        kernel = _load(_services(store))
        package = _call(kernel, "pets.list", {"role_id": "mira"})["packages"][0]
        pets = _pets_root(package)
        asyncio.run(kernel.unload(PLUGIN_ID))
    (pets / "orphan.tmp").write_text("interrupted import", encoding="utf-8")
    unrelated = store.assets_dir / "mira" / "avatar.png"
    unrelated.write_bytes(b"keep")
    store.delete_role("mira", remove_assets=False)
    kernel = _load(_services(store))
    assert not pets.exists()
    assert unrelated.read_bytes() == b"keep"
    assert store.extensions.read(PLUGIN_ID) == {}
    asyncio.run(kernel.unload(PLUGIN_ID))


def test_live_role_deleted_reconciles_and_unload_removes_draft_participant(tmp_path):
    store = RoleStore(tmp_path)
    legacy_pets = _seed_legacy_pet(store).parents[1]
    services = _services(store)
    kernel = _load(services)
    package = _call(kernel, "pets.list", {"role_id": "mira"})["packages"][0]
    assert store.extensions.project("mira")[PLUGIN_ID] == {
        "enabled": True,
        "available": True,
    }
    store.delete_role("mira", remove_assets=False)
    asyncio.run(services.event_bus.observe(RoleDeleted("mira")))
    assert store.extensions.read(PLUGIN_ID) == {}
    assert not legacy_pets.exists()
    assert not _pets_root(package).exists()
    asyncio.run(kernel.unload(PLUGIN_ID))
    assert store.extensions.project("mira") == {}


def test_prepared_plugin_runtime_keeps_role_settings_after_old_runtime_unloads(
    tmp_path,
):
    store = RoleStore(tmp_path)
    _seed_legacy_pet(store)
    old = _load(_services(store))
    candidate = _load(_services(store))
    # Assert actual candidate setup succeeded rather than only inspecting leases.
    assert candidate.rpc.resolve(f"plugin.{PLUGIN_ID}.binding.get") is not None
    asyncio.run(old.unload(PLUGIN_ID))
    store.update_role("mira", plugin_drafts=_enable_draft(False))
    assert store.extensions.project("mira")[PLUGIN_ID]["enabled"] is False
    asyncio.run(candidate.unload(PLUGIN_ID))
    assert store.extensions.project("mira") == {}


def test_role_save_drafts_enable_one_role_and_keep_core_save_atomic(tmp_path):
    store = RoleStore(tmp_path)
    for role_id in ("first", "second"):
        _seed_legacy_pet(store, role_id, enabled=False)
    kernel = _load(_services(store))
    store.update_role("first", plugin_drafts=_enable_draft(True))
    store.update_role(
        "second", name="Saved together", plugin_drafts=_enable_draft(True)
    )
    assert store.extensions.project("first")[PLUGIN_ID]["enabled"] is False
    assert store.extensions.project("second")[PLUGIN_ID]["enabled"] is True
    assert store.get_role("second").name == "Saved together"
    _call(kernel, "pets.remove", {"role_id": "second", "package_id": "pet-1"})
    assert store.extensions.project("second")[PLUGIN_ID] == {
        "enabled": False,
        "available": False,
    }
    with pytest.raises(ValueError, match="启用桌宠前"):
        store.update_role("second", name="Rejected", plugin_drafts=_enable_draft(True))
    assert store.get_role("second").name == "Saved together"
    with pytest.raises(KeyError, match="桌宠包不存在"):
        _call(kernel, "pets.select", {"role_id": "second", "package_id": "absent"})
    asyncio.run(kernel.unload(PLUGIN_ID))


def test_independent_store_instances_serialize_drafts_on_the_same_path(tmp_path):
    first_store = RoleStore(tmp_path)
    _seed_legacy_pet(first_store, "first", enabled=False)
    second_store = RoleStore(tmp_path / ".")
    _seed_legacy_pet(second_store, "second", enabled=False)
    kernels = [_load(_services(store)) for store in (first_store, second_store)]
    started = threading.Event()
    finished = threading.Event()

    def write_second():
        started.set()
        second_store.update_role("second", plugin_drafts=_enable_draft(True))
        finished.set()

    with ThreadPoolExecutor(max_workers=1) as pool:
        with first_store.lock:
            future = pool.submit(write_second)
            assert started.wait(2)
            assert not finished.wait(0.1)
            first_store.update_role("first", plugin_drafts=_enable_draft(True))
        future.result(timeout=3)
    # The second save ran after the first, so its exclusive enable won.
    assert first_store.extensions.project("first")[PLUGIN_ID]["enabled"] is False
    assert first_store.extensions.project("second")[PLUGIN_ID]["enabled"] is True
    for kernel in kernels:
        asyncio.run(kernel.unload(PLUGIN_ID))


def test_concurrent_imports_through_two_store_instances_keep_both(tmp_path):
    first = RoleStore(tmp_path)
    first.create_role(role_id="mira", name="Mira", system_prompt="test")
    second = RoleStore(tmp_path)
    kernels = [_load(_services(store)) for store in (first, second)]
    barrier = threading.Barrier(2)

    def install(kernel, package_id):
        archive = _stage_package(tmp_path, package_id)
        barrier.wait(timeout=3)
        return _import(kernel, "mira", archive)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(install, kernel, package_id)
            for kernel, package_id in zip(kernels, ("first", "second"))
        ]
        imported = [future.result(timeout=10) for future in futures]
    listed = _call(kernels[0], "pets.list", {"role_id": "mira"})["packages"]
    assert {package["id"] for package in listed} == {"first", "second"}
    assert all(Path(package["spritesheet_abs"]).is_file() for package in imported)
    for kernel in kernels:
        asyncio.run(kernel.unload(PLUGIN_ID))


def test_failed_metadata_publish_preserves_source_and_retry_completes(
    tmp_path, monkeypatch
):
    store = RoleStore(tmp_path)
    source = _seed_legacy_pet(store)
    before = store.manifest_path.read_bytes()
    replace = Path.replace

    def fail(path, target):
        if target == store.manifest_path:
            raise OSError("manifest locked")
        return replace(path, target)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "replace", fail)
        failed = _load(_services(store))
    [state] = failed.states()
    assert state["state"] == "FAILED"
    assert "manifest locked" in state["error"]
    assert source.read_bytes() == b"legacy pet"
    assert store.manifest_path.read_bytes() == before
    kernel = _load(_services(store))
    package = _call(kernel, "pets.list", {"role_id": "mira"})["packages"][0]
    migrated = Path(package["spritesheet_abs"])
    assert migrated.is_relative_to(plugin_data_dir(tmp_path, PLUGIN_ID).resolve())
    assert migrated.read_bytes() == b"legacy pet"
    asyncio.run(kernel.unload(PLUGIN_ID))


def test_cleared_plugin_data_can_reimport_same_package_without_reviving_backup(
    tmp_path,
):
    store = RoleStore(tmp_path)
    store.create_role(role_id="mira", name="Mira", system_prompt="test")
    legacy = store.assets_dir / "mira/pets/abandoned/spritesheet.webp"
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(b"old interrupted import")
    unrelated = store.assets_dir / "mira/portrait.png"
    unrelated.write_bytes(b"role portrait")
    kernel = _load(_services(store))
    package = _import(kernel, "mira", _stage_package(tmp_path, "pet"))
    _call(kernel, "pets.select", {"role_id": "mira", "package_id": package["id"]})
    store.update_role("mira", plugin_drafts=_enable_draft(True))
    asyncio.run(kernel.unload(PLUGIN_ID))
    # Recreate a retained upgrade backup; its completed receipt must win.
    legacy.parent.mkdir(parents=True)
    legacy.write_bytes(b"retained backup")
    shutil.rmtree(plugin_data_dir(tmp_path, PLUGIN_ID))

    kernel = _load(_services(store))
    assert _call(kernel, "pets.list", {"role_id": "mira"}) == {
        "selected_package_id": None,
        "packages": [],
    }
    assert store.extensions.project("mira")[PLUGIN_ID]["enabled"] is False
    replacement = _import(kernel, "mira", _stage_package(tmp_path, "pet"))
    assert replacement["id"] == package["id"]
    assert Path(replacement["spritesheet_abs"]).read_bytes() == _atlas()
    asyncio.run(kernel.unload(PLUGIN_ID))

    kernel = _load(_services(store))
    listed = _call(kernel, "pets.list", {"role_id": "mira"})["packages"]
    assert [item["id"] for item in listed] == [package["id"]]
    assert unrelated.read_bytes() == b"role portrait"
    assert not (_pets_root(replacement) / "abandoned").exists()
    asyncio.run(kernel.unload(PLUGIN_ID))


def test_legacy_unregistered_assets_never_clobber_a_later_import(tmp_path):
    store = RoleStore(tmp_path)
    store.create_role(role_id="mira", name="Mira", system_prompt="test")
    orphan = store.assets_dir / "mira/pets/orphan/spritesheet.webp"
    orphan.parent.mkdir(parents=True)
    orphan.write_bytes(b"interrupted import")
    kernel = _load(_services(store))
    package = _import(kernel, "mira", _stage_package(tmp_path, "new-pet"))
    asyncio.run(kernel.unload(PLUGIN_ID))

    kernel = _load(_services(store))
    listed = _call(kernel, "pets.list", {"role_id": "mira"})["packages"]
    assert [item["id"] for item in listed] == ["new-pet"]
    assert Path(package["spritesheet_abs"]).read_bytes() == _atlas()
    assert not orphan.exists()
    assert not (_pets_root(package) / "orphan").exists()
    asyncio.run(kernel.unload(PLUGIN_ID))
