from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path
from typing import Any, cast

import pytest

from session.manager import SessionManager

_FRAME = '<system-reminder data-system-context-frame="true">内部</system-reminder>'


def _run(coro):
    return asyncio.run(coro)


def _add_turn(session, index: int, *, standalone_frame: bool = True) -> None:
    if standalone_frame:
        session.add_message("user", _FRAME)
    session.add_message(
        "user", f"u{index}", llm_context_frame=None if standalone_frame else _FRAME
    )
    session.add_message("assistant", f"a{index}")


def _saved_manager(
    tmp_path: Path, *, turns: int, standalone_frame: bool = True
) -> SessionManager:
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("cli:1")
    for index in range(turns):
        _add_turn(session, index, standalone_frame=standalone_frame)
    manager.save(session)
    return manager


def test_undo_deletes_context_user_assistant_three_rows(tmp_path: Path):
    manager = _saved_manager(tmp_path, turns=2)
    session = manager.get_or_create("cli:1")
    manager._store.update_last_consolidated(session.key, 6)

    session.last_consolidated = 6
    manager.save(session)

    result = _run(manager.undo_last_turn("cli:1"))

    assert result is not None
    assert result.deleted_ids == ["cli:1:3", "cli:1:4", "cli:1:5"]
    session = manager.get_or_create("cli:1")
    assert [m["content"] for m in session.messages] == [_FRAME, "u0", "a0"]
    assert session.last_consolidated == 3


def test_undo_uses_rollback_source_ids_for_consolidated_window_start(tmp_path: Path):
    manager = _saved_manager(tmp_path, turns=2)
    session = manager.get_or_create("cli:1")
    manager._store.update_last_consolidated(session.key, 6)

    session.last_consolidated = 6
    manager.save(session)

    result = _run(
        manager.undo_last_turn(
            "cli:1",
            rollback_source_resolver=lambda _: [
                "cli:1:0",
                "cli:1:1",
                "cli:1:2",
                "cli:1:3",
                "cli:1:4",
                "cli:1:5",
            ],
        )
    )

    assert result is not None
    assert result.last_consolidated_before == 6
    assert result.last_consolidated_after == 0


def test_undo_keeps_cursor_when_target_is_after_consolidated_prefix(tmp_path: Path):
    manager = _saved_manager(tmp_path, turns=3)
    session = manager.get_or_create("cli:1")
    manager._store.update_last_consolidated(session.key, 6)

    session.last_consolidated = 6
    manager.save(session)

    result = _run(manager.undo_last_turn("cli:1"))

    assert result is not None
    assert result.deleted_ids == ["cli:1:6", "cli:1:7", "cli:1:8"]
    assert manager.get_or_create("cli:1").last_consolidated == 6


def test_undo_deletes_user_assistant_when_frame_is_extra(tmp_path: Path):
    manager = _saved_manager(tmp_path, turns=1, standalone_frame=False)

    result = _run(manager.undo_last_turn("cli:1"))

    assert result is not None
    assert result.deleted_ids == ["cli:1:0", "cli:1:1"]
    assert manager.get_or_create("cli:1").messages == []


def test_undo_does_not_reuse_deleted_tail_message_ids(tmp_path: Path):
    manager = _saved_manager(tmp_path, turns=1)

    result = _run(manager.undo_last_turn("cli:1"))
    assert result is not None
    assert result.deleted_ids == ["cli:1:0", "cli:1:1", "cli:1:2"]

    session = manager.get_or_create("cli:1")
    _add_turn(session, 2, standalone_frame=False)
    manager.save(session)

    assert [m["id"] for m in session.messages] == ["cli:1:3", "cli:1:4"]


@pytest.mark.asyncio
async def test_undo_preserves_proactive_messages_and_incomplete_user(tmp_path: Path):
    manager = _saved_manager(tmp_path, turns=1)
    session = manager.get_or_create("cli:1")
    session.add_message("assistant", "proactive", proactive=True)
    session.add_message("user", "incomplete")
    manager.save(session)

    result = await manager.undo_last_turn(session.key)

    assert result is not None
    assert result.deleted_ids == ["cli:1:0", "cli:1:1", "cli:1:2"]
    assert [message["content"] for message in session.messages] == [
        "proactive",
        "incomplete",
    ]
    assert await manager.undo_last_turn(session.key) is None


@pytest.mark.asyncio
async def test_undo_deletes_context_frames_on_both_sides_of_user(tmp_path: Path):
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("cli:1")
    for role, content in [
        ("user", _FRAME),
        ("user", "question"),
        ("user", _FRAME),
        ("assistant", "answer"),
    ]:
        session.add_message(role, content)
    manager.save(session)

    result = await manager.undo_last_turn(session.key)

    assert result is not None
    assert len(result.deleted_ids) == 4
    assert session.messages == []
    manager.invalidate(session.key)
    assert manager.get_or_create(session.key).messages == []


@pytest.mark.asyncio
@pytest.mark.parametrize("append_first", [True, False])
async def test_concurrent_append_and_undo_use_committed_turn_and_keep_shared_cache(
    tmp_path: Path, append_first: bool
):
    manager = _saved_manager(tmp_path, turns=1)
    session = manager.get_or_create("cli:1")
    manager._store.update_last_consolidated(session.key, 3)

    session.last_consolidated = 3
    manager.save(session)
    # Match after_reasoning: mutate the shared Session, then queue append_messages.
    start = len(session.messages)
    _add_turn(session, 1)
    pending = session.messages[start:]
    async with manager._lock(session.key):
        operations = [
            lambda: manager.append_messages(session, pending),
            lambda: manager.undo_last_turn(session.key),
        ]
        if not append_first:
            operations.reverse()
        tasks = []
        for operation in operations:
            tasks.append(asyncio.create_task(operation()))
            await asyncio.sleep(0)
            assert not tasks[-1].done()
    results = await asyncio.gather(*tasks)
    undo_result = results[1 if append_first else 0]
    assert undo_result is not None
    expected_deleted = [
        f"cli:1:{index}" for index in (range(3, 6) if append_first else range(3))
    ]
    assert undo_result.deleted_ids == expected_deleted
    remaining_turn = 0 if append_first else 1
    assert manager.get_or_create(session.key) is session
    assert [message["content"] for message in session.messages] == [
        _FRAME,
        f"u{remaining_turn}",
        f"a{remaining_turn}",
    ]
    assert session.last_consolidated == (3 if append_first else 0)
    assert not set(expected_deleted) & {message["id"] for message in session.messages}
    # A subsequent save must not resurrect deleted rows or overwrite the new cursor.
    await manager.save_async(session)
    manager.invalidate(session.key)
    reloaded = manager.get_or_create(session.key)
    assert reloaded.messages == session.messages
    assert reloaded.last_consolidated == session.last_consolidated
    assert manager.peek_next_message_id(session.key) == "cli:1:6"


@pytest.mark.asyncio
async def test_undo_resolver_failure_preserves_cache_cursor_and_disk(tmp_path: Path):
    manager = _saved_manager(tmp_path, turns=1)
    session = manager.get_or_create("cli:1")
    manager._store.update_last_consolidated(session.key, 3)

    session.last_consolidated = 3
    manager.save(session)
    before = list(session.messages)

    def fail_resolver(message_ids: list[str]) -> list[str]:
        assert message_ids == ["cli:1:0", "cli:1:1", "cli:1:2"]
        raise RuntimeError("memory preview unavailable")

    with pytest.raises(RuntimeError, match="memory preview unavailable"):
        await manager.undo_last_turn(
            session.key, rollback_source_resolver=fail_resolver
        )

    assert session.messages == before
    assert session.last_consolidated == 3
    manager.invalidate(session.key)
    assert manager.get_or_create(session.key).messages == before


@pytest.mark.asyncio
async def test_undo_refreshes_thread_projection_after_last_turn_deleted(tmp_path: Path):
    from conversation.service import ConversationService, LegacySessionDescriptor

    manager = SessionManager(tmp_path)
    thread = ConversationService(manager).ensure_thread_for_session(
        LegacySessionDescriptor(
            session_key="telegram:1", role_id="mira", channel="telegram", chat_id="1"
        )
    )
    session = manager.get_or_create("role:mira")
    session.add_message("user", "question", thread_id=thread.id)
    session.add_message("assistant", "answer", thread_id=thread.id)
    manager.save(session)
    before = manager.conversation_store.get_thread_state(thread.id)
    assert before is not None and before.metadata["message_count"] == 2

    await manager.undo_last_turn(session.key)

    after = manager.conversation_store.get_thread_state(thread.id)
    assert after is not None
    assert after.metadata["message_count"] == 0
    assert after.metadata["last_message_at"] == ""


@pytest.mark.asyncio
async def test_undo_projection_failure_rolls_back_messages_cursor_all_states_and_cache(
    tmp_path: Path,
):
    from conversation.service import ConversationService, LegacySessionDescriptor

    manager = SessionManager(tmp_path)
    thread = ConversationService(manager).ensure_thread_for_session(
        LegacySessionDescriptor(
            session_key="telegram:1", role_id="mira", channel="telegram", chat_id="1"
        )
    )
    session = manager.get_or_create("role:mira")
    session.add_message("user", "question", thread_id=thread.id)
    session.add_message("assistant", "answer", thread_id=thread.id)
    manager._store.update_last_consolidated(session.key, 2)

    session.last_consolidated = 2
    manager.save(session)
    before_messages = list(session.messages)
    before_updated = session.updated_at
    before_meta = manager._store.get_session_meta(session.key)
    store = manager.conversation_store
    before_states = (
        store.get_thread_state(thread.id),
        store.get_contact_state(thread.contact_id),
        store.get_role_state(thread.role_id),
    )
    # Fail the third projection write after thread and contact have already changed.
    manager._store._conn.execute(
        "CREATE TRIGGER fail_undo_role BEFORE INSERT ON role_state BEGIN SELECT RAISE(ABORT, 'projection failed'); END"
    )
    manager._store._conn.commit()

    with pytest.raises(sqlite3.IntegrityError, match="projection failed"):
        await manager.undo_last_turn(session.key)

    assert manager.get_or_create(session.key) is session
    assert session.messages == before_messages
    assert session.last_consolidated == 2
    assert session.updated_at == before_updated
    assert manager._store.get_session_meta(session.key) == before_meta
    assert (
        store.get_thread_state(thread.id),
        store.get_contact_state(thread.contact_id),
        store.get_role_state(thread.role_id),
    ) == before_states
    manager.invalidate(session.key)
    reloaded = manager.get_or_create(session.key)
    assert reloaded.messages == before_messages
    assert reloaded.last_consolidated == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("cursors", "expected"),
    [
        # 删掉的桌面回合已整理：用户游标退回重新整理，外部游标不动。
        ({"user": 8, "external": 4}, {"user": 6, "external": 4}),
        # 删掉的桌面回合未整理：用户游标不动，外部游标随删除平移。
        ({"user": 4, "external": 8}, {"user": 4, "external": 6}),
    ],
)
async def test_undo_rolls_back_each_context_cursor(
    tmp_path: Path, cursors: dict[str, int], expected: dict[str, int]
):
    from conversation.service import desktop_thread_id, network_thread_id

    manager = SessionManager(tmp_path)
    session = manager.get_or_create("role:mira")
    group = network_thread_id("mira", "qq", "g1")
    desktop = desktop_thread_id("mira")
    for index, thread_id in enumerate((group, desktop, group, desktop)):
        session.add_message("user", f"u{index}", thread_id=thread_id)
        session.add_message("assistant", f"a{index}", thread_id=thread_id)
    manager.save(session)
    manager._store.update_last_consolidated(
        session.key, min(cursors.values()), context_cursors=cast(Any, cursors)
    )
    manager.invalidate(session.key)

    result = await manager.undo_last_turn(session.key)

    assert result is not None
    assert result.deleted_ids == ["role:mira:6", "role:mira:7"]
    manager.invalidate(session.key)
    reloaded = manager.get_or_create(session.key)
    assert reloaded.context_cursors == expected
    assert reloaded.last_consolidated == min(expected.values())
    assert result.last_consolidated_after == min(expected.values())


@pytest.mark.asyncio
async def test_undo_ignores_memory_sources_from_the_other_context(tmp_path: Path):
    """另一类上下文的记忆来源不会把本类游标多拉回（#523）。"""
    from conversation.service import desktop_thread_id, network_thread_id

    manager = SessionManager(tmp_path)
    session = manager.get_or_create("role:mira")
    group = network_thread_id("mira", "qq", "g1")
    desktop = desktop_thread_id("mira")
    for index, thread_id in enumerate((group, desktop, group, desktop)):
        session.add_message("user", f"u{index}", thread_id=thread_id)
        session.add_message("assistant", f"a{index}", thread_id=thread_id)
    manager.save(session)
    manager._store.update_last_consolidated(
        session.key, 8, context_cursors={"user": 8, "external": 8}
    )
    manager.invalidate(session.key)

    result = await manager.undo_last_turn(
        session.key,
        rollback_source_resolver=lambda _ids: ["role:mira:0", "role:mira:6"],
    )

    assert result is not None
    reloaded = manager.get_or_create(session.key)
    assert reloaded.context_cursors == {"user": 6, "external": 6}


@pytest.mark.asyncio
async def test_undo_before_a_legacy_cut_invalidates_like_an_explicit_window(
    tmp_path: Path,
):
    from conversation.context_scope import (
        history_start,
        turn_context_view,
        user_context_view,
    )
    from conversation.service import desktop_thread_id, network_thread_id

    manager = SessionManager(tmp_path)
    session = manager.get_or_create("role:mira")
    group = network_thread_id("mira", "qq", "g1")
    desktop = desktop_thread_id("mira")
    for index, thread_id in enumerate((group, desktop, group, desktop)):
        session.add_message("user", f"u{index}", thread_id=thread_id)
        session.add_message("assistant", f"a{index}", thread_id=thread_id)
    manager.save(session)
    manager._store.update_last_consolidated(
        session.key, 8, context_cursors={"user": 8, "external": 8}
    )
    manager.invalidate(session.key)

    assert await manager.undo_last_turn(session.key) is not None

    session = manager.get_or_create(session.key)
    # The undone desktop turn sat before the frozen user cut: that window restarts.
    assert history_start(session, user_context_view(tmp_path, "mira")) == 0
    # The group context lost nothing; its frozen cut only shifts.
    assert history_start(session, turn_context_view(tmp_path, "mira", group)) == 6
