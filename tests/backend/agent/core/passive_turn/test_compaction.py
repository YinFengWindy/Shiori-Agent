"""Request observations retain the independent owners' actual progress and policy."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest

from agent.core.passive_turn.compaction import RequestCompaction
from agent.prompting.input_budget import BudgetPolicy
from agent.provider import LLMProvider
from core.compaction import CompactionController, CompactionPolicy
from core.compaction_summary import WorkingSummary


async def test_normal_request_keeps_actual_progress_without_overwriting_last_compaction(
    memory_harness,
):
    h = memory_harness
    session = h.manager.get_or_create("cli:observed-progress")
    session.metadata["role_id"] = "mira"
    session.add_message("user", "tea plan")
    session.add_message("assistant", "noted")
    h.manager.save(session)
    provider = LLMProvider(
        api_key="test",
        context_window_tokens=100000,
        max_output_tokens=2000,
        budget_policy=BudgetPolicy(safety_margin_tokens=100),
    )
    await h.manager.bind_window_request(
        session.key, None, provider.context_identity("m")
    )
    messages = [
        {"role": "system", "content": "constraints"},
        {"role": "user", "content": "current"},
    ]

    def measure(candidate):
        budget = provider.input_budget(
            messages=candidate, tools=[], model="m", max_tokens=300
        )
        assert budget is not None
        return budget

    controller = CompactionController(
        h.manager,
        h.maintenance,
        SimpleNamespace(
            model_name="m",
            generate=AsyncMock(
                side_effect=lambda prepared: WorkingSummary(
                    "tea", prepared.removed_message_ids
                )
            ),
        ),
    )
    try:
        await controller.ensure(
            session_key=session.key,
            view=None,
            policy=CompactionPolicy(0),
            message_limit=2,
            budget=measure(messages),
            render=AsyncMock(return_value=messages),
            measure=measure,
            reason="manual",
        )
        previous = controller.latest(session.key, None)
        scope = RequestCompaction(
            controller,
            session.key,
            None,
            CompactionPolicy(4),
            2,
            2,
            AsyncMock(),
            lambda _: [],
        )
        await scope.ensure(messages, [], provider, "m", 300, "default")
        await scope.observe_request(measure(messages))
        request = controller.latest(session.key, None, request=True)
        assert request is not None
        assert request["configured_retained_turns"] == 4
        assert request["window_start"] == request["memory_cursor"] == 2
        assert request["compaction_count"] == 1
        assert request["memory_version"] == request["relationship_version"] == 1
        assert request["reason"] == ""
        assert controller.latest(session.key, None) == previous
    finally:
        await provider.aclose()


async def test_degraded_recovery_over_budget_records_the_same_failure_without_sending(
    memory_harness,
):
    from agent.core.passive_turn.budgeted_request import budgeted_chat
    from agent.core.passive_turn.compaction import request_compaction_scope
    from agent.core.passive_turn.reply_recovery import complete_reply
    from agent.core.reply_output import RoleReplyOutput
    from agent.prompting.usage_accounting import turn_usage
    from agent.prompting.usage_anchor import usage_context
    from core.compaction import CompactionFailedError

    h = memory_harness
    session = h.manager.get_or_create("cli:minimal-recovery")
    minimal = [
        {"role": "system", "content": "constraints"},
        {"role": "user", "content": "current"},
    ]
    probe = LLMProvider(
        api_key="test",
        context_window_tokens=10000,
        max_output_tokens=100,
        budget_policy=BudgetPolicy(safety_margin_tokens=100),
    )
    initial = probe.input_budget(messages=minimal, tools=[], model="m", max_tokens=100)
    assert initial is not None
    await probe.aclose()
    provider = LLMProvider(
        api_key="test",
        context_window_tokens=initial.estimate.tokens + 201,
        max_output_tokens=100,
        budget_policy=BudgetPolicy(safety_margin_tokens=100),
    )
    transport = AsyncMock(
        return_value=SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="", tool_calls=[]),
                    finish_reason="stop",
                )
            ],
            usage=SimpleNamespace(
                prompt_tokens=initial.estimate.tokens,
                completion_tokens=0,
                total_tokens=initial.estimate.tokens,
            ),
        )
    )
    provider._create_with_retry = transport
    observations = []

    async def observe(event):
        observations.append(event.status)

    controller = CompactionController(
        h.manager,
        h.maintenance,
        SimpleNamespace(model_name="m", generate=AsyncMock()),
        observe=observe,
    )
    scope = RequestCompaction(
        controller,
        session.key,
        None,
        CompactionPolicy(),
        0,
        2,
        AsyncMock(),
        lambda _: [],
        render_minimal=AsyncMock(return_value=minimal),
    )
    messages = [
        {"role": "system", "content": "optional " * 2000},
        {"role": "user", "content": "current"},
    ]
    try:
        with (
            turn_usage(),
            usage_context((session.key,)),
            request_compaction_scope(scope),
        ):
            await scope.ensure(messages, [], provider, "m", 100, "default")
            assert scope.degraded
            assert controller.latest(session.key, None, request=True) is None
            response = await budgeted_chat(
                provider, messages=messages, tools=[], model="m", max_tokens=100
            )
            sent = controller.latest(session.key, None, request=True)
            with pytest.raises(CompactionFailedError) as caught:
                await complete_reply(
                    response,
                    output=RoleReplyOutput(None, enabled=False),
                    messages=messages,
                    provider=provider,
                    model="m",
                    max_tokens=100,
                    role_reply=False,
                    session=session.key,
                    channel="cli",
                    iteration=1,
                )
        failure = caught.value.result
        assert failure.phase == "failed" and failure.failure_stage == "minimal_budget"
        assert scope.last_result == failure
        latest = controller.latest(session.key, None)
        assert latest is not None and latest["phase"] == "failed"
        assert (
            latest["failure_stage"]
            == observations[-1]["failure_stage"]
            == failure.failure_stage
        )
        assert latest == observations[-1]
        expected = failure.dump()
        expected.pop("error")
        assert all(latest[key] == value for key, value in expected.items())
        assert latest["after_tokens"] == failure.after_tokens
        assert controller.latest(session.key, None, request=True) == sent
        assert transport.await_count == 1
    finally:
        await provider.aclose()
