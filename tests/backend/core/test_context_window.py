"""Actual window maintenance preserves independent memory and visibility state."""

import asyncio
from dataclasses import replace

import pytest

from conversation.context_scope import (
    history_start,
    turn_context_view,
    user_context_view,
)
from conversation.service import desktop_thread_id, network_thread_id
from core.context_window import ContextWindowMaintenance
from core.memory.markdown import ConsolidateRequest, MarkdownMemoryStore
from session.manager.models import consolidation_cursor


def _turn(session, thread="", label="tea", tool=False):
    session.metadata.setdefault("role_id", "mira")
    session.add_message(
        "user",
        label,
        thread_id=thread,
        metadata={"message_source": {"sender_id": "friend", "group_name": thread}},
    )
    extra = (
        {
            "tool_chain": [
                {
                    "calls": [
                        {
                            "call_id": "one",
                            "name": "tool_search",
                            "arguments": {},
                            "result": "ok",
                            "unlocked": ["tea_tool"],
                        }
                    ]
                }
            ]
        }
        if tool
        else {}
    )
    session.add_message("assistant", "yes " + label, thread_id=thread, **extra)


@pytest.mark.asyncio
async def test_memory_alone_preserves_model_history_and_tools(memory_harness):
    h = memory_harness
    session = h.manager.get_or_create("cli:tea")
    _turn(session, tool=True)
    h.manager.save(session)
    original = session.get_history(start_index=history_start(session, None))
    result = await h.maintenance.consolidate(ConsolidateRequest(session, force=True))
    assert result.trace["mode"] == "markdown"
    assert session.last_consolidated == 2
    assert session.get_history(start_index=history_start(session, None)) == original
    assert session.get_history_tool_names(start_index=history_start(session, None)) == [
        "tool_search",
        "tea_tool",
    ]
    assert h.events[0].history_entry_payloads[0][1] == 3
    store = MarkdownMemoryStore(h.manager.workspace / "roles" / "mira")
    assert "tea" in store.read_recent_history()
    assert "tea" in store.read_recent_context()
    progress = session.maintenance_progress
    assert (
        progress.memory_version
        == progress.relationship_version
        == progress.recent_context_version
        == 1
    )
    # A stale ordinary save cannot restore old maintenance progress.
    h.manager.save(replace(session, last_consolidated=0, maintenance_progress=None))
    h.manager.invalidate(session.key)
    reloaded = h.manager.get_or_create(session.key)
    assert reloaded.last_consolidated == 2
    assert history_start(reloaded, None) == 0


@pytest.mark.asyncio
async def test_window_below_memory_threshold_fills_once_and_restores_after_restart(
    memory_harness,
):
    h = memory_harness
    session = h.manager.get_or_create("cli:tea")
    _turn(session, tool=True)
    _turn(session, label="more tea")
    h.manager.save(session)
    assert (await h.maintenance.consolidate(ConsolidateRequest(session))).trace[
        "mode"
    ] == "skipped"
    prepared = await h.manager.prepare_window(session.key, None, keep_count=2)
    assert prepared is not None
    window = ContextWindowMaintenance(h.manager, h.maintenance)
    result = await window.apply(prepared)
    assert result.committed and result.memory_committed
    assert session.last_consolidated == 2
    assert history_start(session, None) == 2
    assert (
        session.get_history_tool_names(start_index=history_start(session, None)) == []
    )
    calls = len(h.prompts)
    assert not (await window.apply(prepared)).committed
    assert len(h.prompts) == calls
    h.manager.invalidate(session.key)
    reloaded = h.manager.get_or_create(session.key)
    assert reloaded.last_consolidated == history_start(reloaded, None) == 2
    assert len(reloaded.messages) == 4


@pytest.mark.asyncio
async def test_interleaved_groups_fill_memory_category_without_compacting_other_windows(
    memory_harness,
):
    h = memory_harness
    session = h.manager.get_or_create("role:mira")
    a, b, stranger = [
        network_thread_id("mira", "qq", value) for value in ("a", "b", "stranger")
    ]
    for thread in (a, b, stranger, a, b, a):
        _turn(session, thread, "source " + thread)
    _turn(session, desktop_thread_id("mira"), "private user tea")
    h.manager.save(session)
    views = [
        turn_context_view(h.manager.workspace, "mira", thread)
        for thread in (a, b, stranger)
    ]
    prepared = await h.manager.prepare_window(session.key, views[0], keep_count=2)
    assert prepared is not None
    result = await ContextWindowMaintenance(h.manager, h.maintenance).apply(prepared)
    assert result.committed
    assert history_start(session, views[0]) > 0
    assert history_start(session, views[1]) == history_start(session, views[2]) == 0
    assert history_start(session, user_context_view(h.manager.workspace, "mira")) == 0
    assert consolidation_cursor(session, "user") == 0
    # The memory owner's external prefix includes interleaved B and stranger.
    prompts = "\n".join(h.prompts)
    assert "source " + b in prompts and "source " + stranger in prompts
    assert "private user tea" not in prompts
    assert not h.events  # External members cannot enter user memory2 extraction.


@pytest.mark.asyncio
async def test_both_failure_stages_and_retry_preserve_committed_memory(
    memory_harness, monkeypatch
):
    h = memory_harness
    session = h.manager.get_or_create("cli:failure")
    _turn(session)
    h.manager.save(session)
    prepared = await h.manager.prepare_window(session.key, None, keep_count=20)
    assert prepared is not None
    window = ContextWindowMaintenance(h.manager, h.maintenance)
    h.fail = True
    failed = await window.apply(prepared)
    assert not failed.committed and failed.failure_stage == "memory"
    assert session.last_consolidated == history_start(session, None) == 0
    h.fail = False
    commit = h.manager.commit_window

    async def reject(_prepared):
        raise RuntimeError("window persistence failed")

    monkeypatch.setattr(h.manager, "commit_window", reject)
    failed = await window.apply(prepared)
    assert failed.memory_committed and failed.failure_stage == "window"
    assert session.last_consolidated == 2 and history_start(session, None) == 0
    calls = len(h.prompts)
    monkeypatch.setattr(h.manager, "commit_window", commit)
    assert (await window.apply(prepared)).committed
    assert len(h.prompts) == calls


@pytest.mark.asyncio
async def test_consumer_failure_retries_durable_payload_without_extraction(
    memory_harness,
):
    h = memory_harness
    session = h.manager.get_or_create("cli:consumers")
    _turn(session)
    h.manager.save(session)

    async def failed_relationship(_session):
        raise RuntimeError("relationship failed")

    h.maintenance._after_consolidation = failed_relationship
    prepared = await h.manager.prepare_window(session.key, None, keep_count=20)
    assert prepared is not None
    window = ContextWindowMaintenance(h.manager, h.maintenance)
    failed = await window.apply(prepared)
    assert failed.memory_committed and failed.failure_stage == "consumers"
    assert history_start(session, None) == 0 and session.last_consolidated == 2
    assert session.maintenance_progress.relationship_version == 0
    assert session.maintenance_progress.published_version == 1
    assert session.maintenance_progress.pending_consumers["published"] is True
    calls = len(h.prompts)
    h.manager.invalidate(session.key)
    h.maintenance._after_consolidation = None
    assert (await window.apply(prepared)).committed
    assert len(h.prompts) == calls and len(h.events) == 1
    restored = h.manager.get_or_create(session.key).maintenance_progress
    assert restored.relationship_version == restored.memory_version
    assert not restored.pending_consumers and not restored.consumer_error


@pytest.mark.asyncio
async def test_concurrent_window_requests_share_memory_commit(memory_harness):
    h = memory_harness
    session = h.manager.get_or_create("cli:concurrent")
    _turn(session)
    h.manager.save(session)
    prepared = await h.manager.prepare_window(session.key, None, keep_count=0)
    assert prepared is not None
    window = ContextWindowMaintenance(h.manager, h.maintenance)
    results = await asyncio.gather(window.apply(prepared), window.apply(prepared))
    assert sum(result.committed for result in results) == 1
    assert len(h.events) == 1


@pytest.mark.asyncio
async def test_actual_window_storage_failure_keeps_cache_and_durable_cut(
    memory_harness, monkeypatch
):
    import json

    h = memory_harness
    session = h.manager.get_or_create("cli:storage-failure")
    _turn(session)
    h.manager.save(session)
    prepared = await h.manager.prepare_window(session.key, None, keep_count=0)
    assert prepared is not None
    original = h.manager._store.write_maintenance_progress

    def fail_window(key, payload, **kwargs):
        if json.loads(payload)["windows"]:
            raise OSError("window storage unavailable")
        return original(key, payload, **kwargs)

    monkeypatch.setattr(h.manager._store, "write_maintenance_progress", fail_window)
    window = ContextWindowMaintenance(h.manager, h.maintenance)
    for _ in range(2):
        result = await window.apply(prepared)
        assert result.failure_stage == "window" and result.memory_committed
        assert history_start(session, None) == 0
        assert session.maintenance_progress.windows == {}
        assert session.last_consolidated == 2
    calls = len(h.prompts)
    # A new manager reads the persisted retry contract, not the old Python cache.
    reopened = h.reopen_sessions()
    assert (
        await ContextWindowMaintenance(reopened, h.maintenance).apply(prepared)
    ).committed
    assert len(h.prompts) == calls and len(h.events) == 1
    assert history_start(reopened.get_or_create(session.key), None) == 2


@pytest.mark.asyncio
async def test_unpublished_memory_consumer_resumes_after_restart(memory_harness):
    from core.memory.events import ConsolidationCommitted

    h = memory_harness
    session = h.manager.get_or_create("cli:publication-retry")
    _turn(session)
    h.manager.save(session)
    failed = True
    received = []

    async def consumer(event):
        if failed:
            raise RuntimeError("memory2 unavailable")
        received.append(
            (event.source_ref, event.conversation, event.history_entry_payloads)
        )

    h.bus.on(ConsolidationCommitted, consumer)
    prepared = await h.manager.prepare_window(session.key, None, keep_count=0)
    assert prepared is not None
    result = await ContextWindowMaintenance(h.manager, h.maintenance).apply(prepared)
    assert result.failure_stage == "consumers" and result.memory_committed
    payload = session.maintenance_progress.pending_consumers
    assert session.maintenance_progress.published_version == 0
    calls = len(h.prompts)
    failed = False
    manager = h.reopen_sessions()
    assert (
        await ContextWindowMaintenance(manager, h.maintenance).apply(prepared)
    ).committed
    assert len(h.prompts) == calls
    assert received == [
        (
            payload["source_ref"],
            payload["conversation"],
            payload["history_entry_payloads"],
        )
    ]


@pytest.mark.asyncio
async def test_larger_retry_preserves_prior_memory_commit_when_consumer_still_fails(
    memory_harness,
):
    import json

    h = memory_harness
    session = h.manager.get_or_create("cli:larger-retry")
    _turn(session)
    h.manager.save(session)

    async def fail(_session):
        raise RuntimeError("relationship unavailable")

    h.maintenance._after_consolidation = fail
    first = await h.manager.prepare_window(session.key, None, keep_count=0)
    assert first is not None
    window = ContextWindowMaintenance(h.manager, h.maintenance)
    assert (await window.apply(first)).memory_committed
    calls = len(h.prompts)
    _turn(session, label="more tea")
    h.manager.save(session)
    larger = await h.manager.prepare_window(session.key, None, keep_count=0)
    assert larger is not None and larger.stop == 4
    retried = await window.apply(larger)
    assert not retried.committed and retried.failure_stage == "consumers"
    assert retried.memory_committed
    assert session.last_consolidated == 2 and history_start(session, None) == 0
    assert len(h.prompts) == calls and len(h.events) == 1
    assert not await h.manager.commit_window(larger)

    h.maintenance._after_consolidation = None
    assert (await window.apply(larger)).committed
    assert session.last_consolidated == history_start(session, None) == 4
    assert [json.loads(event.source_ref) for event in h.events] == [
        [m["id"] for m in session.messages[:2]],
        [m["id"] for m in session.messages[2:]],
    ]
