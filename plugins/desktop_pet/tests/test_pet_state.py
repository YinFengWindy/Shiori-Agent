"""Exclusive visibility and selection are independent of model formats."""

import pytest
from shiori_sdk.testing.roles import FakeRoles
from plugins.desktop_pet.backend.pet_state import RolePetStateStore

REFERENCE = {
    "provider": {"plugin_id": "test_provider", "service_id": "models"},
    "model_id": "model",
}


def test_selecting_inactive_role_never_enables_it_and_enable_is_exclusive(tmp_path):
    roles = FakeRoles(tmp_path)
    state = RolePetStateStore(roles)
    for role_id in ("first", "second"):
        roles.create_role(role_id=role_id, name=role_id, system_prompt="test")
        state.select_model(role_id, REFERENCE)
        assert not state.is_enabled(role_id)
        state.set_enabled(role_id, True)
    assert not state.is_enabled("first")
    assert state.is_enabled("second")
    state.select_model("second", None)
    assert not state.is_enabled("second")
    with pytest.raises(ValueError, match="启用桌宠前"):
        state.set_enabled("second", True)


def test_role_save_preserves_pending_legacy_migration_data():
    old = {
        "pet_packages": [{"id": "pet"}],
        "selected_pet_package_id": "pet",
        "desktop_pet_enabled": True,
    }
    data = {"first": dict(old), "second": {"selected_model": REFERENCE}}
    RolePetStateStore.write_draft("second", {"enabled": True}, data)
    assert data["first"]["pet_packages"] == old["pet_packages"]
    assert not data["first"]["desktop_pet_enabled"]
    assert RolePetStateStore.project("second", data) == {
        "enabled": True,
        "available": True,
    }
    with pytest.raises(ValueError, match="布尔值"):
        RolePetStateStore.write_draft("second", {"enabled": "yes"}, data)
