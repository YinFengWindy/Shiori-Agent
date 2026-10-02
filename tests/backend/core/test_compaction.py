"""Compaction publishes only validated complete windows after real memory work."""

from types import SimpleNamespace
import asyncio
from unittest.mock import AsyncMock

import pytest

from agent.prompting.input_budget import BudgetPolicy, build_input_budget
from agent.prompting.token_estimate import estimate_tokens
from agent.prompting.usage_anchor import InputEstimate
from conversation.context_scope import (
    history_start,
    turn_context_view,
    user_context_view,
)
from conversation.service import network_thread_id, desktop_thread_id
from core.compaction import (
    CompactionController,
    CompactionFailedError,
    CompactionPolicy,
)
from core.compaction_summary import WorkingSummary
from core.memory.markdown import ConsolidateRequest
from session.manager import SessionManager
from session.maintenance_progress import window_key


async def test_controller_rejects_duplicate_non_role_session_before_summary(
    memory_harness,
):
    h = memory_harness
    session = h.manager.get_or_create("cli:duplicate")
    _turn(session)
    h.manager.save(session)
    entered, release = asyncio.Event(), asyncio.Event()

    async def summary(prepared):
        entered.set()
        await release.wait()
        return WorkingSummary("task", prepared.removed_message_ids)

    controller = _controller(h, summary)
    first = asyncio.create_task(_ensure(controller, session, keep=0))
    try:
        await asyncio.wait_for(entered.wait(), 2)
        with pytest.raises(CompactionFailedError) as error:
            await _ensure(controller, session, keep=0)
        assert error.value.result.failure_stage == "busy"
        assert controller.writer.generate.await_count == 1
        release.set()
        await first
        assert not controller.is_busy(session.key)
    finally:
        release.set()
        await first


def _turn(session, label="tea", thread=""):
    session.metadata["role_id"] = "mira"
    session.add_message(
        "user",
        label,
        thread_id=thread,
        metadata={"message_source": {"sender_id": "friend", "group_name": thread}},
    )
    session.add_message("assistant", "done", thread_id=thread)


def _budget(tokens):
    return build_input_budget(
        context_window_tokens=4000,
        max_output_tokens=200,
        output_tokens=200,
        policy=BudgetPolicy(safety_margin_tokens=20),
        estimate=InputEstimate(tokens, "local"),
    )


def _controller(h, generate=None):
    async def summary(prepared):
        return WorkingSummary(
            "tasks: finish the tea plan", prepared.removed_message_ids
        )

    writer = SimpleNamespace(
        model_name="controlled", generate=AsyncMock(side_effect=generate or summary)
    )
    return CompactionController(h.manager, h.maintenance, writer)


async def _ensure(controller, session, *, view=None, keep=2, render=None, measure=None):
    async def project(prepared, summary):
        return [
            {"role": "system", "content": summary},
            *session.get_history(
                start_index=prepared.stop, include=view.includes if view else None
            ),
            {"role": "user", "content": "current"},
        ]

    return await controller.ensure(
        session_key=session.key,
        view=view,
        policy=CompactionPolicy(keep),
        message_limit=len(session.messages),
        budget=_budget(3500),
        render=render or project,
        measure=measure or (lambda messages: _budget(estimate_tokens(messages))),
    )


@pytest.mark.parametrize("keep", [0, 1, 2, 4])
async def test_policy_preserves_complete_turns_then_appends_until_next_compaction(
    memory_harness, keep
):
    h = memory_harness
    session = h.manager.get_or_create("cli:retention")
    for index in range(6):
        _turn(session, f"tea {index}")
    h.manager.save(session)
    controller = _controller(h)
    messages, result = await _ensure(controller, session, keep=keep)
    assert result.committed and result.retained_turns == keep
    assert result.memory_committed
    assert history_start(session, None) == 12 - keep * 2
    assert (
        session.maintenance_progress.summaries["session"]
        == "tasks: finish the tea plan"
    )
    old_cut = history_start(session, None)
    _turn(session, "new tea")
    h.manager.save(session)
    assert history_start(session, None) == old_cut
    assert len(session.get_history(start_index=old_cut)) == keep * 2 + 2
    reloaded = SessionManager(h.manager.workspace).get_or_create(session.key)
    assert (
        reloaded.maintenance_progress.summaries
        == session.maintenance_progress.summaries
    )
    assert len(messages) == keep * 2 + 2


async def test_budget_reduces_turns_and_expands_memory_prerequisite(memory_harness):
    h = memory_harness
    session = h.manager.get_or_create("cli:reduce")
    for _ in range(4):
        _turn(session)
    h.manager.save(session)
    controller = _controller(h)
    candidates = []

    async def render(prepared, summary):
        candidates.append((prepared.stop, session.last_consolidated))
        return [
            {"role": "user", "content": "current", "retained": prepared.retained_turns}
        ]

    _, result = await _ensure(
        controller,
        session,
        render=render,
        measure=lambda messages: _budget(500 + messages[0]["retained"] * 1000),
    )
    assert candidates == [(4, 4), (6, 6)]
    assert result.retained_turns == 1 and result.after_tokens == 1500
    assert session.last_consolidated == history_start(session, None) == 6
    assert controller.writer.generate.await_count == 2


async def test_zero_retention_over_budget_preserves_memory_without_publishing_window(
    memory_harness,
):
    h = memory_harness
    session = h.manager.get_or_create("cli:fail")
    _turn(session)
    h.manager.save(session)
    controller = _controller(h)
    with pytest.raises(CompactionFailedError) as caught:
        await _ensure(controller, session, measure=lambda _: _budget(3000))
    result = caught.value.result
    assert result.failure_stage == "budget" and result.memory_committed
    assert session.last_consolidated == 2 and history_start(session, None) == 0
    assert not session.maintenance_progress.summaries
    calls = len(h.prompts)
    await _ensure(controller, session, keep=0)
    assert len(h.prompts) == calls


@pytest.mark.parametrize("stage", ["summary", "validation", "window"])
async def test_downstream_failure_keeps_committed_memory_and_retries_without_extraction(
    memory_harness, monkeypatch, stage
):
    h = memory_harness
    session = h.manager.get_or_create("cli:downstream")
    _turn(session)
    h.manager.save(session)
    controller = _controller(h)

    async def fail(*args):
        raise RuntimeError("controlled failure")

    original = h.manager.commit_window
    render = None
    if stage == "summary":
        controller.writer.generate.side_effect = fail
    elif stage == "validation":
        render = fail
    else:
        monkeypatch.setattr(h.manager, "commit_window", fail)
    with pytest.raises(CompactionFailedError) as caught:
        await _ensure(controller, session, keep=0, render=render)
    assert caught.value.result.failure_stage == stage
    assert caught.value.result.memory_committed
    assert (
        session.maintenance_progress.relationship_version
        == session.maintenance_progress.memory_version
        == 1
    )
    assert (
        history_start(session, None) == 0 and not session.maintenance_progress.summaries
    )
    count = len(h.prompts)
    monkeypatch.setattr(h.manager, "commit_window", original)
    await _ensure(_controller(h), session, keep=0)
    assert len(h.prompts) == count


async def test_memory_failure_never_generates_or_publishes_a_summary(memory_harness):
    h = memory_harness
    session = h.manager.get_or_create("cli:memory-fail")
    _turn(session)
    h.manager.save(session)
    h.fail = True
    controller = _controller(h)
    with pytest.raises(CompactionFailedError) as caught:
        await _ensure(controller, session, keep=0)
    assert caught.value.result.failure_stage == "memory"
    assert not caught.value.result.memory_committed
    controller.writer.generate.assert_not_awaited()
    assert history_start(session, None) == 0


async def test_memory_only_keeps_the_window_and_semantic_consumers(memory_harness):
    h = memory_harness
    session = h.manager.get_or_create("cli:memory-only")
    _turn(session)
    h.manager.save(session)
    original = session.get_history(start_index=0)
    result = await h.maintenance.consolidate(ConsolidateRequest(session, force=True))
    assert result.trace["mode"] == "markdown"
    assert session.get_history(start_index=history_start(session, None)) == original
    assert session.maintenance_progress.recent_context_version == 1
    assert session.maintenance_progress.relationship_version == 1
    assert len(h.events) == 1


async def test_external_windows_are_isolated_while_memory_covers_interleaved_prefix(
    memory_harness,
):
    h = memory_harness
    session = h.manager.get_or_create("role:mira")
    a, b = [network_thread_id("mira", "qq", value) for value in ("a", "b")]
    for thread in (a, b, a, b, a):
        _turn(session, "tea " + thread, thread)
    _turn(session, "private tea", desktop_thread_id("mira"))
    h.manager.save(session)
    av, bv = [
        turn_context_view(h.manager.workspace, "mira", thread) for thread in (a, b)
    ]
    _, result = await _ensure(_controller(h), session, view=av, keep=1)
    assert result.committed
    assert history_start(session, av) == 8
    assert (
        history_start(session, bv)
        == history_start(session, user_context_view(h.manager.workspace, "mira"))
        == 0
    )
    assert set(session.maintenance_progress.summaries) == {window_key(av)}
    assert b in " ".join(h.prompts) and "private tea" not in " ".join(h.prompts)
    assert not h.events


async def test_rewritten_summary_receives_old_state_and_preserves_old_provenance(
    memory_harness,
):
    h = memory_harness
    session = h.manager.get_or_create("cli:rewrite")
    _turn(session)
    h.manager.save(session)
    await _ensure(_controller(h), session, keep=0)
    first_ids = tuple(session.maintenance_progress.summary_source_ids["session"])
    _turn(session, "another step")
    h.manager.save(session)

    async def rewrite(prepared):
        assert (
            session.maintenance_progress.summaries["session"]
            == "tasks: finish the tea plan"
        )
        return WorkingSummary(
            "tasks: finish the tea plan; next step",
            first_ids + prepared.removed_message_ids,
        )

    await _ensure(_controller(h, rewrite), session, keep=0)
    assert (
        session.maintenance_progress.summaries["session"]
        == "tasks: finish the tea plan; next step"
    )
    assert session.maintenance_progress.summary_source_ids["session"] == [
        m["id"] for m in session.messages
    ]


async def test_stale_window_commit_reports_successful_memory_without_publication(
    memory_harness,
):
    h = memory_harness
    session = h.manager.get_or_create("cli:stale")
    _turn(session)
    h.manager.save(session)

    async def render(prepared, summary):
        await h.manager.bind_window_request(session.key, None, "new-model")
        return [{"role": "system", "content": summary}]

    await h.manager.bind_window_request(session.key, None, "old-model")
    with pytest.raises(CompactionFailedError) as caught:
        await _ensure(_controller(h), session, keep=0, render=render)
    assert caught.value.result.failure_stage == "window"
    assert caught.value.result.memory_committed
    assert history_start(session, None) == 0
    assert not session.maintenance_progress.summaries


async def test_consumer_failure_retains_memory_and_pending_work(memory_harness):
    h = memory_harness
    session = h.manager.get_or_create("cli:consumer-fail")
    _turn(session)
    h.manager.save(session)
    h.maintenance._after_consolidation = AsyncMock(
        side_effect=RuntimeError("relationship unavailable")
    )
    controller = _controller(h)
    with pytest.raises(CompactionFailedError) as caught:
        await _ensure(controller, session, keep=0)
    assert caught.value.result.failure_stage == "consumers"
    assert (
        caught.value.result.memory_committed and caught.value.result.memory_cursor == 2
    )
    controller.writer.generate.assert_not_awaited()
    calls = len(h.prompts)
    h.maintenance._after_consolidation = AsyncMock()
    await _ensure(controller, session, keep=0)
    assert len(h.prompts) == calls
    assert session.maintenance_progress.relationship_version == 1
