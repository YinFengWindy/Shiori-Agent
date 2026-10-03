"""Session snapshot persistence regressions."""

from pathlib import Path
from dataclasses import replace
import asyncio

import pytest

from session.manager import SessionManager
from session.manager.models import build_session_message
from session.manager.consolidation import ConsolidationCommitRequest
from unittest.mock import AsyncMock
from conversation.context_scope import history_start


async def test_private_delivery_deduplication_is_inside_the_session_write_lock(
    tmp_path,
):
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("role:mira")
    manager.save(session)
    drafts = [
        build_session_message(
            "assistant", "delivered", metadata={"delivery_key": "same"}
        )
        for _ in range(2)
    ]
    tasks = []
    try:
        async with manager._lock(session.key):
            tasks = [
                asyncio.create_task(
                    manager.append_messages(
                        session, [draft], pending_messages=True, delivery_key="same"
                    )
                )
                for draft in drafts
            ]
            await asyncio.sleep(0)
            assert not any(task.done() for task in tasks)
            assert session.messages == []
        assert await asyncio.gather(*tasks) == [True, False]
        assert len(manager._store.fetch_session_messages(session.key)) == 1
        assert len(session.messages) == 1
        assert "id" not in drafts[1]
    finally:
        await asyncio.gather(*tasks, return_exceptions=True)


@pytest.mark.parametrize("failure", [OSError("disk full"), asyncio.CancelledError()])
async def test_failed_private_delivery_can_retry_the_same_key(
    tmp_path, monkeypatch, failure
):
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("role:mira")
    manager.save(session)
    draft = build_session_message(
        "assistant", "delivered", metadata={"delivery_key": "same"}
    )
    original = manager._project_session_threads

    def fail_after_insert(*args):
        raise failure

    monkeypatch.setattr(manager, "_project_session_threads", fail_after_insert)
    with pytest.raises(type(failure)):
        await manager.append_messages(
            session, [draft], pending_messages=True, delivery_key="same"
        )
    assert session.messages == [] and "id" not in draft
    assert manager._store.fetch_session_messages(session.key) == []
    monkeypatch.setattr(manager, "_project_session_threads", original)
    assert await manager.append_messages(
        session, [draft], pending_messages=True, delivery_key="same"
    )
    assert not await manager.append_messages(
        session, [draft], pending_messages=True, delivery_key="same"
    )
    assert len(manager._store.fetch_session_messages(session.key)) == 1


async def test_delivery_deduplication_cannot_repeat_a_transport_callback(tmp_path):
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("role:mira")
    draft = build_session_message(
        "assistant", "delivered", metadata={"delivery_key": "same"}
    )
    send = AsyncMock(return_value=True)
    with pytest.raises(ValueError, match="before_commit"):
        await manager.append_messages(
            session,
            [draft],
            pending_messages=True,
            delivery_key="same",
            expected_mood_updated_at="",
            before_commit=send,
        )
    send.assert_not_awaited()
    assert session.messages == []


async def test_stale_message_rewrite_preserves_progress_and_clear_invalidates_it(
    tmp_path,
):
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("cli:rewrite")
    session.add_message("user", "old")
    session.add_message("assistant", "answer")
    manager.save(session)
    stale = replace(session, messages=[dict(message) for message in session.messages])
    assert await manager.commit_consolidation(
        ConsolidationCommitRequest(
            session.key,
            tuple(m["id"] for m in session.messages),
            expected_last_consolidated=0,
            last_consolidated=2,
        ),
        AsyncMock(),
    )
    prepared = await manager.prepare_window(session.key, None, keep_turns=0)
    assert prepared is not None and await manager.commit_window(
        prepared, "state", prepared.removed_message_ids
    )
    stale.messages[0]["content"] = "edited"
    manager.save(stale)
    manager.invalidate(session.key)
    restored = manager.get_or_create(session.key)
    assert restored.last_consolidated == history_start(restored, None) == 2
    restored.clear()
    manager.save(restored)
    restored.add_message("user", "new")
    manager.save(restored)
    manager.invalidate(restored.key)
    restored = manager.get_or_create(restored.key)
    assert restored.last_consolidated == history_start(restored, None) == 0
    assert len(restored.messages) == 1


async def test_clear_without_persisted_progress_expires_old_observations(tmp_path):
    from core.compaction import CompactionController, CompactionResult

    manager = SessionManager(tmp_path)
    session = manager.get_or_create("cli:never-maintained")
    session.add_message("user", "old")
    session.add_message("assistant", "answer")
    manager.save(session)
    assert not manager._store.get_session_meta(session.key)["maintenance_progress"]
    progress = manager.maintenance_progress(session)
    controller = CompactionController(manager, None, None)  # type: ignore[arg-type]
    await controller.record(
        session.key,
        None,
        CompactionResult(
            phase="completed",
            ownership=progress.ownership,
            generation=progress.generation,
        ),
        request_usage={},
        request_attempted=True,
    )
    assert controller.latest(session.key, None) is not None
    session.clear()
    manager.save(session)
    assert controller.latest(session.key, None) is None
    assert controller.latest(session.key, None, request=True) is None


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
