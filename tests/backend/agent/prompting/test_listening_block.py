from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from agent.prompting.listening_block import (
    HEARD_BLOCK_TITLE,
    LISTENING_MESSAGE_CHAR_LIMIT,
    LISTENING_PROMPT_CHAR_LIMIT,
    LISTENING_PROMPT_LIMIT,
    heard_for_prompt,
    render_heard_block,
)
from conversation.listening_store import GroupListeningStore
from conversation.store import ConversationStore

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


def test_block_lists_the_heard_lines_in_time_order_under_its_title(
    tmp_path: Path,
) -> None:
    store = _listening(tmp_path)
    # Heard out of order; a sender without a reported name shows only the ID.
    _hear(store, "后说的", _START + timedelta(minutes=2))
    _hear(store, "先说的", _START + timedelta(minutes=1))
    store.hear(
        _GROUP,
        sender_id="43",
        content="没报昵称",
        source={},
        external_message_id="",
        timestamp=_START + timedelta(minutes=3),
    )

    block = render_heard_block(heard_for_prompt(store, _GROUP))

    assert block.splitlines() == [
        HEARD_BLOCK_TITLE,
        "[09-30 09:01] 阿花（ID 42）（@ ID 7）：先说的",
        "[09-30 09:02] 阿花（ID 42）（@ ID 7）：后说的",
        "[09-30 09:03] ID 43：没报昵称",
    ]
    assert render_heard_block([]) == ""
