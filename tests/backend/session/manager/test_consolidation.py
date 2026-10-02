"""Session-owned validation and persistence for prepared memory commits."""

import asyncio
import json
import threading
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from bus.event_bus import EventBus
from session.manager import ConsolidationCommitRequest, SessionManager
from session.manager.consumers import MemoryConsumersFailedError
from shiori_sdk.memory.events import ConsolidationCommitted

from tests.backend.core.memory.markdown.memory_double import CommittedMemory


@pytest.mark.asyncio
async def test_cursor_persistence_failure_rolls_back_private_progress(
    tmp_path, monkeypatch
):
    manager, session, request = _setup(tmp_path)
    before = manager.maintenance_progress(session).dump()

    def fail(*args, **kwargs):
        raise OSError("cursor store failed")

    monkeypatch.setattr(manager._store, "update_last_consolidated", fail)
    with pytest.raises(OSError, match="cursor store failed"):
        await manager.commit_consolidation(request, AsyncMock())
    assert session.last_consolidated == 0
    assert session.maintenance_progress.memory_version == 0
    assert not manager._store._conn.in_transaction
    manager.save(session)
    assert (
        manager._store.get_session_meta(session.key)["maintenance_progress"] == before
    )


def _setup(tmp_path: Path):
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("role:mira")
    session.add_message("user", "question")
    session.add_message("assistant", "answer")
    manager.save(session)
    request = ConsolidationCommitRequest(
        session_key=session.key,
        expected_message_ids=tuple(message["id"] for message in session.messages),
        expected_last_consolidated=0,
        last_consolidated=2,
    )
    return manager, session, request


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", ["cursor", "reordered", "missing_id"])
async def test_changed_cursor_or_source_ids_reject_before_memory_side_effects(
    tmp_path: Path, changed: str
):
    manager, session, request = _setup(tmp_path)
    if changed == "cursor":
        manager._store.update_last_consolidated(session.key, 1)

        session.last_consolidated = 1
        manager.save(session)
    elif changed == "reordered":
        request = replace(
            request, expected_message_ids=tuple(reversed(request.expected_message_ids))
        )
    else:
        request = replace(
            request, expected_message_ids=(request.expected_message_ids[0], "")
        )
    write = AsyncMock()

    assert await manager.commit_consolidation(request, write) is False
    write.assert_not_awaited()
    assert session.last_consolidated == (1 if changed == "cursor" else 0)


@pytest.mark.asyncio
async def test_commit_allows_extended_persisted_prefix(tmp_path: Path):
    manager, session, request = _setup(tmp_path)
    session.add_message("user", "next question")
    session.add_message("assistant", "next answer")
    await manager.append_messages(session, session.messages[2:])
    write = AsyncMock()

    assert await manager.commit_consolidation(request, write) is True

    write.assert_awaited_once()
    assert len(session.messages) == 4
    assert session.last_consolidated == 2
    manager.invalidate(session.key)
    reloaded = manager.get_or_create(session.key)
    assert len(reloaded.messages) == 4
    assert reloaded.last_consolidated == 2


@pytest.mark.asyncio
async def test_commit_does_not_persist_pending_append_or_overwrite_its_messages(
    tmp_path: Path,
):
    manager, session, request = _setup(tmp_path)
    entered, resume = asyncio.Event(), asyncio.Event()

    async def write():
        entered.set()
        await resume.wait()

    task = asyncio.create_task(manager.commit_consolidation(request, write))
    await asyncio.wait_for(entered.wait(), timeout=2)
    session.add_message("user", "pending question")
    session.add_message("assistant", "pending answer")
    pending = session.messages[2:]
    resume.set()
    assert await asyncio.wait_for(task, timeout=2) is True
    assert all("id" not in message for message in pending)
    assert len(manager._store.fetch_session_messages(session.key)) == 2
    await manager.append_messages(session, pending)
    assert [message["id"] for message in session.messages] == [
        f"role:mira:{index}" for index in range(4)
    ]
    assert session.last_consolidated == 2


@pytest.mark.asyncio
async def test_failed_memory_write_preserves_persisted_and_cached_cursor(
    tmp_path: Path,
):
    manager, session, request = _setup(tmp_path)
    write = AsyncMock(side_effect=RuntimeError("memory write failed"))

    with pytest.raises(RuntimeError, match="memory write failed"):
        await manager.commit_consolidation(request, write)

    assert session.last_consolidated == 0
    manager.invalidate(session.key)
    assert manager.get_or_create(session.key).last_consolidated == 0


@pytest.mark.asyncio
async def test_failed_consumer_preserves_cursor_committed_after_memory_write(
    tmp_path: Path,
):
    manager, session, request = _setup(tmp_path)
    write = AsyncMock()
    publish = AsyncMock(side_effect=RuntimeError("memory consumer failed"))

    with pytest.raises(RuntimeError, match="memory consumer failed"):
        await manager.commit_consolidation(request, write, publish)

    write.assert_awaited_once()
    assert session.last_consolidated == 2
    manager.invalidate(session.key)
    assert manager.get_or_create(session.key).last_consolidated == 2


@pytest.mark.asyncio
async def test_context_cursors_commit_independently_and_repeat_is_rejected(
    tmp_path: Path,
):
    """角色会话两个游标各自条件提交：另一类游标变了不影响本类，重复提交不生效。"""
    manager, session, _ = _setup(tmp_path)
    manager._store.update_last_consolidated(session.key, 1)

    session.last_consolidated = 1
    manager.save(session)
    ids = tuple(message["id"] for message in session.messages)
    user = ConsolidationCommitRequest(
        session_key=session.key,
        expected_message_ids=ids,
        expected_context_cursors={"user": 1},
        context_cursors={"user": 2},
    )
    external = ConsolidationCommitRequest(
        session_key=session.key,
        expected_message_ids=ids,
        expected_context_cursors={"external": 1},
        context_cursors={"external": 2},
    )
    write = AsyncMock()

    # 旧会话首次提交：未推进的外部游标沿用原 last_consolidated。
    assert await manager.commit_consolidation(user, write) is True
    assert session.context_cursors == {
        "user": 2,
        "external": 1,
    }
    assert session.last_consolidated == 1
    assert await manager.commit_consolidation(user, write) is False
    assert await manager.commit_consolidation(external, write) is True
    assert await manager.commit_consolidation(external, write) is False
    assert write.await_count == 2
    manager.invalidate(session.key)
    reloaded = manager.get_or_create(session.key)
    assert reloaded.context_cursors == {
        "user": 2,
        "external": 2,
    }
    assert reloaded.last_consolidated == 2


@pytest.mark.asyncio
async def test_saving_a_stale_session_keeps_context_cursors(tmp_path: Path):
    """普通保存不碰按上下文游标：过期对象或别处改写元数据都抹不掉它们（#523）。"""
    manager, session, _ = _setup(tmp_path)
    ids = tuple(message["id"] for message in session.messages)
    stale = replace(session, messages=list(session.messages), metadata={})
    request = ConsolidationCommitRequest(
        session_key=session.key,
        expected_message_ids=ids,
        expected_context_cursors={"user": 0},
        context_cursors={"user": 2},
    )
    assert await manager.commit_consolidation(request, AsyncMock()) is True

    manager.save(stale)
    manager.invalidate(session.key)

    assert manager.get_or_create(session.key).context_cursors == {
        "user": 2,
        "external": 0,
    }


class _ConcurrentMemorizer:
    def __init__(self, store: CommittedMemory):
        self.store = store
        self.started = asyncio.Event()
        self.failed = asyncio.Event()
        self.release = threading.Event()
        self.finished = asyncio.Event()
        self.error = RuntimeError("first memory save failed")
        self.item_ids: list[str] = []
        self.loop = asyncio.get_running_loop()

    async def save_from_consolidation(
        self, history_entry: str, source_ref: str, **_kwargs: object
    ) -> None:
        if history_entry == "failure":
            await self.started.wait()
            self.failed.set()
            raise self.error
        await asyncio.to_thread(self._delayed_save, source_ref)

    def _delayed_save(self, source_ref: str) -> None:
        self.loop.call_soon_threadsafe(self.started.set)
        if not self.release.wait(timeout=5):
            raise TimeoutError("test did not release delayed memory write")
        result = self.store.upsert_item(
            memory_type="event",
            summary="delayed memory",
            embedding=[0.1, 0.2],
            source_ref=source_ref,
        )
        self.item_ids.append(result.split(":", 1)[1])
        self.loop.call_soon_threadsafe(self.finished.set)


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel_count", [0, 1, 2])
async def test_failed_parallel_consumer_settles_writes_before_undo_and_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cancel_count: int
):
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("role:mira")
    for index in range(3):
        session.add_message("user", f"question {index}")
        session.add_message("assistant", f"answer {index}")
    manager.save(session)
    message_ids = tuple(message["id"] for message in session.messages)
    store = CommittedMemory(message_ids)
    memorizer = _ConcurrentMemorizer(store)
    engine = store
    implicit = AsyncMock(return_value=None)

    async def consume(event):
        results = await asyncio.gather(
            *(
                memorizer.save_from_consolidation(entry, event.source_ref)
                for entry, _ in event.history_entry_payloads
            ),
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, BaseException):
                raise result
        await implicit()

    bus = EventBus()
    bus.on(ConsolidationCommitted, consume)
    event = ConsolidationCommitted(
        history_entry_payloads=[("failure", 0), ("delayed", 0)],
        source_ref=json.dumps(message_ids),
        scope_channel="desktop",
        scope_chat_id=session.key,
        conversation="question 2",
        role_id="mira",
    )

    async def publish():
        await bus.emit(event)

    def resolve_sources(message_ids: list[str]) -> list[str]:
        preview = engine.undo_by_message_sources(message_ids, dry_run=True)
        sources = preview["rollback_source_ids"]
        assert isinstance(sources, list)
        return [str(source) for source in sources]

    async def undo_session():
        result = await manager.undo_last_turn(
            session.key, rollback_source_resolver=resolve_sources
        )
        assert result is not None
        return engine.undo_by_message_sources(result.deleted_ids)

    task = asyncio.create_task(
        manager.commit_consolidation(
            ConsolidationCommitRequest(session.key, message_ids, 0, 6),
            AsyncMock(),
            publish,
        )
    )
    undo_task = None
    try:
        await asyncio.wait_for(memorizer.failed.wait(), timeout=2)
        for _ in range(cancel_count):
            task.cancel()
            await asyncio.sleep(0)
        undo_task = asyncio.create_task(undo_session())
        # Let the failing child, gather completion and queued undo all take their turns.
        for _ in range(5):
            await asyncio.sleep(0)
        assert not undo_task.done()
        assert not task.done()
        assert session.last_consolidated == 6
        assert len(session.messages) == 6
        memorizer.release.set()
        outcome, cleanup = await asyncio.wait_for(
            asyncio.gather(task, undo_task, return_exceptions=True), timeout=2
        )
        if cancel_count:
            assert isinstance(outcome, asyncio.CancelledError)
        else:
            assert isinstance(outcome, MemoryConsumersFailedError)
            assert outcome.__cause__ is memorizer.error
        assert isinstance(cleanup, dict)
        assert cleanup["affected_ids"] == memorizer.item_ids
        assert memorizer.finished.is_set()
        assert store.get_items_by_ids(memorizer.item_ids)[0]["status"] == "superseded"
        assert len(session.messages) == 4
        assert session.last_consolidated == 0
        implicit.assert_not_awaited()
        manager.invalidate(session.key)
        assert manager.get_or_create(session.key).last_consolidated == 0
    finally:
        memorizer.release.set()
        await asyncio.gather(
            task, *([undo_task] if undo_task else []), return_exceptions=True
        )
        await asyncio.wait_for(memorizer.finished.wait(), timeout=2)
        store.close()
        await bus.aclose()
