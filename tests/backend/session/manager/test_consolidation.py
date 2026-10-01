"""Session-owned validation and persistence for prepared memory commits."""

import asyncio
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from session.manager import ConsolidationCommitRequest, SessionManager


@pytest.mark.asyncio
async def test_cursor_persistence_failure_rolls_back_private_progress(
    tmp_path, monkeypatch
):
    manager, session, request = _setup(tmp_path)
    before = manager._store.get_session_meta(session.key)["maintenance_progress"]

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
