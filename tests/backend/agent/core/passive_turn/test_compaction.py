"""Request observations retain the independent owners' actual progress and policy."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

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
