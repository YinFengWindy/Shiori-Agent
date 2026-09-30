"""A group's listening records: the switch gate, the daily cap and the recent window."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from conversation.listening_store import GroupListeningStore
from conversation.store import ConversationStore

_GROUP = "thread:mira:qq:gqq:5"
_DAY = datetime(2026, 9, 30, 9, 0).astimezone()


def _store(tmp_path: Path) -> GroupListeningStore:
    return ConversationStore(tmp_path / "sessions.db").listening


def _hear(store: GroupListeningStore, content: str, at: datetime, external: str = ""):
    return store.hear(
        _GROUP,
        sender_id="42",
        content=content,
        source={"sender_name": "阿花"},
        external_message_id=external,
        timestamp=at,
    )


def test_only_a_listened_group_keeps_messages_and_turning_off_keeps_them(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    assert _hear(store, "没开", _DAY) is None

    store.switches.set_enabled(_GROUP, True, operator="user")
    heard = _hear(store, "开了", _DAY, external="m1")
    # A replayed platform message is kept once.
    assert _hear(store, "开了", _DAY, external="m1") is None
    store.switches.set_enabled(_GROUP, False, operator="role")

    assert heard is not None and heard.stored
    assert [message.content for message in store.page(_GROUP)["messages"]] == ["开了"]
    assert _hear(store, "又关了", _DAY) is None


def test_past_the_daily_cap_messages_stay_only_in_the_recent_window(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    store.switches.set_enabled(_GROUP, True, operator="user")
    store.switches.set_daily_cap(_GROUP, 2)
    heard = [
        _hear(store, f"第{index}条", _DAY + timedelta(minutes=index), f"m{index}")
        for index in range(3)
    ]
    # A replay of a message past the cap does not enter the window twice.
    assert _hear(store, "第2条", _DAY + timedelta(minutes=2), "m2") is None
    next_day = _hear(store, "第二天", _DAY + timedelta(days=1))

    assert [message.stored for message in heard if message] == [True, True, False]
    assert next_day is not None and next_day.stored
    assert [message.content for message in store.page(_GROUP)["messages"]] == [
        "第0条",
        "第1条",
        "第二天",
    ]
    # The prompt reads stored records and the window together, by time.
    assert [message.content for message in store.recent(_GROUP)] == [
        "第0条",
        "第1条",
        "第2条",
        "第二天",
    ]
