from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.common.channel_chat_types import ChatTypeDeclaration
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
                    chat_type="private",
                    allow_from=[],
                )
            ]
        )


def test_binding_policy_rejects_channel_owned_by_another_role() -> None:
    policy = RoleBindingPolicy()
    existing = RoleChannelBindingConfig(
        channel="telegram",
        chat_id="chat-1",
        chat_type="private",
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
        # A private QQ chat no longer has to equal its contact (#397).
        RoleChannelBindingConfig("qq", "831907794", "private", ["3174898512"]),
        RoleChannelBindingConfig("qq", "gqq:831907794", "group", ["3174898512"]),
        RoleChannelBindingConfig("qqbot", "c2c:u1", "private", ["u1"]),
    ]

    assert _declared_policy().normalize(bindings) == bindings


@pytest.mark.parametrize(
    "binding, message",
    [
        # Group type without its prefix: QQ would send it as a private chat.
        (RoleChannelBindingConfig("qq", "831907794", "group", ["3"]), "gqq:<群号>"),
        (RoleChannelBindingConfig("qq", "gqq:", "group", ["3"]), "gqq:<群号>"),
        # Private type carrying the group prefix names the other type.
        (RoleChannelBindingConfig("qq", "gqq:831907794", "private", ["3"]), "群聊格式"),
        (
            RoleChannelBindingConfig("qqbot", "u1", "private", ["u1"]),
            "c2c:<用户 OpenID>",
        ),
        # qqbot declares no group chats.
        (RoleChannelBindingConfig("qqbot", "c2c:u1", "group", ["u1"]), "可选：私聊"),
    ],
)
def test_binding_policy_rejects_chat_id_inconsistent_with_its_type(
    binding: RoleChannelBindingConfig, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        _declared_policy().normalize([binding])


def test_binding_policy_accepts_any_type_for_channels_without_declarations() -> None:
    bindings = [
        RoleChannelBindingConfig("custom", "room-1", "group", ["u1"]),
        RoleChannelBindingConfig("custom", "gqq:1", "private", ["u1"]),
    ]

    assert _declared_policy().normalize(bindings) == bindings


def test_binding_policy_requires_private_desktop_session() -> None:
    desktop = RoleChannelBindingConfig("desktop", "role:mira", "group", [])

    with pytest.raises(ValueError, match="私聊"):
        RoleBindingPolicy().normalize_for_role([], "mira", [desktop])
