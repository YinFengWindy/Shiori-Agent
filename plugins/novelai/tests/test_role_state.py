"""NovelAI role preference policy works through opaque SDK role namespaces."""

import pytest
from shiori_sdk.testing.roles import FakeRoles
from plugins.novelai.backend.role_state import NovelAIRoleState


def test_reconcile_prunes_deleted_roles_without_touching_other_plugins(tmp_path):
    roles = FakeRoles(tmp_path)
    roles.create_role(role_id="live", name="Live", system_prompt="test")
    roles.extensions.values["novelai"] = {
        "live": {"auto_scene_cg_enabled": True},
        "deleted": {"auto_scene_cg_enabled": True},
    }
    roles.extensions.values["other"] = {"opaque": 42}
    state = NovelAIRoleState(roles)
    state.reconcile()
    assert state.enabled("live") and not state.enabled("deleted")
    assert roles.extensions.read("novelai") == {"live": {"auto_scene_cg_enabled": True}}
    assert roles.extensions.read("other") == {"opaque": 42}
    roles.create_role(role_id="deleted", name="Replacement", system_prompt="test")
    assert not state.enabled("deleted")


def test_reconcile_without_deleted_roles_does_not_write(tmp_path, monkeypatch):
    roles = FakeRoles(tmp_path)
    roles.create_role(role_id="live", name="Live", system_prompt="test")
    roles.extensions.values["novelai"] = {"live": {"auto_scene_cg_enabled": False}}

    def unexpected_write(*_args):
        raise AssertionError("reconcile must not rewrite live state")

    monkeypatch.setattr(roles.extensions, "update", unexpected_write)
    NovelAIRoleState(roles).reconcile()
    assert roles.extensions.read("novelai") == {
        "live": {"auto_scene_cg_enabled": False}
    }


def test_draft_rejects_non_boolean_without_touching_namespace():
    data: dict[str, object] = {"mira": {"auto_scene_cg_enabled": False}}
    with pytest.raises(ValueError, match="autoSceneCgEnabled"):
        NovelAIRoleState.write_draft("mira", {"autoSceneCgEnabled": "false"}, data)
    assert data == {"mira": {"auto_scene_cg_enabled": False}}


def test_draft_keeps_other_preferences_and_projection_defaults_off(tmp_path):
    data: dict[str, object] = {"mira": {"other": 1}}
    assert NovelAIRoleState.project("mira", data) == {"autoSceneCgEnabled": False}
    NovelAIRoleState.write_draft("mira", {"autoSceneCgEnabled": True}, data)
    assert data == {"mira": {"other": 1, "auto_scene_cg_enabled": True}}
    assert NovelAIRoleState.project("mira", data) == {"autoSceneCgEnabled": True}

    roles = FakeRoles(tmp_path)
    roles.create_role(role_id="mira", name="Mira", system_prompt="test")
    roles.extensions.values["novelai"] = data
    state = NovelAIRoleState(roles)
    assert state.enabled("mira")
    assert not state.enabled("missing")
