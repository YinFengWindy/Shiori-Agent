"""Response rule payloads normalize IDs and reject ambiguous group policies."""

from __future__ import annotations

import pytest

from desktop_bridge.account_rule_payload import parse_response_rules


def test_normalizes_account_and_group_sender_ids():
    rules = parse_response_rules(
        {
            "private_enabled": True,
            "group_enabled": True,
            "require_mention": False,
            "blocked_sender_ids": [" member-1 ", "member-1"],
            "group_rules": [
                {
                    "chat_id": " group-1 ",
                    "enabled": False,
                    "require_mention": True,
                    "blocked_sender_ids": ["sender-1", " sender-1 "],
                }
            ],
        }
    )
    assert rules.blocked_sender_ids == ("member-1",)
    assert rules.group_rules[0].chat_id == "group-1"
    assert rules.group_rules[0].blocked_sender_ids == ("sender-1",)


@pytest.mark.parametrize(
    "change, message",
    [
        ({"private_enabled": "true"}, "Invalid account response rules"),
        ({"blocked_sender_ids": [""]}, "Invalid account response rules"),
        ({"group_rules": [{}]}, "Invalid group response rule"),
        (
            {
                "group_rules": [
                    {
                        "chat_id": "a",
                        "enabled": True,
                        "require_mention": True,
                        "blocked_sender_ids": [],
                    },
                    {
                        "chat_id": " a ",
                        "enabled": True,
                        "require_mention": True,
                        "blocked_sender_ids": [],
                    },
                ]
            },
            "Duplicate group response rule",
        ),
    ],
)
def test_rejects_malformed_or_duplicate_rules(change, message):
    payload = {
        "private_enabled": True,
        "group_enabled": True,
        "require_mention": True,
        "blocked_sender_ids": [],
        "group_rules": [],
        **change,
    }
    with pytest.raises(ValueError, match=message):
        parse_response_rules(payload)
