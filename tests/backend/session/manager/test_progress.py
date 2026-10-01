"""Legacy migration freezes all initial windows before memory can advance."""

from unittest.mock import AsyncMock
import pytest

from conversation.context_scope import history_start, turn_context_view
from conversation.service import network_thread_id
from session.manager import Session, SessionManager
from session.manager.consolidation import ConsolidationCommitRequest


@pytest.mark.asyncio
async def test_late_first_read_of_other_group_uses_frozen_legacy_cut(tmp_path):
    manager = SessionManager(tmp_path)
    a, b = [network_thread_id("mira", "qq", name) for name in ("a", "b")]
    legacy = Session("role:mira", last_consolidated=2)
    for thread in (a, b, a, b, a, b):
        legacy.add_message("user", thread, thread_id=thread)
        legacy.add_message("assistant", "reply", thread_id=thread)
    manager.save(legacy)
    manager._store.update_last_consolidated(
        legacy.key, 2, context_cursors={"user": 2, "external": 4}
    )
    session = manager.get_or_create(legacy.key)
    view_a = turn_context_view(tmp_path, "mira", a)
    assert history_start(session, view_a) == 4
    request = ConsolidationCommitRequest(
        session.key,
        tuple(m["id"] for m in session.messages),
        expected_context_cursors={"external": 4},
        context_cursors={"external": 12},
    )
    assert await manager.commit_consolidation(request, AsyncMock())
    manager.invalidate(session.key)
    restored = manager.get_or_create(session.key)
    view_b = turn_context_view(tmp_path, "mira", b)
    assert history_start(restored, view_b) == 4
    first = restored.get_history(
        start_index=history_start(restored, view_b), include=view_b.includes
    )
    assert len(first) == 4
    raw = manager._store.get_session_meta(session.key)["maintenance_progress"]
    manager.invalidate(session.key)
    assert history_start(manager.get_or_create(session.key), view_b) == 4
    assert manager._store.get_session_meta(session.key)["maintenance_progress"] == raw
