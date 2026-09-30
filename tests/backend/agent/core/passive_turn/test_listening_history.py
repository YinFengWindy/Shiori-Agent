from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from agent.core.passive_turn.listening_history import (
    HEARD_SEGMENT_HEADER,
    LISTENING_MESSAGE_CHAR_LIMIT,
    LISTENING_PROMPT_CHAR_LIMIT,
    LISTENING_PROMPT_LIMIT,
    heard_for_prompt,
    merge_heard_into_history,
)
from conversation.listening_store import GroupListeningStore
from conversation.store import ConversationStore
from session.manager.models import Session

_GROUP = "thread:mira:qq:gqq:5"
_START = datetime(2026, 9, 30, 9, 0).astimezone()


def _listening(tmp_path: Path) -> GroupListeningStore:
    store = ConversationStore(tmp_path / "sessions.db").listening
    store.switches.set_enabled(_GROUP, True, operator="user")
    return store


def _hear(store: GroupListeningStore, content: str, at: datetime) -> None:
    store.hear(
        _GROUP,
        sender_id="42",
        content=content,
        source={"sender_name": "阿花", "mentioned_ids": ["7"]},
        external_message_id="",
        timestamp=at,
    )


def test_heard_part_keeps_the_newest_within_the_count_cap(tmp_path: Path) -> None:
    store = _listening(tmp_path)
    for index in range(LISTENING_PROMPT_LIMIT + 5):
        _hear(store, f"第{index}条", _START + timedelta(minutes=index))

    lines = heard_for_prompt(store, _GROUP)

    assert len(lines) == LISTENING_PROMPT_LIMIT
    assert lines[0].text.endswith("：第5条")
    assert lines[-1].text == "[09-30 09:34] 阿花（ID 42）（@ ID 7）：第34条"


def test_long_messages_are_cut_and_the_part_stays_within_the_char_cap(
    tmp_path: Path,
) -> None:
    store = _listening(tmp_path)
    for index in range(LISTENING_PROMPT_LIMIT):
        _hear(store, f"{index}" + "长" * 1000, _START + timedelta(minutes=index))

    lines = heard_for_prompt(store, _GROUP)

    assert sum(len(line.text) + 1 for line in lines) <= LISTENING_PROMPT_CHAR_LIMIT
    # Every line is cut, so the budget holds more than a handful of them, and
    # the ones kept are the newest.
    assert all(
        "长" * (LISTENING_MESSAGE_CHAR_LIMIT + 1) not in line.text for line in lines
    )
    assert all("截断" in line.text for line in lines)
    assert len(lines) > 3
    assert "：29长" in lines[-1].text


def test_heard_messages_are_placed_between_turns_by_time(tmp_path: Path) -> None:
    store = _listening(tmp_path)
    session = Session(key="role:mira")
    for index, minute in enumerate((10, 20)):
        at = (_START + timedelta(minutes=minute)).isoformat()
        session.add_message("user", f"问{index}", thread_id=_GROUP)
        session.messages[-1]["timestamp"] = at
        session.add_message("assistant", f"答{index}", thread_id=_GROUP)
        session.messages[-1]["timestamp"] = at
    for minute in (5, 15, 16, 30):
        _hear(store, f"旁听{minute}", _START + timedelta(minutes=minute))

    merged = merge_heard_into_history(
        session, session.messages, heard_for_prompt(store, _GROUP)
    )

    def label(message: dict) -> str:
        content = str(message["content"])
        if content.startswith(HEARD_SEGMENT_HEADER):
            return "+".join(
                line.rsplit("：", 1)[-1] for line in content.split("\n")[1:]
            )
        return content.rsplit("\n", 1)[-1]

    assert [label(message) for message in merged] == [
        "旁听5",
        "问0",
        "答0",
        "旁听15+旁听16",
        "问1",
        "答1",
        "旁听30",
    ]
