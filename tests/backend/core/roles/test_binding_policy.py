from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.common.channel_chat_types import ChatTypeDeclaration
from core.roles.binding_policy import RoleBindingPolicy
from core.roles.models import RoleChannelBindingConfig, RoleProactiveConfig


def test_binding_policy_accepts_external_bindings_without_any_contact() -> None:
    # A private chat's partner is the chat itself; a group admits every member
    # not blacklisted (#398).
    bindings = [
        RoleChannelBindingConfig("qq", "10001", "private"),
        RoleChannelBindingConfig("qq", "gqq:7", "group"),
        RoleChannelBindingConfig("qq", "gqq:8", "group", ["42"]),
    ]

    assert RoleBindingPolicy().normalize(bindings) == bindings


def test_binding_policy_rejects_blacklist_on_private_binding_payload() -> None:
    with pytest.raises(ValueError, match="只有群聊绑定可以设置黑名单"):
        RoleBindingPolicy().normalize(
            [
                {
                    "channel": "qq",
                    "chat_id": "10001",
                    "chat_type": "private",
                    "blocked_senders": ["42"],
                }
            ]
        )


def test_binding_policy_rejects_channel_owned_by_another_role() -> None:
    policy = RoleBindingPolicy()
    existing = RoleChannelBindingConfig(
        channel="telegram",
        chat_id="chat-1",
        chat_type="private",
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


_QQ_TYPES = {
    "qq": (
        ChatTypeDeclaration("private", "私聊", "QQ 号"),
        ChatTypeDeclaration("group", "群聊", "群号", prefix="gqq:"),
    ),
    "qqbot": (ChatTypeDeclaration("private", "私聊", "用户 OpenID", prefix="c2c:"),),
}


def _declared_policy() -> RoleBindingPolicy:
    policy = RoleBindingPolicy()
    policy.bind_chat_types(_QQ_TYPES)
    return policy


def test_binding_policy_accepts_chat_ids_matching_their_declared_type() -> None:
    bindings = [
        RoleChannelBindingConfig("qq", "831907794", "private"),
        RoleChannelBindingConfig("qq", "gqq:831907794", "group", ["3174898512"]),
        RoleChannelBindingConfig("qqbot", "c2c:u1", "private"),
    ]

    assert _declared_policy().normalize(bindings) == bindings


@pytest.mark.parametrize(
    "binding, message",
    [
        # Group type without its prefix: QQ would send it as a private chat.
        (RoleChannelBindingConfig("qq", "831907794", "group"), "gqq:<群号>"),
        (RoleChannelBindingConfig("qq", "gqq:", "group"), "gqq:<群号>"),
        # Private type carrying the group prefix names the other type.
        (RoleChannelBindingConfig("qq", "gqq:831907794", "private"), "群聊格式"),
        (
            RoleChannelBindingConfig("qqbot", "u1", "private"),
            "c2c:<用户 OpenID>",
        ),
        # qqbot declares no group chats.
        (RoleChannelBindingConfig("qqbot", "c2c:u1", "group"), "可选：私聊"),
    ],
)
def test_binding_policy_rejects_chat_id_inconsistent_with_its_type(
    binding: RoleChannelBindingConfig, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        _declared_policy().normalize([binding])


def test_binding_policy_rejects_new_binding_on_channel_no_plugin_declares() -> None:
    binding = RoleChannelBindingConfig("gone", "room-1", "group")

    with pytest.raises(ValueError, match="没有已安装的插件"):
        _declared_policy().normalize([binding])


def test_binding_policy_keeps_unchanged_binding_of_an_uninstalled_plugin() -> None:
    # The desktop resends read-only bindings of uninstalled plugins on every save.
    saved = RoleChannelBindingConfig("gone", "room-1", "group")
    edited = RoleChannelBindingConfig("gone", "room-2", "group")
    roles = [SimpleNamespace(id="mira", channel_bindings=[saved])]
    policy = _declared_policy()

    assert policy.normalize_for_role(roles, "mira", [saved]) == [saved]
    with pytest.raises(ValueError, match="没有已安装的插件"):
        policy.normalize_for_role(roles, "mira", [edited])


def test_binding_policy_requires_private_desktop_session() -> None:
    desktop = RoleChannelBindingConfig("desktop", "role:mira", "group")

    with pytest.raises(ValueError, match="私聊"):
        RoleBindingPolicy().normalize_for_role([], "mira", [desktop])
