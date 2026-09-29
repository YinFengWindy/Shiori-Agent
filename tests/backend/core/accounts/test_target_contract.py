"""Account targets are checked for shape only; capability is the plugin's call."""

from __future__ import annotations

import pytest

from core.accounts.target_contract import AccountTarget, account_send_media


def test_target_options_travel_to_the_plugin_payload() -> None:
    group = AccountTarget.from_arguments(
        {"target_kind": "group", "target_id": 777, "mention_ids": ["902", 903, "902"]}
    )
    assert group.to_payload() == {
        "target_kind": "group",
        "target_id": "777",
        "message_thread_id": None,
        "group_id": "",
        "mention_ids": ["902", "903"],
    }
    member = AccountTarget.from_arguments(
        {"target_kind": "group_member", "target_id": "902", "group_id": "777"}
    )
    assert (member.kind, member.id, member.group_id) == ("group_member", "902", "777")


@pytest.mark.parametrize(
    ("arguments", "error"),
    [
        ({"target_kind": "private"}, "目标 ID"),
        ({"target_kind": "private", "target_id": "1", "mention_ids": ["2"]}, "group"),
        ({"target_kind": "group", "target_id": "1", "mention_ids": "2"}, "列表"),
        ({"target_kind": "group", "target_id": "1", "mention_ids": [" "]}, "空成员"),
        ({"target_kind": "group_member", "target_id": "1"}, "group_id"),
        ({"target_kind": "private", "target_id": "1", "group_id": "7"}, "group_id"),
        (
            {"target_kind": "group", "target_id": "1", "message_thread_id": True},
            "整数",
        ),
    ],
)
def test_misplaced_or_malformed_options_are_refused(arguments, error) -> None:
    with pytest.raises(ValueError, match=error):
        AccountTarget.from_arguments(arguments)


def test_send_media_is_a_list_of_image_sources() -> None:
    assert account_send_media({}) == ()
    assert account_send_media({"media": [" a.png ", "https://x/b.png"]}) == (
        "a.png",
        "https://x/b.png",
    )
    for bad in ("a.png", [""], [1]):
        with pytest.raises(ValueError, match="media"):
            account_send_media({"media": bad})
