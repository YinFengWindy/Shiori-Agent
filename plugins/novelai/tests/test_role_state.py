"""CG drafts share the role commit and survive plugin disablement."""

from pathlib import Path

import pytest

from core.roles.store import RoleStore
from plugins.novelai.backend.role_state import NovelAIRoleState


def test_cg_draft_is_atomic_with_role_save_and_preserved_when_disabled(
    tmp_path, monkeypatch
):
    roles = RoleStore(tmp_path)
    roles.create_role(role_id="mira", name="Before", system_prompt="test")
    state = NovelAIRoleState(roles)
    dispose = roles.extensions.register("novelai", state.write_draft, state.project)
    assert not state.enabled("mira")
    before = roles.manifest_path.read_bytes()
    original_replace = Path.replace

    def fail(path, target):
        if target == roles.manifest_path:
            raise OSError("disk unavailable")
        return original_replace(path, target)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "replace", fail)
        with pytest.raises(OSError, match="disk unavailable"):
            roles.update_role(
                "mira",
                name="After",
                plugin_drafts={"novelai": {"autoSceneCgEnabled": True}},
            )
    assert roles.manifest_path.read_bytes() == before
    assert not state.enabled("mira")
    roles.update_role(
        "mira", name="After", plugin_drafts={"novelai": {"autoSceneCgEnabled": True}}
    )
    assert state.enabled("mira")
    role = roles.get_role("mira")
    assert role is not None and role.name == "After"
    assert "auto_scene_cg_enabled" not in role.runtime_config
    dispose()
    roles.update_role("mira", description="Edited while disabled")
    assert state.enabled("mira")
    assert not state.enabled("missing")


def test_invalid_cg_draft_cannot_commit_other_role_edits(tmp_path):
    roles = RoleStore(tmp_path)
    roles.create_role(role_id="mira", name="Before", system_prompt="test")
    roles.extensions.register(
        "novelai", NovelAIRoleState.write_draft, NovelAIRoleState.project
    )
    before = roles.manifest_path.read_bytes()
    with pytest.raises(ValueError, match="autoSceneCgEnabled"):
        roles.update_role(
            "mira",
            name="Rejected",
            plugin_drafts={"novelai": {"autoSceneCgEnabled": "false"}},
        )
    assert roles.manifest_path.read_bytes() == before


def test_reconcile_prunes_only_deleted_roles_and_does_not_rewrite_live_state(tmp_path):
    roles = RoleStore(tmp_path)
    for role_id in ("gone", "live"):
        roles.create_role(role_id=role_id, name=role_id, system_prompt="test")
    roles.extensions.update(
        "novelai",
        lambda data: data.update(
            {
                "gone": {"auto_scene_cg_enabled": True},
                "live": {"auto_scene_cg_enabled": False},
            }
        ),
    )
    roles.extensions.update("other", lambda data: data.update({"opaque": 42}))
    roles.delete_role("gone")
    state = NovelAIRoleState(roles)
    state.reconcile()
    assert roles.extensions.read("novelai") == {
        "live": {"auto_scene_cg_enabled": False}
    }
    assert roles.extensions.read("other") == {"opaque": 42}
    before = roles.manifest_path.read_bytes()
    state.reconcile()
    assert roles.manifest_path.read_bytes() == before
    roles.create_role(role_id="gone", name="Replacement", system_prompt="test")
    assert not state.enabled("gone")
