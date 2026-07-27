from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.roles.binding_policy import RoleBindingPolicy
from core.roles.models import RoleChannelBindingConfig, RoleProactiveConfig


def test_binding_policy_rejects_external_channel_without_single_contact() -> None:
    policy = RoleBindingPolicy()

    with pytest.raises(ValueError, match="仅绑定一个联系人"):
        policy.normalize(
            [
                RoleChannelBindingConfig(
                    channel="qq",
                    chat_id="10001",
                    allow_from=[],
                )
            ]
        )


def test_binding_policy_rejects_channel_owned_by_another_role() -> None:
    policy = RoleBindingPolicy()
    existing = RoleChannelBindingConfig(
        channel="telegram",
        chat_id="chat-1",
        allow_from=["user-1"],
    )
    roles = [SimpleNamespace(id="role-a", channel_bindings=[existing])]

    with pytest.raises(ValueError, match="已绑定其他角色"):
        policy.normalize_for_role(roles, "role-b", [existing])


def test_binding_policy_disables_removed_proactive_target() -> None:
    proactive = RoleProactiveConfig(
        enabled=True,
        target_channel="telegram",
        target_chat_id="chat-1",
    )

    normalized = RoleBindingPolicy.disable_missing_proactive_target(proactive, [])

    assert normalized.enabled is False
    assert normalized.target_channel == ""
    assert normalized.target_chat_id == ""
