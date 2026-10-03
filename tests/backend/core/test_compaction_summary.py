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
        assert sent["response_format"] == {"type": "json_object"}
        assert preflight.call_args.kwargs["response_format"] == sent["response_format"]
        assert budget == provider._budget_for_request(sent, calibrate=False)
        prompt = sent["messages"][0]["content"]
        template, _ = json.JSONDecoder().raw_decode(prompt[prompt.index("{") :])
        assert template == {
            "tasks": "",
            "constraints": "",
            "decisions": "",
            "unfinished": "",
            "tool_state": "",
            "entities": "",
            "source_message_ids": ["<source message ID>"],
        }
        assert "Do not wrap" in prompt and "Markdown" in prompt
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
        assert create.await_count == (2 if outcome == "oversized" else 1)
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


@pytest.mark.parametrize("content", ["[]", '"summary"', "null", "42"])
def test_rejects_non_object_with_specific_diagnostic(content):
    with pytest.raises(ValueError, match="^工作摘要必须为 JSON 对象$"):
        validate_summary(content, {"old"})


@pytest.mark.parametrize(
    "missing", [("constraints",), ("constraints", "source_message_ids")]
)
def test_missing_required_fields_are_not_filled_even_with_extra_metadata(missing):
    payload = json.loads(_payload(["old"]))
    for field in missing:
        del payload[field]
    payload["private extra field"] = "private model output"
    with pytest.raises(ValueError) as caught:
        validate_summary(json.dumps(payload), {"old"})
    assert str(caught.value) == "工作摘要缺少字段：" + ", ".join(missing)


def test_wrapper_is_not_accepted_as_the_summary_object():
    payload = {"summary": json.loads(_payload(["old"]))}
    with pytest.raises(ValueError) as caught:
        validate_summary(json.dumps(payload), {"old"})
    assert str(caught.value) == (
        "工作摘要缺少字段：tasks, constraints, decisions, unfinished, tool_state, "
        "entities, source_message_ids"
    )


def test_extra_metadata_is_ignored_before_storage_and_token_limit_validation():
    expected = json.loads(_payload(["old", "new", "old"]))
    payload = expected | {
        "metadata": {"source_message_ids": ["invented"], "confidence": 0.9},
        "explanation": "私密的额外说明" * 2000,
    }
    summary = validate_summary(json.dumps(payload, ensure_ascii=False), {"old", "new"})
    expected["source_message_ids"] = ["old", "new"]
    assert json.loads(summary.content) == expected
    assert summary.source_ids == ("old", "new")


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


@pytest.mark.parametrize(
    "completion,reasoning,thinking,fallback",
    [
        (1392, None, None, ""),
        (7000, 5608, "private reasoning", ""),
        (7000, 5608, None, ""),
        (None, None, None, "missing_completion_usage"),
        (7000, None, "private reasoning", "missing_reasoning_usage"),
        (True, None, None, "invalid_completion_usage"),
    ],
)
async def test_real_transport_usage_controls_chinese_summary(
    tmp_path, monkeypatch, completion, reasoning, thinking, fallback
):
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("cli:actual-summary")
    session.add_message("user", "private source")
    session.add_message("assistant", "noted")
    manager.save(session)
    prepared = await manager.prepare_window(session.key, None, keep_turns=0)
    provider = LLMProvider(
        api_key="test",
        provider_name="deepseek",
        model_context_window=40000,
        default_max_tokens=16000,
    )
    response = _completion(
        _payload([session.messages[0]["id"]], tasks="中文摘要" * 300)
    )
    response.usage = SimpleNamespace(
        completion_tokens=completion,
        completion_tokens_details=SimpleNamespace(reasoning_tokens=reasoning),
    )
    response.choices[0].message.reasoning_content = thinking
    create = AsyncMock(return_value=response)
    monkeypatch.setattr(provider._client.chat.completions, "create", create)
    try:
        writer = WorkingSummaryWriter(manager, provider, "explicit", 16000)
        if fallback:
            with pytest.raises(ValueError, match="超过 2000 token") as error:
                await writer.generate(prepared)
            diagnostics = error.value.diagnostics
            assert len(diagnostics) == create.await_count == 2
        else:
            result = await writer.generate(prepared)
            diagnostics = result.diagnostics
            assert create.await_count == 1
            assert diagnostics[0].counted_tokens == 1392
        assert diagnostics[0].local_tokens > 2000
        assert diagnostics[0].fallback_reason == fallback
        assert "private" not in str(diagnostics)
    finally:
        await provider.aclose()


@pytest.mark.parametrize("second", ["short", "long", "invalid", "truncated"])
async def test_complete_oversized_summary_shortens_once_with_budget_feedback(
    tmp_path, monkeypatch, second
):
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("cli:shorten")
    session.add_message("user", "private source")
    session.add_message("assistant", "noted")
    manager.save(session)
    prepared = await manager.prepare_window(session.key, None, keep_turns=0)
    provider = LLMProvider(
        api_key="test",
        provider_name="deepseek",
        model_context_window=40000,
        default_max_tokens=16000,
    )
    old = _payload([session.messages[0]["id"]], tasks="private state")
    first = _completion(old)
    first.usage = SimpleNamespace(completion_tokens=3000)
    following = _completion(
        "{}" if second == "invalid" else old,
        "length" if second == "truncated" else "stop",
    )
    following.usage = SimpleNamespace(
        completion_tokens=3000 if second == "long" else 500
    )
    create = AsyncMock(side_effect=[first, following])
    monkeypatch.setattr(provider._client.chat.completions, "create", create)
    preflight = Mock(wraps=provider.input_budget)
    monkeypatch.setattr(provider, "input_budget", preflight)
    try:
        writer = WorkingSummaryWriter(manager, provider, "explicit", 16000)
        if second == "short":
            diagnostics = (await writer.generate(prepared)).diagnostics
        else:
            with pytest.raises(ValueError) as error:
                await writer.generate(prepared)
            diagnostics = error.value.diagnostics
        assert create.await_count == 2
        assert [item.rewrite for item in diagnostics] == [0, 1]
        assert diagnostics[0].outcome == "oversized"
        assert (
            diagnostics[1].outcome
            == {
                "short": "accepted",
                "long": "oversized",
                "invalid": "invalid",
                "truncated": "truncated",
            }[second]
        )
        sent = create.await_args.kwargs
        feedback = json.loads(sent["messages"][-1]["content"])["budget_feedback"]
        assert feedback["counted_tokens"] == 3000
        assert feedback["hard_limit"] == 2000
        assert feedback["count_source"] == "provider_output_upper_bound"
        assert preflight.call_args.kwargs["messages"] == sent["messages"]
        assert (
            provider._budget_for_request(
                sent, calibrate=False
            ).output_reservation_tokens
            == 4000
        )
        assert not manager.maintenance_progress(session).summaries
    finally:
        await provider.aclose()


async def test_custom_summary_limit_changes_prompt_and_generation_headroom(
    tmp_path, monkeypatch
):
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("cli:custom-budget")
    session.add_message("user", "state")
    session.add_message("assistant", "done")
    manager.save(session)
    prepared = await manager.prepare_window(session.key, None, keep_turns=0)
    provider = LLMProvider(
        api_key="test",
        provider_name="deepseek",
        model_context_window=40000,
        default_max_tokens=7000,
    )
    response = _completion(_payload([session.messages[0]["id"]]))
    response.usage = SimpleNamespace(completion_tokens=3500)
    create = AsyncMock(return_value=response)
    monkeypatch.setattr(provider._client.chat.completions, "create", create)
    try:
        result = await WorkingSummaryWriter(
            manager, provider, "explicit", 7000, 4000
        ).generate(prepared)
        assert result.diagnostics[0].limit == 4000
        assert create.await_args.kwargs["max_tokens"] == 7000
        assert (
            "Target 2000–3600 tokens, hard maximum 4000"
            in create.await_args.kwargs["messages"][0]["content"]
        )
    finally:
        await provider.aclose()
