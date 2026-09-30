"""Response rules normalize IDs, reject malformed fields, and round-trip."""

from __future__ import annotations

import pytest

from core.accounts.rules import response_rules_from_dict, response_rules_to_dict


def test_normalizes_blocked_sender_ids_and_round_trips():
    # Rules saved before #537 still carry the retired ``require_mention`` switch.
    rules = response_rules_from_dict(
        {
            "private_enabled": True,
            "group_enabled": True,
            "require_mention": False,
            "blocked_sender_ids": [" member-1 ", "member-1"],
        }
    )
    assert rules.blocked_sender_ids == ("member-1",)
    assert "require_mention" not in response_rules_to_dict(rules)
    assert response_rules_from_dict(response_rules_to_dict(rules)) == rules


@pytest.mark.parametrize(
    "change",
    [{"private_enabled": "true"}, {"blocked_sender_ids": [""]}],
)
def test_rejects_malformed_rules(change):
    payload = {
        "private_enabled": True,
        "group_enabled": True,
        "blocked_sender_ids": [],
        **change,
    }
    with pytest.raises(ValueError, match="Invalid account response rules"):
        response_rules_from_dict(payload)
