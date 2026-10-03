"""Working summaries validate size/provenance and budget their own request."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from agent.prompting.input_budget import BudgetPolicy
from agent.provider import LLMProvider, LLMResponse
from core.compaction_summary import WorkingSummaryWriter, validate_summary
from session.manager import SessionManager


def _payload(ids, **changes):
    return json.dumps(
        {
            "tasks": "continue the plan",
            "constraints": "keep privacy",
            "decisions": "chosen",
            "unfinished": "finish",
            "tool_state": "complete",
            "entities": "project",
            "source_message_ids": ids,
            **changes,
        },
        ensure_ascii=False,
    )


def _completion(content, finish_reason="stop"):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content, tool_calls=[]),
                finish_reason=finish_reason,
            )
        ],
        usage=None,
    )


@pytest.mark.parametrize(
    "provider_name, configured, expected",
    [
        ("StepFun", 16384, 16384),
        ("deepseek", 16384, 4000),
        ("StepFun", 1024, 1024),
        ("deepseek", 1024, 1024),
    ],
)
async def test_summary_generation_budget_matches_provider_preflight(
    tmp_path, monkeypatch, provider_name, configured, expected
):
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("cli:summary-generation-budget")
    session.add_message("user", "continue the plan")
    session.add_message("assistant", "noted")
    manager.save(session)
    prepared = await manager.prepare_window(session.key, None, keep_turns=0)
    assert prepared is not None
    provider = LLMProvider(
        api_key="test",
        provider_name=provider_name,
        model_context_window=24000,
        default_max_tokens=configured,
        budget_policy=BudgetPolicy(safety_margin_tokens=20),
    )
    content = _payload([session.messages[0]["id"]])
    create = AsyncMock(return_value=_completion(content))
    monkeypatch.setattr(provider._client.chat.completions, "create", create)
    measure = provider.input_budget
    preflight = Mock(wraps=measure)
    monkeypatch.setattr(provider, "input_budget", preflight)
    try:
        result = await WorkingSummaryWriter(
            manager, provider, "explicit", configured
        ).generate(prepared)
        sent = create.await_args.kwargs
        budget = measure(**preflight.call_args.kwargs)
        assert budget is not None
        assert budget.output_reservation_tokens == sent["max_tokens"] == expected
        assert budget.estimate.tokens <= budget.input_limit_tokens
        assert create.await_count == 1
        assert "auxiliary_max_tokens" not in sent and "call_purpose" not in sent
        if provider_name == "deepseek":
            assert sent["extra_body"]["thinking"] == {"type": "disabled"}
        assert json.loads(result.content) == json.loads(content)
    finally:
        await provider.aclose()


@pytest.mark.parametrize("outcome", ["complete", "oversized", "truncated"])
async def test_generation_headroom_keeps_summary_validation(
    tmp_path, monkeypatch, outcome
):
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("cli:summary-headroom")
    session.add_message("user", "continue the plan")
    session.add_message("assistant", "noted")
    manager.save(session)
    prepared = await manager.prepare_window(session.key, None, keep_turns=0)
    assert prepared is not None
    provider = LLMProvider(
        api_key="test",
        provider_name="StepFun",
        model_context_window=1000000,
        default_max_tokens=16384,
    )
    content = _payload(
        [session.messages[0]["id"]],
        tasks="中" * 1000 if outcome == "oversized" else "continue the plan",
    )

    async def complete(**kwargs):
        # Reasoning can exhaust 2000 tokens before even a short JSON is complete.
        truncated = kwargs["max_tokens"] <= 2000 or outcome == "truncated"
        return _completion(content, "length" if truncated else "stop")

    create = AsyncMock(side_effect=complete)
    monkeypatch.setattr(provider._client.chat.completions, "create", create)
    try:
        writer = WorkingSummaryWriter(manager, provider, "step-5-preview", 16384)
        if outcome == "complete":
            summary = await writer.generate(prepared)
            assert json.loads(summary.content) == json.loads(content)
        else:
            error = "超过 2000 token 上限" if outcome == "oversized" else "输出被截断"
            with pytest.raises(ValueError, match=error):
                await writer.generate(prepared)
        assert create.await_count == 1
        assert not manager.maintenance_progress(session).summaries
    finally:
        await provider.aclose()


@pytest.mark.parametrize(
    "content",
    [
        "not json",
        "{}",
        _payload(["invented"]),
        _payload(["old"], tasks="中" * 1000),
        _payload(["old"], decisions=[]),
        _payload([]),
    ],
)
def test_rejects_invalid_or_oversized_state(content):
    with pytest.raises((ValueError, TypeError)):
        validate_summary(content, {"old"})


def test_valid_old_and_new_provenance_survives_replacement():
    summary = validate_summary(_payload(["old", "new", "old"]), {"old", "new"})
    assert summary.source_ids == ("old", "new")
    assert "keep privacy" in summary.content


async def test_summary_request_includes_old_state_and_attachments_without_base64(
    tmp_path,
):
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("cli:summary")
    session.add_message(
        "user",
        "inspect image",
        media=["image.png"],
        llm_user_content=[
            {
                "type": "image_url",
                "image_url": {"url": "data:image/png;base64," + "X" * 50000},
            }
        ],
    )
    session.add_message(
        "assistant",
        "image inspected",
        tool_chain=[
            {"calls": [{"call_id": "one", "name": "inspect", "result": "found entity"}]}
        ],
    )
    manager.save(session)
    progress = manager.maintenance_progress(session)
    progress.summaries["session"] = _payload(
        ["earlier"], tasks="older unfinished promise"
    )
    progress.summary_source_ids["session"] = ["earlier"]
    manager._store.write_maintenance_progress(session.key, progress.dump())
    prepared = await manager.prepare_window(session.key, None, keep_turns=0)
    assert prepared is not None
    provider = LLMProvider(
        api_key="test",
        model_context_window=10000,
        default_max_tokens=2000,
        budget_policy=BudgetPolicy(safety_margin_tokens=20),
    )
    provider.chat = AsyncMock(
        return_value=LLMResponse(
            content=_payload(["earlier", session.messages[0]["id"]])
        )
    )
    try:
        result = await WorkingSummaryWriter(
            manager, provider, "explicit", 2000
        ).generate(prepared)
        sent = provider.chat.await_args.kwargs
        assert sent["call_purpose"] == "auxiliary" and sent["max_tokens"] == 2000
        source = sent["messages"][-1]["content"]
        assert "older unfinished promise" in source
        assert "found entity" in source and "image.png" in source
        assert "base64" not in source and "X" * 100 not in source
        assert result.source_ids[0] == "earlier"
    finally:
        await provider.aclose()


@pytest.mark.parametrize("failure", ["input", "truncated"])
async def test_auxiliary_overflow_or_truncation_never_produces_a_summary(
    tmp_path, failure
):
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("cli:summary-budget")
    session.add_message("user", "x" * 10)
    session.add_message("assistant", "done")
    manager.save(session)
    prepared = await manager.prepare_window(session.key, None, keep_turns=0)
    assert prepared is not None
    # The input case leaves less room than the instructions alone need.
    provider = LLMProvider(
        api_key="test",
        model_context_window=2100 if failure == "input" else 4000,
        default_max_tokens=2000,
        budget_policy=BudgetPolicy(safety_margin_tokens=20),
    )
    provider.chat = AsyncMock(
        return_value=LLMResponse(
            content=_payload([session.messages[0]["id"]]), finish_reason="length"
        )
    )
    try:
        with pytest.raises(ValueError):
            await WorkingSummaryWriter(manager, provider, "explicit", 2000).generate(
                prepared
            )
        assert provider.chat.await_count == (0 if failure == "input" else 1)
        assert not manager.maintenance_progress(session).summaries
    finally:
        await provider.aclose()


async def test_native_tool_exchange_survives_storage_and_enters_summary_sources(
    tmp_path,
):
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("cli:native")
    call = {
        "id": "native-call",
        "type": "function",
        "function": {"name": "write_file", "arguments": '{"path":"report.txt"}'},
    }
    session.add_message("user", "write report")
    session.add_message("assistant", "", tool_calls=[call])
    session.add_message(
        "tool", "report saved", tool_call_id="native-call", name="write_file"
    )
    session.add_message("assistant", "completed")
    manager.save(session)
    manager = SessionManager(tmp_path)
    session = manager.get_or_create(session.key)
    prepared = await manager.prepare_window(session.key, None, keep_turns=0)
    assert prepared is not None and len(prepared.removed_message_ids) == 4
    provider = LLMProvider(
        api_key="test",
        model_context_window=10000,
        default_max_tokens=2000,
        budget_policy=BudgetPolicy(safety_margin_tokens=20),
    )
    provider.chat = AsyncMock(
        return_value=LLMResponse(
            content=_payload(
                [session.messages[0]["id"]],
                tool_state="report saved; do not repeat write_file",
            )
        )
    )
    try:
        await WorkingSummaryWriter(manager, provider, "explicit", 2000).generate(
            prepared
        )
        sources = json.loads(
            provider.chat.await_args.kwargs["messages"][-1]["content"]
        )["messages"]
        assert sources[1]["tool_calls"] == [call]
        assert sources[2]["tool_call_id"] == "native-call"
        assert sources[2]["content"] == "report saved"
    finally:
        await provider.aclose()


async def test_oversized_removed_range_is_folded_in_budgeted_batches(tmp_path):
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("cli:summary-batches")
    session.add_message("user", "paste " + "p" * 60000)
    session.add_message("assistant", "noted")
    for index in range(6):
        session.add_message("user", f"fetch page {index}")
        session.add_message(
            "assistant",
            f"page {index} fetched",
            tool_chain=[
                {
                    "calls": [
                        {
                            "call_id": f"fetch-{index}",
                            "name": "web_fetch",
                            "result": f"head-{index}-" + "w" * 40000 + "-tail",
                        }
                    ]
                }
            ],
        )
    manager.save(session)
    prepared = await manager.prepare_window(session.key, None, keep_turns=0)
    assert prepared is not None
    provider = LLMProvider(
        api_key="test",
        model_context_window=8000,
        default_max_tokens=2000,
        budget_policy=BudgetPolicy(safety_margin_tokens=20),
    )
    first_id = session.messages[0]["id"]
    requests = []

    async def fake_chat(**kwargs):
        budget = provider.input_budget(**kwargs)
        assert budget is not None
        requests.append(
            (budget.estimate.tokens, budget.input_limit_tokens, kwargs["messages"])
        )
        return LLMResponse(content=_payload([first_id], tasks=f"step {len(requests)}"))

    provider.chat = AsyncMock(side_effect=fake_chat)
    try:
        result = await WorkingSummaryWriter(
            manager, provider, "explicit", 2000
        ).generate(prepared)
        assert len(requests) > 1
        assert all(tokens <= limit for tokens, limit, _ in requests)
        # Each later batch rewrites the previous batch's state, not the original.
        for index, (_, _, messages) in enumerate(requests[1:], start=1):
            payload = json.loads(messages[-1]["content"])
            assert f"step {index}" in payload["previous_state"]
        sent = "".join(messages[-1]["content"] for _, _, messages in requests)
        assert "chars truncated" in sent and "w" * 10001 not in sent
        assert all("-tail" in sent and f"head-{i}-" in sent for i in range(6))
        assert json.loads(result.content)["tasks"] == f"step {len(requests)}"
        assert result.source_ids == (first_id,)
    finally:
        await provider.aclose()
