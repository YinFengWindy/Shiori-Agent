from __future__ import annotations

from conversation.service import network_thread_id
from shiori_sdk.accounts.models import AccountRecord
from core.identity import BoundUserSenders, UserIdentity
from core.memory.group_environment import GroupEnvironmentSnapshot
from core.memory.markdown.contracts import ConsolidationSegments, ConsolidationWindow
from core.memory.markdown.external_segment import (
    build_group_environment_prompt,
    format_external_thread,
    group_external_threads,
    parse_group_environment_update,
)
from core.memory.member_profiles import MemberKey

_GROUP = network_thread_id("mira", "qq", "g1")
_NO_BINDINGS = BoundUserSenders(identities=(), accounts=())


def _group_message(content: str, **source: object) -> dict:
    return {
        "role": "user",
        "content": content,
        "timestamp": "2026-09-30T10:00:00",
        "thread_id": _GROUP,
        "metadata": {
            "message_source": {"chat_type": "group", "group_name": "猫猫群", **source}
        },
    }


def test_external_thread_renders_speakers_in_the_third_person() -> None:
    member = _group_message("我最喜欢狗", sender_id="555", sender_name="阿明")
    reply = {
        "role": "assistant",
        "content": "阿明好",
        "timestamp": "2026-09-30T10:01:00",
        "thread_id": _GROUP,
    }
    user = _group_message(
        "我明天去面试", sender_id="902", sender_name="小风", sender_is_user=True
    )
    window = ConsolidationWindow(
        old_messages=[member, reply, user], keep_count=0, consolidate_up_to=3
    )
    # 用户本人的发言归用户本人段，但作为群里的上下文一并渲染。
    segments = ConsolidationSegments(
        user_messages=[user], external_messages=[member, reply]
    )

    [thread] = group_external_threads(window, segments, _NO_BINDINGS)
    conversation = format_external_thread(thread)
    prompt = build_group_environment_prompt(
        thread, conversation, GroupEnvironmentSnapshot("", ""), thread.members, {}
    )

    assert thread.label == "群「猫猫群」"
    assert "阿明（555）: 我最喜欢狗" in conversation
    assert "我: 阿明好" in conversation
    assert "你的用户（小风）: 我明天去面试" in conversation
    assert "「群「猫猫群」」" in prompt
    assert "600 字" in prompt


def test_parse_keeps_only_text_fields() -> None:
    window = ConsolidationWindow(
        old_messages=[_group_message("hi", sender_id="555")],
        keep_count=0,
        consolidate_up_to=1,
    )
    [thread] = group_external_threads(
        window,
        ConsolidationSegments(user_messages=[], external_messages=window.old_messages),
        _NO_BINDINGS,
    )

    update = parse_group_environment_update(
        {"recent_activity": " 阿明打了招呼。 ", "group_note": ["not text"]}, thread
    )

    assert update.thread_id == _GROUP
    assert update.recent_activity == "阿明打了招呼。"
    assert update.group_note == ""


def test_members_skip_the_bound_user_and_take_the_latest_nickname_across_threads() -> (
    None
):
    other_group = network_thread_id("mira", "qq", "g2")
    messages = [
        _group_message("hi", channel="qq", sender_id="555", sender_name="阿明"),
        {
            **_group_message("hi", channel="qq", sender_id="555", sender_name="明哥"),
            "thread_id": other_group,
        },
        _group_message("hi", channel="qq", sender_id="555", sender_name="小明"),
        # 消息没有标记，但此刻的身份绑定认出他是用户本人。
        _group_message("hi", channel="qq", sender_id="902", sender_name="小风"),
    ]
    window = ConsolidationWindow(
        old_messages=messages, keep_count=0, consolidate_up_to=len(messages)
    )
    bound = BoundUserSenders(
        identities=(
            UserIdentity("i1", "qq", "902", "platform", "", "2026-09-30T00:00:00"),
        ),
        accounts=(AccountRecord("qq:1", "qq", "qq", "1", "cfg", role_id="mira"),),
    )

    threads = group_external_threads(
        window,
        ConsolidationSegments(user_messages=[], external_messages=messages),
        bound,
    )

    # 两个会话里都是同一人，昵称按消息先后累积，最后出现的「小明」是当前称呼。
    for thread in threads:
        [member] = thread.members
        assert member.key == MemberKey("qq", "555")
        assert member.nicknames == ("阿明", "明哥", "小明")


def test_a_sender_bound_after_the_message_is_rendered_as_the_user() -> None:
    private = network_thread_id("mira", "qq", "902")
    # 收到时还没绑定，消息没有标记；此刻的身份绑定认出他是用户本人。
    message = {
        "role": "user",
        "content": "我明天去面试",
        "timestamp": "2026-09-30T10:00:00",
        "thread_id": private,
        "metadata": {
            "message_source": {
                "channel": "qq",
                "chat_type": "private",
                "sender_id": "902",
                "sender_name": "小风",
            }
        },
    }
    window = ConsolidationWindow(
        old_messages=[message], keep_count=0, consolidate_up_to=1
    )
    bound = BoundUserSenders(
        identities=(
            UserIdentity("i1", "qq", "902", "platform", "", "2026-09-30T00:00:00"),
        ),
        accounts=(AccountRecord("qq:1", "qq", "qq", "1", "cfg", role_id="mira"),),
    )

    [thread] = group_external_threads(
        window,
        ConsolidationSegments(user_messages=[], external_messages=[message]),
        bound,
    )

    assert thread.label == "一段私聊"
    assert "你的用户（小风）: 我明天去面试" in format_external_thread(thread)
    assert "小风（902）" not in format_external_thread(thread)
