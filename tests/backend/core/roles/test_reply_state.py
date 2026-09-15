"""Formal role state rejects missing fields instead of inferring from reasoning."""

import json

import pytest

from core.roles.reply_state import InvalidRoleReply, parse_role_reply, role_mood_catalog


@pytest.mark.parametrize(
    "raw",
    [
        "哼，总算回我了。",
        "",
        '{"content":"你好"',
        "[]",
        '{"content":"你好","mood":"平静"}',
        '{"content":"你好","mood":"害羞","thought":"我很开心。"}',
        '{"content":"你好","mood":"平静","thought":"她很开心。"}',
        '{"content":"你好","content":"改写","mood":"平静","thought":"我很开心。"}',
    ],
)
def test_invalid_formal_reply_cannot_silently_choose_default(raw):
    with pytest.raises(InvalidRoleReply):
        parse_role_reply(raw, ("平静",))


def test_short_first_person_thought_does_not_require_padding():
    raw = json.dumps(
        {"content": "正文" * 500, "mood": "平静", "thought": "我终于放心了。"},
        ensure_ascii=False,
    )
    reply = parse_role_reply(raw, ("平静",))
    assert reply.mood == "平静"
    assert len(reply.content) == 1000
    assert reply.thought == "我终于放心了。"


def test_excessively_long_thought_is_rejected():
    with pytest.raises(InvalidRoleReply, match="100"):
        parse_role_reply(
            json.dumps({"content": "你好", "mood": "平静", "thought": "我" * 101}),
            ("平静",),
        )


def test_mood_catalog_does_not_require_illustrations():
    assert role_mood_catalog(
        {"mood_catalog": ["平静", "开心"], "mood_illustration_bindings": {}}
    ) == ("平静", "开心")
    assert role_mood_catalog({}) == ("平静",)
