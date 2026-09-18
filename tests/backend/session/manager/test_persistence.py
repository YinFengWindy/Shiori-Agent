"""Session snapshot persistence regressions."""

from pathlib import Path
from dataclasses import replace

import pytest

from session.manager import SessionManager
from session.manager.models import build_session_message


async def test_media_replacement_copies_assets_preserves_cache_and_rejects_stale_cas(
    tmp_path,
):
    old = tmp_path / "old.png"
    old.write_bytes(b"old")
    new = tmp_path / "new.png"
    new.write_bytes(b"new")
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("role:media")
    session.add_message("assistant", "image", media=[str(old)])
    manager.save(session)
    message_id = session.messages[0]["id"]
    expected = session.messages[0]["media"][0]
    assert expected != str(old)
    updated = await manager.replace_message_media(
        session_key=session.key,
        message_id=message_id,
        media_index=0,
        expected_path=expected,
        new_path=str(new),
    )
    current = updated.messages[0]["media"][0]
    assert current != str(new)
    assert Path(current).read_bytes() == b"new"
    with pytest.raises(ValueError, match="已发生变化"):
        await manager.replace_message_media(
            session_key=session.key,
            message_id=message_id,
            media_index=0,
            expected_path=expected,
            new_path=str(old),
        )
    assert manager.get_or_create(session.key).messages[0]["media"] == [current]
    manager.invalidate(session.key)
    assert manager.get_or_create(session.key).messages[0]["media"] == [current]


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


async def test_pending_commit_checks_latest_cached_session_instead_of_old_reference(
    tmp_path,
):
    manager = SessionManager(tmp_path)
    old = manager.get_or_create("role:yin")
    old.metadata = {"current_mood_updated_at": "old"}
    manager.save(old)
    latest = replace(
        old, metadata={"current_mood_updated_at": "new", "current_mood": "开心"}
    )
    manager.save(latest)
    draft = build_session_message("assistant", "过时的回复")
    with pytest.raises(ValueError, match="过时"):
        await manager.append_messages(
            old,
            [draft],
            pending_messages=True,
            metadata_updates={"current_mood": "平静"},
            expected_mood_updated_at="old",
        )
    assert manager.get_or_create(old.key) is latest
    assert latest.messages == []
    assert latest.metadata["current_mood"] == "开心"
    assert "id" not in draft
