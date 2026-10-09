"""Auxiliary budget summaries remain separate from role-facing replies."""

from unittest.mock import AsyncMock
from copy import deepcopy
from types import SimpleNamespace

import pytest

from agent.core.passive_turn import DefaultReasoner
from agent.core.runtime_support import ToolDiscoveryState
from agent.looping.ports import LLMConfig, LLMServices
from agent.provider import LLMResponse
from agent.prompting.usage_accounting import turn_usage
from agent.tools.registry import ToolRegistry


async def test_summary_and_recovery_remove_only_generated_attachment_instructions(
    tmp_path,
):
    from agent.context import MessageEnvelopeBuilder

    attachment = tmp_path / "article.txt"
    attachment.write_text("article", encoding="utf-8")
    user_line = "- 如需读取内容，请调用 user_example()"
    content = MessageEnvelopeBuilder()._append_text_attachment_refs(
        "解释这句话：\n" + user_line, [str(attachment)], "read_attachment"
    )
    messages = [{"role": "user", "content": content}]
    sent = []

    async def chat(**kwargs):
        sent.append(deepcopy(kwargs))
        return LLMResponse(content="" if len(sent) == 1 else "尚未读到文章。")

    provider = AsyncMock()
    provider.chat.side_effect = chat
    reasoner = DefaultReasoner(
        llm=LLMServices(provider=provider, light_provider=provider),
        llm_config=LLMConfig(),
        tools=ToolRegistry(),
        discovery=ToolDiscoveryState(),
        tool_search_enabled=False,
    )
    result = await reasoner._summarize_incomplete_progress(
        messages, reason="max_iterations", iteration=1, tools_used=[]
    )
    assert result[0] == "尚未读到文章。"
    assert len(sent) == 2
    for call in sent:
        assert call["tools"] == []
        text = call["messages"][0]["content"]
        assert user_line in text and str(attachment) in text
        assert "请调用 read_attachment" not in text
    assert messages[0]["content"] == content


async def test_role_summary_normalizes_legacy_content_before_mood_call():
    provider = AsyncMock()
    provider.chat.side_effect = [
        LLMResponse(
            content='{"thought":"我想先收尾。","content":"先告诉你当前进度。","mood":"害羞"}',
            total_tokens=40,
        ),
        LLMResponse(content='{"mood":"平静","thought":"我已经告诉你进度。"}'),
    ]
    reasoner = DefaultReasoner(
        llm=LLMServices(provider=provider, light_provider=provider),
        llm_config=LLMConfig(),
        tools=ToolRegistry(),
        discovery=ToolDiscoveryState(),
        tool_search_enabled=False,
    )

    content, tokens, role_reply, recovery = (
        await reasoner._summarize_incomplete_progress(
            [{"role": "user", "content": "请检查"}],
            reason="max_iterations",
            iteration=1,
            tools_used=["search"],
            reply_moods=("平静", "害羞"),
        )
    )

    assert content == "先告诉你当前进度。"
    assert tokens == 40
    assert recovery is None
    assert role_reply is not None
    assert role_reply.content == content
    assert role_reply.mood == "平静"
    assert provider.chat.call_args_list[1].kwargs["messages"][-2] == {
        "role": "assistant",
        "content": content,
    }


@pytest.mark.parametrize("max_tokens,expected_budget", [(256, 256), (8192, 512)])
async def test_internal_budget_summary_uses_auxiliary_purpose(
    max_tokens, expected_budget
):
    provider = AsyncMock()
    provider.chat.return_value = LLMResponse(
        content="检查到当前进度。", total_tokens=40
    )
    reasoner = DefaultReasoner(
        llm=LLMServices(provider=provider, light_provider=provider),
        llm_config=LLMConfig(max_tokens=max_tokens),
        tools=ToolRegistry(),
        discovery=ToolDiscoveryState(),
        tool_search_enabled=False,
    )

    result = await reasoner._summarize_incomplete_progress(
        [{"role": "user", "content": "请检查"}],
        reason="max_iterations",
        iteration=1,
        tools_used=["search"],
    )

    assert result == ("检查到当前进度。", 40, None, None)
    request = provider.chat.await_args.kwargs
    assert request["call_purpose"] == "auxiliary"
    assert request["max_tokens"] == expected_budget
    assert request["tools"] == []


async def test_role_summary_recovery_obeys_input_budget_and_skips_mood():
    from agent.provider import LLMProvider
    from agent.prompting.input_budget import BudgetPolicy
    from agent.prompting.usage_anchor import usage_context
    from core.compaction import CompactionFailedError

    provider = LLMProvider(
        api_key="test",
        model_context_window=2000,
        default_max_tokens=100,
        budget_policy=BudgetPolicy(safety_margin_tokens=20),
    )
    provider._create_with_retry = AsyncMock(
        return_value=SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="", tool_calls=[]),
                    finish_reason="stop",
                )
            ],
            usage=SimpleNamespace(
                prompt_tokens=1499, completion_tokens=1, total_tokens=1500
            ),
        )
    )
    reasoner = DefaultReasoner(
        llm=LLMServices(provider, provider),
        llm_config=LLMConfig(max_tokens=100),
        tools=ToolRegistry(),
        discovery=ToolDiscoveryState(),
        tool_search_enabled=False,
    )
    try:
        with (
            usage_context(("cli:summary-recovery",)),
            pytest.raises(CompactionFailedError) as caught,
        ):
            await reasoner._summarize_incomplete_progress(
                [{"role": "user", "content": "检查"}],
                reason="early_stop",
                iteration=1,
                tools_used=[],
                reply_moods=("平静",),
                session="role:mira",
                channel="qq",
            )
        assert caught.value.result.failure_stage == "budget"
        assert provider._create_with_retry.await_count == 1
    finally:
        await provider.aclose()


@pytest.mark.parametrize("outcome", ["tool", "empty", "network"])
async def test_non_role_finalize_degrades_then_rejects_invalid_response(
    memory_harness, outcome
):
    import json
    from datetime import datetime
    from agent.context import ContextBuilder
    from agent.core.passive_turn.compaction import (
        RequestCompaction,
        request_compaction_scope,
    )
    from agent.core.passive_turn.compaction_render import CompactionRenderer
    from agent.core.passive_turn.empty_reply import EmptyReplyError
    from agent.lifecycle.types import PromptRenderInput
    from agent.provider import LLMProvider
    from agent.prompting.input_budget import BudgetPolicy
    from core.compaction import CompactionFailedError, CompactionPolicy
    from core.roles import RoleStore

    h = memory_harness
    roles = RoleStore(h.manager.workspace)
    roles.create_role(
        role_id="mira", name="Mira", system_prompt="keep role constraints"
    )
    session = h.manager.get_or_create("cli:finalize")
    session.metadata["role_id"] = "mira"
    session.add_message("user", "original task")
    session.add_message("assistant", "done")
    h.manager.save(session)
    provider = LLMProvider(
        api_key="test",
        model_context_window=10000,
        default_max_tokens=500,
        budget_policy=BudgetPolicy(safety_margin_tokens=100),
    )
    tools = ToolRegistry()
    reasoner = DefaultReasoner(
        LLMServices(provider, provider),
        LLMConfig(model="m", max_tokens=500),
        tools,
        ToolDiscoveryState(),
        tool_search_enabled=False,
        context=ContextBuilder(
            h.manager.workspace, h.maintenance._store, runtime_roles=roles
        ),
        session_manager=h.manager,
        compaction_memory=h.maintenance,
    )
    prompt = PromptRenderInput(
        session_key=session.key,
        channel="cli",
        chat_id="finalize",
        content="finish current",
        media=None,
        timestamp=datetime.now(),
        history=session.get_history(start_index=0),
        skill_names=None,
        retrieved_memory_block="optional retrieval " * 2000,
        disabled_sections=set(),
        turn_injection_prompt="",
        session_metadata=session.metadata,
    )
    initial = await reasoner.render_prompt(prompt)
    renderer = CompactionRenderer(
        h.manager,
        None,
        2,
        prompt,
        initial.current_message,
        reasoner.render_prompt,
        tools,
        False,
        set(),
        False,
        lambda: [],
    )
    controller = reasoner._compaction
    assert controller is not None
    scope = RequestCompaction(
        controller,
        session.key,
        None,
        CompactionPolicy(2),
        2,
        len(initial.messages),
        renderer.render,
        renderer.history_tools,
        render_minimal=renderer.render_minimal,
    )
    sent = []

    async def transport(kwargs, **unused):
        calls = []
        if "Rewrite the current working state" in kwargs["messages"][0]["content"]:
            data = json.loads(kwargs["messages"][-1]["content"])
            content = json.dumps(
                {
                    "tasks": "original task",
                    "constraints": "",
                    "decisions": "",
                    "unfinished": "finish",
                    "tool_state": "",
                    "entities": "",
                    "source_message_ids": [data["messages"][0]["id"]],
                }
            )
        else:
            sent.append(kwargs)
            if outcome == "network":
                raise OSError("offline")
            content = "pretend success" if outcome == "tool" else ""
            if outcome == "tool":
                calls = [
                    SimpleNamespace(
                        id="unexpected",
                        function=SimpleNamespace(name="side_effect", arguments="{}"),
                    )
                ]
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=content, tool_calls=calls),
                    finish_reason="stop",
                )
            ],
            usage=None,
        )

    provider._create_with_retry = transport
    try:
        with (
            turn_usage(),
            request_compaction_scope(scope),
            pytest.raises(
                {
                    "empty": EmptyReplyError,
                    "network": OSError,
                    "tool": CompactionFailedError,
                }[outcome]
            ),
        ):
            await reasoner._summarize_incomplete_progress(
                initial.messages,
                reason="max_iterations",
                iteration=1,
                tools_used=[],
                session=session.key,
                channel="cli",
            )
        assert scope.degraded
        assert len(sent) == (2 if outcome == "empty" else 1)
        assert all(not request.get("tools") for request in sent)
        assert all("summary_request" in str(request["messages"]) for request in sent)
        latest = controller.latest(session.key, None)
        assert latest is not None
        if outcome == "network":
            # An ordinary provider failure is not a compaction failure.
            assert latest["phase"] != "failed"
            latest = controller.latest(session.key, None, request=True)
            assert latest is not None and latest["failure_kind"] == "provider_error"
        else:
            assert latest["phase"] == "failed"
            assert latest["failure_stage"] == "response"
        assert latest["request_usage"]["last_request"]["purpose"] == "auxiliary"
        assert not session.maintenance_progress.summaries and len(session.messages) == 2
    finally:
        await provider.aclose()
