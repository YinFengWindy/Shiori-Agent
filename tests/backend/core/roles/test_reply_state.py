"""Formal role state rejects invalid fields instead of inferring from reasoning.

Content stopped round-tripping through JSON with #303 (the reasoner now
produces plain content directly and only sends `{mood, thought}` payloads
through `validate_role_reply`), so this validates the shared contract
directly on dict payloads rather than through JSON string parsing.
"""

import pytest

from core.roles.reply_state import (
    AffectionChange,
    InvalidRoleReply,
    role_mood_catalog,
    role_mood_prompt,
    validate_role_reply,
    with_affection_change,
    with_group_mentions,
)


@pytest.mark.parametrize(
    "payload",
    [
        {"content": "你好", "mood": "平静"},
        {"content": "你好", "mood": "害羞", "thought": "我很开心。"},
        {"content": "你好", "mood": "平静", "thought": "她很开心。"},
        {"content": "", "mood": "平静", "thought": "我很开心。"},
        {"content": "你好", "mood": "", "thought": "我很开心。"},
    ],
)
def test_invalid_formal_reply_cannot_silently_choose_default(payload):
    with pytest.raises(InvalidRoleReply):
        validate_role_reply(payload, ("平静",))


def test_short_first_person_thought_does_not_require_padding():
    payload = {"content": "正文" * 500, "mood": "平静", "thought": "我终于放心了。"}
    reply = validate_role_reply(payload, ("平静",))
    assert reply.mood == "平静"
    assert len(reply.content) == 1000
    assert reply.thought == "我终于放心了。"


def test_excessively_long_thought_is_rejected():
    with pytest.raises(InvalidRoleReply, match="100"):
        validate_role_reply(
            {"content": "你好", "mood": "平静", "thought": "我" * 101}, ("平静",)
        )


def test_empty_content_allowed_only_when_explicitly_opted_in():
    reply = validate_role_reply(
        {"content": "", "mood": "平静", "thought": "我很开心。"},
        ("平静",),
        allow_empty_content=True,
    )
    assert reply.content == ""


def test_mood_catalog_does_not_require_illustrations():
    assert role_mood_catalog(
        {"mood_catalog": ["平静", "开心"], "mood_illustration_bindings": {}}
    ) == ("平静", "开心")
    assert role_mood_catalog({}) == ("平静",)


def test_only_group_replies_carry_mentions_and_a_bad_list_keeps_the_mood(caplog):
    payload = {"content": "好", "mood": "平静", "thought": "我放心了。"}
    # The shared validator never reads mentions, so private, desktop and
    # proactive replies cannot carry any.
    reply = validate_role_reply({**payload, "mention_ids": ["902"]}, ("平静",))
    assert reply.mention_ids == ()
    grouped = with_group_mentions(reply, ["902", 903, "902"])
    assert grouped.mention_ids == ("902", "903")
    assert (grouped.mood, grouped.thought) == ("平静", "我放心了。")
    with caplog.at_level("WARNING", logger="core.roles.reply_state"):
        kept = with_group_mentions(reply, "902")
    assert kept == reply
    assert "mention_ids" in caplog.text
    assert "mention_ids" in role_mood_prompt(("平静",), group=True)
    assert "mention_ids" not in role_mood_prompt(("平静",))


MOOD = {"content": "好", "mood": "平静", "thought": "我放心了。"}


@pytest.mark.parametrize(("reported", "applied"), [(10, 3), (-10, -3), (-1, -1)])
def test_affection_change_is_truncated_to_three(reported, applied):
    reply = validate_role_reply(MOOD, ("平静",))
    changed = with_affection_change(
        reply, {"affection_delta": reported, "affection_reason": " 他记得我。 "}
    )
    assert changed.affection == AffectionChange(applied, "他记得我。")
    assert (changed.mood, changed.thought) == ("平静", "我放心了。")


@pytest.mark.parametrize(
    ("affection", "logged"),
    [
        ({}, None),
        ({"affection_delta": 0, "affection_reason": "没什么变化"}, None),
        ({"affection_reason": "原因"}, "缺少 affection_delta"),
        ({"affection_delta": "2", "affection_reason": "原因"}, "affection_delta 无效"),
        ({"affection_delta": 1.5, "affection_reason": "原因"}, "affection_delta 无效"),
        ({"affection_delta": True, "affection_reason": "原因"}, "affection_delta 无效"),
        ({"affection_delta": 2}, "affection_reason"),
        ({"affection_delta": 2, "affection_reason": "  "}, "affection_reason"),
    ],
)
def test_missing_or_invalid_affection_keeps_the_mood_and_changes_nothing(
    caplog, affection, logged
):
    reply = validate_role_reply(MOOD, ("平静",))
    with caplog.at_level("WARNING", logger="core.roles.reply_state"):
        kept = with_affection_change(reply, {**MOOD, **affection})
    assert kept == reply
    assert kept.affection is None
    if logged is None:
        assert caplog.text == ""
    else:
        assert logged in caplog.text
