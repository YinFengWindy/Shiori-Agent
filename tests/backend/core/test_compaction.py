"""Compaction publishes only validated complete windows after real memory work."""

from types import SimpleNamespace
import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from agent.prompting.input_budget import BudgetPolicy, build_input_budget
from agent.prompting.token_estimate import estimate_tokens
from agent.prompting.usage_anchor import InputEstimate
from agent.provider import LLMProvider
from conversation.context_scope import (
    history_start,
    turn_context_view,
    user_context_view,
)
from conversation.service import desktop_thread_id
from shiori_sdk.channels.threads import network_thread_id
from core.compaction import (
    CompactionController,
    CompactionFailedError,
    CompactionPolicy,
)
from core.compaction_summary import WorkingSummary, WorkingSummaryWriter
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


def _advance_generation(h, session_key):
    """Simulate an undo/rebinding that lands while the controller is working."""
    progress = h.manager.maintenance_progress(h.manager.get_or_create(session_key))
    progress.generation += 1
    h.manager._store.write_maintenance_progress(session_key, progress.dump())


def _budget(tokens):
    return build_input_budget(
        model_context_window=4000,
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


async def test_budget_estimates_turns_before_memory_and_summarizes_once(
    memory_harness,
):
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
    # Local estimates without memory work, then one real render.
    assert candidates == [(4, 0), (6, 0), (8, 0), (6, 6)]
    assert result.retained_turns == 1 and result.after_tokens == 1500
    assert result.retained_reduction_reason == "budget"
    assert session.last_consolidated == history_start(session, None) == 6
    assert controller.writer.generate.await_count == 1


async def test_over_target_within_hard_limit_commits_most_turns_without_degrading(
    memory_harness,
):
    h = memory_harness
    session = h.manager.get_or_create("cli:hard-limit")
    for _ in range(4):
        _turn(session)
    h.manager.save(session)
    controller = _controller(h)
    minimal = AsyncMock(return_value=[])

    async def render(prepared, summary):
        return [{"role": "user", "content": "x", "retained": prepared.retained_turns}]

    # Target 1600, hard limit 3780; estimates add the 2000-token summary limit:
    # 2 turns exceed the limit, 1 turn only the target.
    _, result = await controller.ensure(
        session_key=session.key,
        view=None,
        policy=CompactionPolicy(2),
        message_limit=len(session.messages),
        budget=_budget(3500),
        render=render,
        render_minimal=minimal,
        measure=lambda messages: _budget(
            3900 if messages[0]["retained"] == 2 else 1700
        ),
    )
    assert result.committed and not result.degraded and not result.tools_disabled
    assert result.retained_turns == 1 and result.after_tokens == 1700
    assert history_start(session, None) == 6
    assert controller.writer.generate.await_count == 1
    minimal.assert_not_awaited()


async def test_zero_retention_over_budget_preserves_memory_without_publishing_window(
    memory_harness,
):
    h = memory_harness
    session = h.manager.get_or_create("cli:fail")
    _turn(session)
    h.manager.save(session)
    controller = _controller(h)
    with pytest.raises(CompactionFailedError) as caught:
        await _ensure(controller, session, measure=lambda _: _budget(3900))
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

    async def fail_rendering_summary(prepared, summary):
        if summary == "tasks: finish the tea plan":
            raise RuntimeError("controlled failure")
        return [{"role": "user", "content": "current"}]

    if stage == "summary":
        controller.writer.generate.side_effect = fail
    elif stage == "validation":
        render = fail_rendering_summary
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


async def test_truncated_summary_retry_commits_window_without_repeating_memory(
    memory_harness, monkeypatch
):
    h = memory_harness
    session = h.manager.get_or_create("cli:truncated-summary")
    _turn(session)
    h.manager.save(session)
    provider = LLMProvider(
        api_key="test",
        provider_name="StepFun",
        model_context_window=1000000,
        default_max_tokens=16384,
    )
    content = json.dumps(
        {
            "tasks": "finish the tea plan",
            "constraints": "",
            "decisions": "",
            "unfinished": "",
            "tool_state": "",
            "entities": "",
            "source_message_ids": [session.messages[0]["id"]],
        }
    )

    async def complete(**kwargs):
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=content, tool_calls=[]),
                    finish_reason="length" if kwargs["max_tokens"] <= 2000 else "stop",
                )
            ],
            usage=None,
        )

    create = AsyncMock(side_effect=complete)
    monkeypatch.setattr(provider._client.chat.completions, "create", create)
    controller = CompactionController(
        h.manager,
        h.maintenance,
        WorkingSummaryWriter(h.manager, provider, "step-5-preview", 2000),
    )
    try:
        with pytest.raises(CompactionFailedError) as caught:
            await _ensure(controller, session, keep=0)
        assert caught.value.result.failure_stage == "summary"
        assert caught.value.result.memory_committed
        assert "工作摘要输出被截断" in caught.value.result.error
        assert history_start(session, None) == 0
        assert not session.maintenance_progress.summaries
        memory_calls = len(h.prompts)
        assert memory_calls > 0
        controller.writer = WorkingSummaryWriter(
            h.manager, provider, "step-5-preview", 16384
        )
        _, result = await _ensure(controller, session, keep=0)
        assert result.committed and history_start(session, None) == 2
        assert len(h.prompts) == memory_calls
        assert json.loads(session.maintenance_progress.summaries["session"]) == (
            json.loads(content)
        )
        assert [call.kwargs["max_tokens"] for call in create.await_args_list] == [
            2000,
            16384,
        ]
    finally:
        await provider.aclose()


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
        if summary == "tasks: finish the tea plan":
            _advance_generation(h, session.key)
        return [{"role": "system", "content": summary}]

    with pytest.raises(CompactionFailedError) as caught:
        await _ensure(_controller(h), session, keep=0, render=render)
    assert caught.value.result.failure_stage == "window"
    assert caught.value.result.memory_committed
    assert history_start(session, None) == 0
    assert not session.maintenance_progress.summaries


async def test_consumer_failure_commits_window_and_keeps_pending_work(memory_harness):
    h = memory_harness
    session = h.manager.get_or_create("cli:consumer-fail")
    _turn(session)
    h.manager.save(session)
    h.maintenance._after_consolidation = AsyncMock(
        side_effect=RuntimeError("relationship unavailable")
    )
    controller = _controller(h)
    _, result = await _ensure(controller, session, keep=0)
    assert result.committed and result.memory_committed and result.memory_cursor == 2
    assert history_start(session, None) == 2
    progress = session.maintenance_progress
    assert progress.consumer_error and progress.pending_consumers
    assert progress.relationship_version == 0
    calls = len(h.prompts)
    h.maintenance._after_consolidation = AsyncMock()
    await h.maintenance.consolidate(ConsolidateRequest(session))
    assert len(h.prompts) == calls
    assert session.maintenance_progress.relationship_version == 1


async def test_persistent_consumer_failure_still_commits_new_memory_and_window(
    memory_harness,
):
    from shiori_sdk.memory.events import ConsolidationCommitted

    h = memory_harness
    session = h.manager.get_or_create("cli:consumer-down")
    _turn(session)
    h.manager.save(session)
    down = True

    def publish(event):
        if down:
            raise RuntimeError("memory engine unavailable")

    h.bus.on(ConsolidationCommitted, publish)
    controller = _controller(h)
    await _ensure(controller, session, keep=0)
    first_ref = session.maintenance_progress.pending_consumers["source_ref"]
    _turn(session, "next tea")
    h.manager.save(session)
    _, result = await _ensure(controller, session, keep=0)
    assert result.committed and result.memory_cursor == 4
    assert history_start(session, None) == 4
    pending = session.maintenance_progress.pending_consumers
    assert pending["source_ref"] != first_ref and not pending.get("published")
    assert [entry["source_ref"] for entry in pending["backlog"]] == [first_ref]
    calls = len(h.prompts)
    down = False
    await h.maintenance.consolidate(ConsolidateRequest(session))
    assert len(h.prompts) == calls
    assert not session.maintenance_progress.pending_consumers
    assert session.maintenance_progress.relationship_version == 2
    assert {first_ref, pending["source_ref"]} <= {e.source_ref for e in h.events}


async def test_measured_overflow_falls_back_to_zero_turns_before_degrading(
    memory_harness,
):
    h = memory_harness
    session = h.manager.get_or_create("cli:fallback")
    for _ in range(4):
        _turn(session)
    h.manager.save(session)
    controller = _controller(h)
    minimal = AsyncMock(return_value=[])

    async def render(prepared, summary):
        return [
            {"role": "user", "content": summary, "retained": prepared.retained_turns}
        ]

    def measure(messages):
        # Every estimate fits the hard limit; the real summary does not with turns.
        real = messages[0]["content"] == "tasks: finish the tea plan"
        real = real and messages[0]["retained"]
        return _budget(3900 if real else 1000)

    _, result = await controller.ensure(
        session_key=session.key,
        view=None,
        policy=CompactionPolicy(2),
        message_limit=len(session.messages),
        budget=_budget(3500),
        render=render,
        render_minimal=minimal,
        measure=measure,
    )
    assert result.committed and not result.degraded
    assert result.retained_turns == 0 and result.after_tokens == 1000
    assert history_start(session, None) == 8
    assert controller.writer.generate.await_count == 2
    minimal.assert_not_awaited()


async def test_minimal_expands_memory_to_unfinished_originals_without_committing_cut(
    memory_harness,
):
    h = memory_harness
    session = h.manager.get_or_create("cli:minimal-incomplete")
    _turn(session)
    session.add_message("user", "unfinished original input")
    h.manager.save(session)
    controller = _controller(h)
    calls = []

    async def render(prepared, summary):
        calls.append((prepared.stop, session.last_consolidated))
        return [{"role": "system", "content": "too large"}]

    async def minimal(summary):
        assert session.last_consolidated == 3
        return [
            {"role": "system", "content": summary},
            {"role": "user", "content": "current"},
        ]

    _, result = await controller.ensure(
        session_key=session.key,
        view=None,
        policy=CompactionPolicy(0),
        message_limit=3,
        budget=_budget(3500),
        render=render,
        render_minimal=minimal,
        measure=lambda messages: _budget(
            3900 if messages[0]["content"] == "too large" else 100
        ),
    )
    assert calls == [(2, 0), (2, 2)]
    assert result.memory_stop == 3 and result.degraded and not result.committed
    assert controller.writer.generate.await_count == 2
    assert len(session.messages) == 3 and history_start(session, None) == 0
    assert not session.maintenance_progress.summaries
    assert (
        session.maintenance_progress.relationship_version
        == session.maintenance_progress.memory_version
    )


async def test_stale_minimal_owner_is_rejected_and_not_adopted_by_latest(
    memory_harness,
):
    h = memory_harness
    session = h.manager.get_or_create("cli:stale-minimal")
    controller = _controller(h)

    async def minimal(summary):
        _advance_generation(h, session.key)
        return [{"role": "user", "content": "current"}]

    with pytest.raises(CompactionFailedError) as caught:
        await controller.ensure(
            session_key=session.key,
            view=None,
            policy=CompactionPolicy(),
            message_limit=0,
            budget=_budget(3500),
            render=AsyncMock(),
            render_minimal=minimal,
            measure=lambda _: _budget(100),
        )
    assert caught.value.result.failure_stage == "window"
    assert controller.latest(session.key, None) is None


async def test_manual_budget_failure_never_calls_minimal_renderer(memory_harness):
    h = memory_harness
    session = h.manager.get_or_create("cli:manual-budget")
    _turn(session)
    h.manager.save(session)
    minimal = AsyncMock(return_value=[])
    with pytest.raises(CompactionFailedError) as caught:
        await _controller(h).ensure(
            session_key=session.key,
            view=None,
            policy=CompactionPolicy(0),
            message_limit=2,
            budget=_budget(3500),
            render=AsyncMock(return_value=[]),
            render_minimal=minimal,
            measure=lambda _: _budget(3900),
            reason="manual",
        )
    assert (
        caught.value.result.memory_committed
        and caught.value.result.failure_stage == "budget"
    )
    minimal.assert_not_awaited()


@pytest.mark.parametrize("reason, retained", [("manual", 2), ("auto_threshold", 1)])
async def test_manual_keeps_configured_turns_between_target_and_hard_limit(
    memory_harness, reason, retained
):
    h = memory_harness
    session = h.manager.get_or_create(f"cli:between-{reason}")
    for _ in range(4):
        _turn(session)
    h.manager.save(session)
    controller = _controller(h)

    def measure(messages):
        # Window 20000: target 8000, hard limit 19780. With the 2000-token
        # summary allowance two turns project to 12000, one turn to 5000.
        return build_input_budget(
            model_context_window=20000,
            output_tokens=200,
            policy=BudgetPolicy(safety_margin_tokens=20),
            estimate=InputEstimate(
                10000 if messages[0]["retained"] == 2 else 3000, "local"
            ),
        )

    async def render(prepared, summary):
        return [{"role": "user", "content": "x", "retained": prepared.retained_turns}]

    _, result = await controller.ensure(
        session_key=session.key,
        view=None,
        policy=CompactionPolicy(2),
        message_limit=len(session.messages),
        budget=_budget(3500),
        render=render,
        measure=measure,
        reason=reason,
    )
    assert result.committed and result.retained_turns == retained
    assert result.retained_reduction_reason == ("" if retained == 2 else "budget")


async def test_manual_without_removable_configured_turns_commits_nothing(
    memory_harness,
):
    h = memory_harness
    session = h.manager.get_or_create("cli:manual-retained")
    _turn(session)
    _turn(session)
    h.manager.save(session)
    controller = _controller(h)
    with pytest.raises(CompactionFailedError) as caught:
        await controller.ensure(
            session_key=session.key,
            view=None,
            policy=CompactionPolicy(2),
            message_limit=len(session.messages),
            budget=_budget(3500),
            render=AsyncMock(return_value=[]),
            measure=lambda _: _budget(100),
            reason="manual",
        )
    assert caught.value.result.failure_stage == "no_turns"
    assert history_start(session, None) == 0 and not h.prompts
    controller.writer.generate.assert_not_awaited()


async def test_observation_from_another_binding_at_the_same_generation_is_stale():
    from core.compaction import CompactionResult
    from session.maintenance_progress import MaintenanceProgress

    # Unpersisted rebinding A→B and A→C both derive generation 1 from (A, 0).
    sessions = SimpleNamespace(
        get_or_create=lambda key: None,
        progress=MaintenanceProgress(ownership="B", generation=1),
    )
    sessions.maintenance_progress = lambda session: sessions.progress
    controller = CompactionController(sessions, None, None)  # type: ignore[arg-type]
    await controller.record(
        "role:mira",
        None,
        CompactionResult(phase="completed", ownership="B", generation=1),
        request_usage={},
        request_attempted=True,
    )
    assert controller.latest("role:mira", None) is not None
    sessions.progress = MaintenanceProgress(ownership="C", generation=1)
    assert controller.latest("role:mira", None) is None
    assert controller.latest("role:mira", None, request=True) is None
