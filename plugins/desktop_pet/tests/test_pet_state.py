"""Pet membership and exclusive visibility are plugin-owned policies."""

import pytest
from shiori_sdk.testing.roles import FakeRoles
from plugins.desktop_pet.backend.models import RolePetPackage
from plugins.desktop_pet.backend.pet_state import RolePetStateStore


def test_enabling_one_role_replaces_visibility_and_missing_selection_rejects(tmp_path):
    roles = FakeRoles(tmp_path)
    state = RolePetStateStore(roles)
    for role_id in ("first", "second"):
        roles.create_role(role_id=role_id, name=role_id, system_prompt="test")
        state.replace_packages(
            role_id,
            [
                RolePetPackage(
                    "pet", "codex-sprite@1", "Pet", "pet.json", "pet.webp", "today"
                )
            ],
        )
        state.select_package(role_id, "pet")
        state.set_enabled(role_id, True)
    assert not state.require_role("first").desktop_pet_enabled
    assert state.require_role("second").desktop_pet_enabled
    state.replace_packages("second", [])
    assert not state.require_role("second").desktop_pet_enabled
    assert state.require_role("second").selected_pet_package_id is None
    with pytest.raises(ValueError, match="启用桌宠前"):
        state.set_enabled("second", True)
    with pytest.raises(KeyError, match="桌宠包不存在"):
        state.select_package("second", "missing")
