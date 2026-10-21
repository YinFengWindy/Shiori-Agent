"""Per-role drafts default off and never change another role's choice."""

import pytest

from plugins.natural_chat.backend.role_state import NaturalChatRoleState
from shiori_sdk.testing.roles import FakeRoles


def test_role_preferences_are_independent_and_pruned_after_deletion(tmp_path):
    roles = FakeRoles(tmp_path)
    roles.create_role(role_id="a", name="A", system_prompt="a")
    roles.create_role(role_id="b", name="B", system_prompt="b")
    state = NaturalChatRoleState(roles)
    assert not state.enabled("a")
    values = {}
    state.write_draft("a", {"enabled": True}, values)
    roles.extensions.values["natural_chat"] = values
    assert state.enabled("a") and not state.enabled("b")
    roles.values.pop("a")
    state.reconcile()
    assert roles.extensions.read("natural_chat") == {}
    assert not state.enabled("a")


@pytest.mark.parametrize("value", [None, 1, "false", []])
def test_invalid_draft_does_not_mutate_namespace(value):
    values = {"a": {"enabled": True}}
    with pytest.raises(ValueError):
        NaturalChatRoleState.write_draft("a", {"enabled": value}, values)
    assert values == {"a": {"enabled": True}}
