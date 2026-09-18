from __future__ import annotations

import asyncio
import tempfile
import threading
from pathlib import Path

import pytest
from shiori_plugin_testkit.packages import stage_plugin_package

from agent.plugin_host import HostServices, PluginKernel
from agent.tools.registry import ToolRegistry
from bus.event_bus import EventBus
from core.roles.store import RoleStore
from plugins.desktop_pet.backend.models import RolePetPackage
from plugins.desktop_pet.backend.pet_state import RolePetStateStore

PLUGIN_DIR = Path(__file__).resolve().parents[1]


def _load_desktop_pet_plugin(*, services: HostServices) -> PluginKernel:
    """Loads a fresh copy of the plugin package through the real v2 kernel.

    Same pattern as ``plugins/novelai/tests/test_plugin.py``: copying into a
    throwaway directory gives each test its own ``import_path``, so tests never
    collide through ``sys.modules`` caching.
    """
    with tempfile.TemporaryDirectory() as tmp:
        plugin_dir = Path(tmp) / "desktop_pet"
        stage_plugin_package(PLUGIN_DIR, plugin_dir)
        kernel = PluginKernel([Path(tmp)], services=services)
        asyncio.run(kernel.load_all())
        return kernel


def _services(tmp_path: Path, role_store: RoleStore | None = None) -> HostServices:
    # Match bootstrap: the host instance owns active draft participants, while
    # repositories for the same path also share the canonical persistence lock.
    return HostServices(
        event_bus=EventBus(),
        tool_registry=ToolRegistry(),
        workspace=tmp_path,
        role_store=role_store or RoleStore(tmp_path),
    )


def _bind_pet(
    workspace: Path,
    *,
    enabled: bool = True,
    with_file: bool = True,
    store: RoleStore | None = None,
) -> RoleStore:
    store = store or RoleStore(workspace)
    role = store.create_role(role_id="mira", name="Mira", system_prompt="test")
    spritesheet = "assets/mira/pets/pet-1/spritesheet.webp"
    RolePetStateStore(store).replace_packages(
        role.id,
        [
            RolePetPackage(
                id="pet-1",
                format="codex-sprite@1",
                display_name="Pet",
                manifest_path="assets/mira/pets/pet-1/pet.json",
                spritesheet_path=spritesheet,
                imported_at="2026-07-25T00:00:00+08:00",
                actions={"greeting": "waving"},
            )
        ],
    )
    RolePetStateStore(store).select_package(role.id, "pet-1")
    RolePetStateStore(store).set_enabled(role.id, enabled)
    if with_file:
        target = store.roles_dir / spritesheet
        target.parent.mkdir(parents=True, exist_ok=True)
        _ = target.write_bytes(b"not-a-real-webp")
    return store


def test_plugin_registers_tool_and_rpc_and_both_disappear_on_unload(
    tmp_path: Path,
) -> None:
    services = _services(tmp_path)
    kernel = _load_desktop_pet_plugin(services=services)

    assert services.tool_registry is not None
    assert services.tool_registry.has_tool("pet_action") is True
    assert kernel.rpc.resolve("plugin.desktop_pet.binding.get") is not None

    asyncio.run(kernel.unload("desktop_pet"))

    assert services.tool_registry.has_tool("pet_action") is False
    assert kernel.rpc.resolve("plugin.desktop_pet.binding.get") is None


def test_binding_get_returns_the_selected_package(tmp_path: Path) -> None:
    store = RoleStore(tmp_path)
    _bind_pet(tmp_path, store=store)
    kernel = _load_desktop_pet_plugin(services=_services(tmp_path, store))
    resolved = kernel.rpc.resolve("plugin.desktop_pet.binding.get")
    assert resolved is not None

    result = asyncio.run(resolved[1]({}))

    assert result is not None
    binding = result["binding"]
    assert binding is not None
    assert binding["role_id"] == "mira"
    assert binding["actions"] == {"greeting": "waving"}
    package = binding["package"]
    assert package["id"] == "pet-1"
    assert package["display_name"] == "Pet"
    # Absolute, and named `spritesheet_abs` so the desktop bridge grants it a
    # `shiori-asset://` URL on the way to the renderer.
    assert (
        Path(package["spritesheet_abs"])
        == (
            tmp_path / "plugin-data/desktop_pet/pets-mira/pet-1/spritesheet.webp"
        ).resolve()
    )

    assert Path(package["spritesheet_abs"]).read_bytes() == b"not-a-real-webp"


def test_binding_get_ignores_a_role_whose_pet_is_switched_off(tmp_path: Path) -> None:
    store = RoleStore(tmp_path)
    _bind_pet(tmp_path, enabled=False, store=store)
    kernel = _load_desktop_pet_plugin(services=_services(tmp_path, store))
    resolved = kernel.rpc.resolve("plugin.desktop_pet.binding.get")
    assert resolved is not None

    # A role keeps its package after the user switches the pet off; only
    # `desktop_pet_enabled` says whether to render it.
    assert asyncio.run(resolved[1]({})) == {"binding": None}


def test_binding_get_reports_nothing_when_the_spritesheet_is_missing(
    tmp_path: Path,
) -> None:
    store = RoleStore(tmp_path)
    _bind_pet(tmp_path, with_file=False, store=store)
    kernel = _load_desktop_pet_plugin(services=_services(tmp_path, store))
    resolved = kernel.rpc.resolve("plugin.desktop_pet.binding.get")
    assert resolved is not None

    assert asyncio.run(resolved[1]({})) == {"binding": None}


def test_binding_get_reports_nothing_when_no_role_has_a_pet(tmp_path: Path) -> None:
    store = RoleStore(tmp_path)
    _ = store.create_role(role_id="mira", name="Mira", system_prompt="test")
    kernel = _load_desktop_pet_plugin(services=_services(tmp_path, store))
    resolved = kernel.rpc.resolve("plugin.desktop_pet.binding.get")
    assert resolved is not None

    assert asyncio.run(resolved[1]({})) == {"binding": None}


def _resolve(kernel: PluginKernel, method: str):
    resolved = kernel.rpc.resolve(f"plugin.desktop_pet.{method}")
    assert resolved is not None, method
    return resolved[1]


def test_a_plugin_write_waits_on_the_host_role_lock(tmp_path: Path) -> None:
    """Plugin mutations participate in the canonical role persistence lock."""
    store = RoleStore(tmp_path)
    _bind_pet(tmp_path, store=store)
    kernel = _load_desktop_pet_plugin(services=_services(tmp_path, store))
    select = _resolve(kernel, "pets.select")
    finished = threading.Event()

    def run_plugin_write() -> None:
        asyncio.run(select({"role_id": "mira", "package_id": "pet-1"}))
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
    assert (
        finished.is_set()
    ), "the plugin write never completed after the lock was released"


def test_pets_list_returns_the_rows_roles_list_used_to_carry(tmp_path: Path) -> None:
    store = RoleStore(tmp_path)
    _bind_pet(tmp_path, store=store)
    kernel = _load_desktop_pet_plugin(services=_services(tmp_path, store))

    result = asyncio.run(_resolve(kernel, "pets.list")({"role_id": "mira"}))

    assert result is not None
    assert result["selected_package_id"] == "pet-1"
    package = result["packages"][0]
    assert package["id"] == "pet-1"
    assert package["display_name"] == "Pet"
    # The two names the desktop grants `shiori-asset://` URLs for; they are the
    # contract, so they must match what `role_presenter` emitted.
    assert Path(package["spritesheet_abs"]).is_absolute()
    assert package["preview_abs"] is None


def test_pets_select_and_remove_go_through_the_shared_store(tmp_path: Path) -> None:
    store = RoleStore(tmp_path)
    _bind_pet(tmp_path, store=store)
    kernel = _load_desktop_pet_plugin(services=_services(tmp_path, store))

    after_remove = asyncio.run(
        _resolve(kernel, "pets.remove")({"role_id": "mira", "package_id": "pet-1"})
    )

    assert after_remove == {"selected_package_id": None, "packages": []}
    # Written through the host's own store, so the host sees it without a reload.
    role = RolePetStateStore(store).require_role("mira")
    assert role.pet_packages == []
    # Removing the selected package also switches the pet off — that invariant
    # lives in `pet_state.replace_packages` and must survive the move.
    assert role.desktop_pet_enabled is False


def test_pet_rpc_requires_the_ids_it_acts_on(tmp_path: Path) -> None:
    store = RoleStore(tmp_path)
    _bind_pet(tmp_path, store=store)
    kernel = _load_desktop_pet_plugin(services=_services(tmp_path, store))

    for method, payload in [
        ("pets.list", {}),
        ("pets.import", {"role_id": "mira"}),
        ("pets.remove", {"role_id": "mira"}),
        ("pets.select", {"role_id": "mira"}),
        ("pets.select", {"package_id": "pet-1"}),
    ]:
        with pytest.raises((ValueError, KeyError)):
            asyncio.run(_resolve(kernel, method)(payload))


def test_every_pet_method_disappears_when_the_plugin_is_unloaded(
    tmp_path: Path,
) -> None:
    store = RoleStore(tmp_path)
    _bind_pet(tmp_path, store=store)
    kernel = _load_desktop_pet_plugin(services=_services(tmp_path, store))
    methods = ("binding.get", "pets.list", "pets.import", "pets.remove", "pets.select")
    for method in methods:
        assert kernel.rpc.resolve(f"plugin.desktop_pet.{method}") is not None, method

    asyncio.run(kernel.unload("desktop_pet"))

    for method in methods:
        assert kernel.rpc.resolve(f"plugin.desktop_pet.{method}") is None, method


def test_disabled_upgrade_then_ordinary_save_restores_binding_on_enable(tmp_path):
    import json

    store = RoleStore(tmp_path)
    _bind_pet(tmp_path, store=store)
    # Actual v3 disk shape: the plugin is not loaded during the upgrade/save.
    payload = json.loads(store.manifest_path.read_text(encoding="utf-8"))
    payload["version"] = 3
    legacy_state = payload.pop("plugin_data")["desktop_pet"]["mira"]
    payload["roles"][0].update(legacy_state)
    store.manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    store.update_role("mira", name="Edited while disabled")
    assert "pet_packages" not in store.get_role("mira").to_dict()
    kernel = _load_desktop_pet_plugin(services=_services(tmp_path, store))
    binding = asyncio.run(_resolve(kernel, "binding.get")({}))["binding"]
    assert binding["role_id"] == "mira"
    assert binding["package"]["id"] == "pet-1"
    asyncio.run(kernel.unload("desktop_pet"))


@pytest.mark.parametrize("migrated", [False, True])
def test_role_deleted_while_disabled_prunes_pet_data_and_whole_asset_root(
    tmp_path, migrated
):
    store = RoleStore(tmp_path)
    _bind_pet(tmp_path, store=store)
    pets = store.assets_dir / "mira" / "pets"
    if migrated:
        kernel = _load_desktop_pet_plugin(services=_services(tmp_path, store))
        asyncio.run(kernel.unload("desktop_pet"))
        pets = tmp_path / "plugin-data/desktop_pet/pets-mira"
    (pets / "orphan.tmp").write_text("interrupted import", encoding="utf-8")
    unrelated = store.assets_dir / "mira" / "avatar.png"
    unrelated.write_bytes(b"keep")
    store.delete_role("mira", remove_assets=False)
    kernel = _load_desktop_pet_plugin(services=_services(tmp_path, store))
    assert not pets.exists()
    assert unrelated.read_bytes() == b"keep"
    assert store.extensions.read("desktop_pet") == {}
    asyncio.run(kernel.unload("desktop_pet"))


def test_live_role_deleted_reconciles_and_unload_removes_draft_participant(tmp_path):
    from bus.events_lifecycle import RoleDeleted

    store = RoleStore(tmp_path)
    _bind_pet(tmp_path, store=store)
    services = _services(tmp_path, store)
    kernel = _load_desktop_pet_plugin(services=services)
    assert store.extensions.project("mira")["desktop_pet"] == {
        "enabled": True,
        "available": True,
    }
    store.delete_role("mira", remove_assets=False)
    asyncio.run(services.event_bus.observe(RoleDeleted("mira")))
    assert store.extensions.read("desktop_pet") == {}
    assert not (store.assets_dir / "mira" / "pets").exists()
    assert not (tmp_path / "plugin-data/desktop_pet/pets-mira").exists()
    asyncio.run(kernel.unload("desktop_pet"))
    assert store.extensions.project("mira") == {}


def test_prepared_plugin_runtime_keeps_role_settings_after_old_runtime_unloads(
    tmp_path,
):
    store = RoleStore(tmp_path)
    _bind_pet(tmp_path, store=store)
    old = _load_desktop_pet_plugin(services=_services(tmp_path, store))
    candidate = _load_desktop_pet_plugin(services=_services(tmp_path, store))
    # Assert actual candidate setup succeeded rather than only inspecting leases.
    assert candidate.rpc.resolve("plugin.desktop_pet.binding.get") is not None
    asyncio.run(old.unload("desktop_pet"))
    store.update_role("mira", plugin_drafts={"desktop_pet": {"enabled": False}})
    assert store.extensions.project("mira")["desktop_pet"]["enabled"] is False
    asyncio.run(candidate.unload("desktop_pet"))
    assert store.extensions.project("mira") == {}
