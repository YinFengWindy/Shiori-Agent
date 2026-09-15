"""Session snapshot persistence regressions."""

from pathlib import Path

import pytest

from session.manager import SessionManager


def test_session_clear_persists_deleted_messages(tmp_path: Path):
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("cli:1")
    session.add_message("user", "question")
    session.add_message("assistant", "answer")
    manager.save(session)

    session.clear()
    manager.save(session)
    manager.invalidate(session.key)

    assert manager.get_or_create(session.key).messages == []


async def test_append_state_and_messages_roll_back_together_on_second_insert_failure(
    tmp_path, monkeypatch
):
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("role:yin")
    session.metadata = {"current_mood": "害羞", "current_thought": "我在等你。"}
    manager.save(session)
    session.metadata.update(current_mood="平静", current_thought="我放心了。")
    session.add_message("user", "你好")
    session.add_message(
        "assistant", "回来啦", metadata={"mood": "平静", "thought": "我放心了。"}
    )
    original_insert = manager._store.insert_message
    calls = 0

    def insert(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("disk full")
        return original_insert(*args, **kwargs)

    monkeypatch.setattr(manager._store, "insert_message", insert)
    with pytest.raises(OSError, match="disk full"):
        await manager.append_messages(session, session.messages)
    assert all("id" not in message for message in session.messages)
    reloaded = SessionManager(tmp_path).get_or_create(session.key)
    assert reloaded.messages == []
    assert reloaded.metadata == {
        "current_mood": "害羞",
        "current_thought": "我在等你。",
    }
