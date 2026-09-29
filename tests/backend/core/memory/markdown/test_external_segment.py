from __future__ import annotations

from conversation.service import network_thread_id
from core.memory.group_environment import GroupEnvironmentSnapshot
from core.memory.markdown.contracts import ConsolidationSegments, _ConsolidationWindow
from core.memory.markdown.external_segment import (
    build_group_environment_prompt,
    format_external_thread,
    group_external_threads,
    parse_group_environment_update,
)

_GROUP = network_thread_id("mira", "qq", "g1")


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
    window = _ConsolidationWindow(
        old_messages=[member, reply, user], keep_count=0, consolidate_up_to=3
    )
    # 用户本人的发言归用户本人段，但作为群里的上下文一并渲染。
    segments = ConsolidationSegments(
        user_messages=[user], external_messages=[member, reply]
    )

    [thread] = group_external_threads(window, segments)
    conversation = format_external_thread(thread)
    prompt = build_group_environment_prompt(
        thread, conversation, GroupEnvironmentSnapshot("", ""), {}
    )

    assert thread.label == "群「猫猫群」"
    assert "阿明（555）: 我最喜欢狗" in conversation
    assert "我: 阿明好" in conversation
    assert "你的用户（小风）: 我明天去面试" in conversation
    assert "「群「猫猫群」」" in prompt
    assert "600 字" in prompt


def test_parse_keeps_only_text_fields() -> None:
    window = _ConsolidationWindow(
        old_messages=[_group_message("hi", sender_id="555")],
        keep_count=0,
        consolidate_up_to=1,
    )
    [thread] = group_external_threads(
        window,
        ConsolidationSegments(user_messages=[], external_messages=window.old_messages),
    )

    update = parse_group_environment_update(
        {"recent_activity": " 阿明打了招呼。 ", "group_note": ["not text"]}, thread
    )

    assert update.thread_id == _GROUP
    assert update.recent_activity == "阿明打了招呼。"
    assert update.group_note == ""
