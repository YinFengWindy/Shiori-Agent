"""Formal role state rejects invalid fields instead of inferring from reasoning.

Content stopped round-tripping through JSON with #303 (the reasoner now
produces plain content directly and only sends `{mood, thought}` payloads
through `validate_role_reply`), so this validates the shared contract
directly on dict payloads rather than through JSON string parsing.
"""

import pytest

from core.roles.reply_state import (
    InvalidRoleReply,
    role_mood_catalog,
    validate_role_reply,
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
