"""Plugin-owned membership, visibility and concurrent instance regressions."""

from concurrent.futures import ThreadPoolExecutor
import threading

import pytest

from core.roles.store import RoleStore
from agent.plugin_host.roles import HostRoles
from plugins.desktop_pet.backend.models import RolePetPackage
from plugins.desktop_pet.backend.pet_state import RolePetStateStore


def _bound(store, role_id):
    store.create_role(role_id=role_id, name=role_id, system_prompt="test")
    state = RolePetStateStore(HostRoles(store))
    state.replace_packages(
        role_id,
        [
            RolePetPackage(
                "pet",
                "codex-sprite@1",
                "Pet",
                f"assets/{role_id}/pets/pet/pet.json",
                f"assets/{role_id}/pets/pet/spritesheet.webp",
                "today",
            )
        ],
    )
    state.select_package(role_id, "pet")
    return state


def test_role_draft_enables_one_role_and_preserves_core_save_semantics(tmp_path):
    store = RoleStore(tmp_path)
    state = _bound(store, "first")
    _bound(store, "second")
    store.extensions.register("desktop_pet", state.write_draft, state.project)
    store.update_role("first", plugin_drafts={"desktop_pet": {"enabled": True}})
    store.update_role(
        "second",
        name="Saved together",
        plugin_drafts={"desktop_pet": {"enabled": True}},
    )
    assert state.require_role("first").desktop_pet_enabled is False
    assert state.require_role("second").desktop_pet_enabled is True
    assert store.get_role("second").name == "Saved together"
    state.replace_packages("second", [])
    assert state.require_role("second").desktop_pet_enabled is False
    assert state.require_role("second").selected_pet_package_id is None
    with pytest.raises(ValueError, match="启用桌宠前"):
        store.update_role(
            "second", name="Rejected", plugin_drafts={"desktop_pet": {"enabled": True}}
        )
    assert store.get_role("second").name == "Saved together"
    with pytest.raises(KeyError, match="桌宠包不存在"):
        state.select_package("second", "absent")


def test_independent_store_instances_serialize_updates_on_the_same_path(tmp_path):
    first_store = RoleStore(tmp_path)
    first = _bound(first_store, "first")
    second_store = RoleStore(tmp_path / ".")
    second = _bound(second_store, "second")
    started = threading.Event()
    finished = threading.Event()

    def write_second():
        started.set()
        second.set_enabled("second", True)
        finished.set()

    with ThreadPoolExecutor(max_workers=1) as pool:
        with first_store.lock:
            future = pool.submit(write_second)
            assert started.wait(2)
            assert not finished.wait(0.1)
            first.set_enabled("first", True)
        future.result(timeout=3)
    assert first.require_role("first").desktop_pet_enabled is False
    assert second.require_role("second").desktop_pet_enabled is True
