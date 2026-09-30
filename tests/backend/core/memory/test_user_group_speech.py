"""「用户最近在群里说过」：只含用户本人在群里的发言与角色的回复（#539）。"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from conversation.service import desktop_thread_id, network_thread_id
from core.memory.user_group_speech import (
    USER_GROUP_SPEECH_LIMIT,
    collect_user_group_speech,
    render_user_group_speech,
)
from session.manager import SessionManager

GROUP_A = network_thread_id("mira", "qq", "gqq:1")
GROUP_B = network_thread_id("mira", "qq", "gqq:2")
USER_DM = network_thread_id("mira", "qq", "902")
NOW = datetime(2026, 9, 30, 18, 0).astimezone()


def _source(sender_id: str, group: str | None, *, is_user: bool) -> dict:
    source: dict[str, object] = {"channel": "qq", "sender_id": sender_id}
    if group is not None:
        source.update(chat_type="group", group_name=group)
    else:
        source["chat_type"] = "private"
    if is_user:
        source["sender_is_user"] = True
    return {"message_source": source}


def _say(session, thread: str, role: str, text: str, at: datetime, **metadata):
    session.add_message(role, text, thread_id=thread, metadata=metadata)
    session.messages[-1]["timestamp"] = at.isoformat()


def test_only_the_users_own_group_speech_and_the_replies(tmp_path: Path) -> None:
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("role:mira")
    early = NOW - timedelta(hours=7)
    recent = NOW - timedelta(hours=1)
    _say(
        session,
        GROUP_A,
        "user",
        "太早了",
        early,
        **_source("902", "猫猫群", is_user=True),
    )
    _say(session, GROUP_A, "assistant", "早的回复", early)
    _say(
        session,
        GROUP_A,
        "user",
        "晚上吃啥",
        recent,
        **_source("902", "猫猫群", is_user=True),
    )
    _say(session, GROUP_A, "assistant", "火锅吧", recent)
    _say(
        session,
        GROUP_A,
        "user",
        "群友的话",
        recent,
        **_source("77", "猫猫群", is_user=False),
    )
    _say(session, GROUP_A, "assistant", "回群友", recent)
    _say(
        session,
        USER_DM,
        "user",
        "私聊的话",
        recent,
        **_source("902", None, is_user=True),
    )
    _say(session, desktop_thread_id("mira"), "user", "桌面的话", recent)
    manager.save(session)
    listening = manager.conversation_store.listening
    listening.switches.set_enabled(GROUP_B, True, operator="user")
    for sender_id, text, is_user in (
        ("902", "旁听里我说的", True),
        ("77", "旁听群友", False),
    ):
        listening.hear(
            GROUP_B,
            sender_id=sender_id,
            content=text,
            source=_source(sender_id, "狗狗群", is_user=is_user)["message_source"],
            external_message_id="",
            timestamp=recent + timedelta(minutes=5),
        )

    rendered = render_user_group_speech(
        collect_user_group_speech(manager.conversation_store, "mira", now=NOW)
    )

    assert "群「猫猫群」 用户：晚上吃啥" in rendered
    assert "我的回复：火锅吧" in rendered
    assert "群「狗狗群」 用户：旁听里我说的" in rendered
    for absent in ("太早了", "早的回复", "群友", "回群友", "私聊的话", "桌面的话"):
        assert absent not in rendered


def test_keeps_the_newest_user_messages_within_the_limit(tmp_path: Path) -> None:
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("role:mira")
    for index in range(USER_GROUP_SPEECH_LIMIT + 2):
        _say(
            session,
            GROUP_A,
            "user",
            f"第{index}句",
            NOW - timedelta(minutes=60 - index),
            **_source("902", "猫猫群", is_user=True),
        )
    manager.save(session)

    speeches = collect_user_group_speech(manager.conversation_store, "mira", now=NOW)

    assert [speech.text for speech in speeches] == [
        f"第{index}句" for index in range(2, USER_GROUP_SPEECH_LIMIT + 2)
    ]
