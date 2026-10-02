"""NovelAI role preference policy works through opaque SDK role namespaces."""

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
