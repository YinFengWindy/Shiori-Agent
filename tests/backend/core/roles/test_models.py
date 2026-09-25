from __future__ import annotations

import pytest

from core.roles.models import RoleChannelBindingConfig


def test_group_binding_normalizes_its_blacklist() -> None:
    binding = RoleChannelBindingConfig.from_dict(
        {
            "channel": "qq",
            "chat_id": "gqq:7",
            "chat_type": "group",
            "blocked_senders": [" 42", "", "13", "42 ", 7],
        }
    )

    assert binding.blocked_senders == ["13", "42", "7"]
    assert binding.to_dict() == {
        "channel": "qq",
        "chat_id": "gqq:7",
        "chat_type": "group",
        "blocked_senders": ["13", "42", "7"],
    }


def test_binding_without_blacklist_defaults_to_empty() -> None:
    binding = RoleChannelBindingConfig.from_dict(
        {"channel": "qq", "chat_id": "10001", "chat_type": "private"}
    )

    assert binding.blocked_senders == []


@pytest.mark.parametrize("channel, chat_id", [("qq", "10001"), ("desktop", "role:a")])
def test_private_binding_rejects_a_blacklist(channel: str, chat_id: str) -> None:
    with pytest.raises(ValueError, match="只有群聊绑定可以设置黑名单"):
        RoleChannelBindingConfig(channel, chat_id, "private", ["42"])


def test_binding_rejects_non_list_blacklist() -> None:
    with pytest.raises(ValueError, match="blocked_senders 必须是数组"):
        RoleChannelBindingConfig.from_dict(
            {
                "channel": "qq",
                "chat_id": "gqq:7",
                "chat_type": "group",
                "blocked_senders": "42",
            }
        )
