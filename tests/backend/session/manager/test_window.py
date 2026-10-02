"""Session-owned prefix, scope, generation and version preconditions."""

import pytest
from unittest.mock import AsyncMock

from conversation.context_scope import (
    history_start,
    turn_context_view,
    user_context_view,
)
from conversation.service import desktop_thread_id, network_thread_id
from core.identity import UserIdentityStore, IdentityChat
from core.accounts import AccountRecord
from session.manager import SessionManager
from session.manager.consolidation import ConsolidationCommitRequest


def _session(tmp_path):
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("role:mira")
    for index in range(3):
        session.add_message("user", str(index), thread_id=desktop_thread_id("mira"))
        session.add_message(
            "assistant", str(index), thread_id=desktop_thread_id("mira")
        )
    manager.save(session)
    return manager, session, user_context_view(tmp_path, "mira")


async def _memory(manager, session):
    request = ConsolidationCommitRequest(
        session.key,
        tuple(m["id"] for m in session.messages),
        expected_context_cursors={"user": 0},
        context_cursors={"user": len(session.messages)},
    )
    assert await manager.commit_consolidation(request, AsyncMock())


@pytest.mark.asyncio
async def test_append_after_prepare_is_not_compacted_and_duplicate_commit_is_stale(
    tmp_path,
):
    manager, session, view = _session(tmp_path)
    prepared = await manager.prepare_window(session.key, view, keep_turns=1)
    assert prepared is not None
    await _memory(manager, session)
    session.add_message("user", "concurrent", thread_id=desktop_thread_id("mira"))
    await manager.save_async(session)
    assert await manager.commit_window(prepared, "state", prepared.removed_message_ids)
    assert not await manager.commit_window(
        prepared, "state", prepared.removed_message_ids
    )
    assert history_start(session, view) == 4
    assert session.get_history(
        start_index=history_start(session, view), include=view.includes
    )[-1]["content"].endswith("concurrent")
    assert len(manager._store.fetch_session_messages(session.key)) == 7


@pytest.mark.asyncio
async def test_invalidation_keeps_originals_and_rejects_old_preparation(tmp_path):
    manager, session, view = _session(tmp_path)
    prepared = await manager.prepare_window(session.key, view, keep_turns=0)
    assert prepared is not None
    await _memory(manager, session)
    assert await manager.commit_window(prepared, "state", prepared.removed_message_ids)
    ids = [m["id"] for m in session.messages]
    await manager.invalidate_maintenance(session.key)
    assert history_start(session, view) == session.last_consolidated == 0
    assert not await manager.commit_window(
        prepared, "state", prepared.removed_message_ids
    )
    assert [m["id"] for m in manager._store.fetch_session_messages(session.key)] == ids


@pytest.mark.asyncio
async def test_user_shares_window_with_bound_private_and_binding_change_invalidates(
    tmp_path,
):
    manager, session, _view = _session(tmp_path)
    identities = UserIdentityStore(tmp_path)
    # Use the identity store's real binding API, not a synthetic view stamp.
    record = AccountRecord(
        id="qq:101",
        plugin_id="qq",
        platform="qq",
        platform_account_id="101",
        config_ref="101",
        role_id="mira",
    )
    identity = identities.pair(
        identities.create_pairing_code().code,
        record=record,
        user_id="owner",
        scope="platform",
        chat=IdentityChat(record.id, "qq", "owner"),
    )
    assert identity is not None
    session = manager.get_or_create(session.key)
    view = user_context_view(tmp_path, "mira")
    private = turn_context_view(
        tmp_path, "mira", network_thread_id("mira", "qq", "owner")
    )
    prepared = await manager.prepare_window(session.key, view, keep_turns=0)
    assert prepared is not None
    await _memory(manager, session)
    assert await manager.commit_window(prepared, "state", prepared.removed_message_ids)
    assert history_start(session, private) == history_start(session, view) == 6
    identities.unbind(identity.id)
    changed = user_context_view(tmp_path, "mira")
    assert history_start(session, changed) == 0
    session = manager.get_or_create(session.key)
    assert session.context_cursors == {"user": 0, "external": 0}
    assert not await manager.commit_window(
        prepared, "state", prepared.removed_message_ids
    )
    with pytest.raises(ValueError, match="身份归属"):
        await manager.prepare_window(session.key, view, keep_turns=0)


@pytest.mark.asyncio
async def test_chat_turn_undo_invalidates_windows_and_prepared_versions(tmp_path):
    manager, session, view = _session(tmp_path)
    prepared = await manager.prepare_window(session.key, view, keep_turns=0)
    assert prepared is not None
    await _memory(manager, session)
    assert await manager.commit_window(prepared, "state", prepared.removed_message_ids)
    assert await manager.undo_last_turn(session.key) is not None
    assert history_start(session, view) == 0
    assert not await manager.commit_window(
        prepared, "state", prepared.removed_message_ids
    )
    assert len(session.messages) == 4  # Only the explicitly undone turn is removed.


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    [
        ("content", "rewritten"),
        (
            "tool_calls",
            [{"id": "changed", "function": {"name": "changed", "arguments": "{}"}}],
        ),
        ("tool_call_id", "changed-result-owner"),
        ("llm_user_content", "changed visible content"),
        ("reasoning_content", "changed reasoning"),
        ("proactive", True),
        (
            "metadata",
            {"message_source": {"sender_is_user": True, "sender_id": "changed"}},
        ),
    ],
)
async def test_same_id_semantic_rewrite_rejects_prepared_window(tmp_path, field, value):
    manager, session, view = _session(tmp_path)
    prepared = await manager.prepare_window(session.key, view, keep_turns=1)
    assert prepared is not None
    await _memory(manager, session)
    original_id = session.messages[0]["id"]
    session.messages[0][field] = value
    manager.save(session)
    assert session.messages[0]["id"] == original_id
    assert not await manager.commit_window(
        prepared, "state", prepared.removed_message_ids
    )
    assert history_start(session, view) == 0


@pytest.mark.asyncio
async def test_model_switch_invalidates_summary_and_cut_but_keeps_memory(tmp_path):
    manager, session, view = _session(tmp_path)
    await manager.bind_window_request(session.key, view, "connection:model-a")
    prepared = await manager.prepare_window(session.key, view, keep_turns=1)
    assert prepared is not None
    await _memory(manager, session)
    assert await manager.commit_window(prepared, "state", prepared.removed_message_ids)
    await manager.bind_window_request(session.key, view, "connection:model-b")
    assert history_start(session, view) == 0
    assert not session.maintenance_progress.summaries
    assert session.context_cursors["user"] == 6
    assert not await manager.commit_window(
        prepared, "state", prepared.removed_message_ids
    )


@pytest.mark.asyncio
async def test_window_write_failure_cannot_publish_only_summary_or_cut(
    tmp_path, monkeypatch
):
    manager, session, view = _session(tmp_path)
    prepared = await manager.prepare_window(session.key, view, keep_turns=0)
    assert prepared is not None
    await _memory(manager, session)
    previous = session.maintenance_progress.dump()

    def fail(*args):
        raise OSError("disk unavailable")

    monkeypatch.setattr(manager._store, "write_maintenance_progress", fail)
    with pytest.raises(OSError):
        await manager.commit_window(prepared, "new state", prepared.removed_message_ids)
    assert session.maintenance_progress.dump() == previous
    assert history_start(session, view) == 0
