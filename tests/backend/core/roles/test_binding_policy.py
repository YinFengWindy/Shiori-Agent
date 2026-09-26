from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.common.channel_chat_types import ChatTypeDeclaration
from core.roles.binding_policy import RoleBindingPolicy
from core.roles.models import (
    RoleChannelBindingConfig,
    RoleProactiveCandidate,
    RoleProactiveConfig,
)


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


_DESKTOP = RoleChannelBindingConfig("desktop", "role:mira", "private")
_QQ_PRIVATE = RoleChannelBindingConfig("qq", "10001", "private")
_QQ_GROUP = RoleChannelBindingConfig("qq", "gqq:7", "group")


def test_proactive_candidates_are_stored_in_binding_order() -> None:
    normalized = RoleBindingPolicy.normalize_proactive(
        {
            "enabled": True,
            "candidates": [
                {"channel": "qq", "chat_id": "gqq:7"},
                {"channel": "desktop", "chat_id": "role:mira"},
            ],
        },
        [_DESKTOP, _QQ_PRIVATE, _QQ_GROUP],
    )

    assert normalized.candidates == (
        RoleProactiveCandidate("desktop", "role:mira"),
        RoleProactiveCandidate("qq", "gqq:7"),
    )


def test_proactive_candidate_must_be_a_bound_session() -> None:
    # A bare QQ number is a private chat, not the bound gqq: group.
    with pytest.raises(ValueError, match="已绑定的会话: qq:7"):
        RoleBindingPolicy.normalize_proactive(
            {"enabled": True, "candidates": [{"channel": "qq", "chat_id": "7"}]},
            [_QQ_GROUP],
        )


def test_enabling_proactive_without_legacy_candidate_keeps_setting() -> None:
    enabled = RoleBindingPolicy.normalize_proactive(
        {"enabled": True, "candidates": []}, [_DESKTOP]
    )
    assert enabled.enabled is True
    assert enabled.candidates == ()
    disabled = RoleBindingPolicy.normalize_proactive(
        {"enabled": False, "candidates": []}, [_DESKTOP]
    )
    assert disabled.candidates == ()


def test_removed_binding_leaves_candidates_and_preserves_enabled_setting() -> None:
    proactive = RoleProactiveConfig(
        enabled=True,
        candidates=(
            RoleProactiveCandidate("qq", "gqq:7"),
            RoleProactiveCandidate("desktop", "role:mira"),
        ),
    )

    kept = RoleBindingPolicy.prune_proactive_candidates(proactive, [_DESKTOP])
    emptied = RoleBindingPolicy.prune_proactive_candidates(proactive, [_QQ_PRIVATE])

    assert kept.enabled is True
    assert kept.candidates == (RoleProactiveCandidate("desktop", "role:mira"),)
    assert emptied.enabled is True
    assert emptied.candidates == ()


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
