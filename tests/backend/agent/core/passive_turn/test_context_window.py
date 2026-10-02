"""Idle inspection and manual compaction use the real prompt/budget/memory owners."""

from copy import deepcopy
from unittest.mock import AsyncMock

import pytest

from agent.context import ContextBuilder
from agent.core.passive_turn.reasoner import DefaultReasoner
from agent.core.runtime_support import ToolDiscoveryState
from agent.looping.ports import LLMConfig, LLMServices
from agent.provider import LLMProvider
from agent.prompting.input_budget import BudgetPolicy
from bus.events import InboundMessage
from conversation.context_scope import history_start, turn_context_view
from conversation.service import network_thread_id
from core.compaction_summary import WorkingSummary
from core.memory.markdown import MarkdownMemoryStore
from core.roles import RoleStore


def _turn(session, label, thread=""):
    session.add_message("user", label, thread_id=thread)
    session.add_message("assistant", "finished", thread_id=thread)


def _window(h, keep=2):
    from agent.tools.registry import ToolRegistry

    roles = RoleStore(h.manager.workspace)
    roles.create_role(role_id="mira", name="Mira", system_prompt="fixed role")

    provider = LLMProvider(
        api_key="test",
        context_window_tokens=128000,
        max_output_tokens=8192,
        budget_policy=BudgetPolicy(safety_margin_tokens=100),
    )
    provider.chat = AsyncMock(side_effect=AssertionError("inspection called a model"))
    config = LLMConfig(
        model="explicit-model", max_tokens=4000, compaction_retained_turns=keep
    )
    reasoner = DefaultReasoner(
        LLMServices(provider, provider),
        config,
        ToolRegistry(),
        ToolDiscoveryState(),
        tool_search_enabled=False,
        memory_window=20,
        context=ContextBuilder(
            h.manager.workspace,
            MarkdownMemoryStore(h.manager.workspace),
            runtime_roles=RoleStore(h.manager.workspace),
        ),
        session_manager=h.manager,
        compaction_memory=h.maintenance,
    )
    window = reasoner.context_window
    assert window is not None

    async def summarize(prepared):
        return WorkingSummary("tasks: continue tea", prepared.removed_message_ids)

    window.controller.writer.generate = AsyncMock(side_effect=summarize)
    return window, provider


@pytest.mark.parametrize("keep", [0, 2, 4])
async def test_idle_read_is_model_free_and_manual_uses_completed_turns_below_trigger(
    memory_harness, keep
):
    h = memory_harness
    session = h.manager.get_or_create("cli:manual")
    session.metadata["role_id"] = "mira"
    for index in range(6):
        _turn(session, f"tea task {index}")
    h.manager.save(session)
    original = deepcopy(session.messages)
    window, provider = _window(h, keep)
    msg = InboundMessage(
        channel="cli",
        sender="user",
        chat_id="manual",
        content="/compact with an unsent draft",
        media=["never-read.png"],
    )
    try:
        state = await window.inspect(session=session, context_view=None, msg=msg)
        assert state["tokens"] < 128000 * 0.75
        assert state["context_window_tokens"] == 128000
        assert state["input_limit_tokens"] == 123900
        assert state["source"] == "local" and state["can_compact"]
        assert not h.prompts
        state = await window.inspect(
            session=session, context_view=None, msg=msg, compact=True
        )
        assert state["result"]["committed"]
        assert state["result"]["configured_retained_turns"] == keep
        assert state["result"]["retained_turns"] == keep
        assert state["budget"]["max_output_tokens"] == 8192
        assert state["budget"]["output_reservation_tokens"] == 4000
        assert state["budget"]["estimate"]["tokens"] == state["tokens"]
        assert state["compaction_count"] == 1
        assert state["window_start"] == state["result"]["retained_start"]
        assert state["memory_version"] == state["result"]["memory_version"]
        assert history_start(session, None) == 12 - 2 * keep
        assert session.messages == original
        assert h.prompts and all(
            "unsent draft" not in prompt and "never-read" not in prompt
            for prompt in h.prompts
        )
        provider.chat.assert_not_awaited()
    finally:
        await provider.aclose()


@pytest.mark.parametrize("failure", ["memory", "summary", "validation"])
async def test_manual_failure_preserves_window_and_reports_memory_commit_then_retries(
    memory_harness, failure
):
    h = memory_harness
    session = h.manager.get_or_create("cli:failure")
    session.metadata["role_id"] = "mira"
    _turn(session, "tea task")
    h.manager.save(session)
    window, provider = _window(h, 0)
    original = deepcopy(session.messages)
    writer = window.controller.writer.generate
    if failure == "memory":
        h.fail = True
    elif failure == "summary":
        window.controller.writer.generate = AsyncMock(
            side_effect=RuntimeError("summary offline")
        )
    else:
        window.controller.writer.generate = AsyncMock(
            return_value=WorkingSummary("x" * 300000, (session.messages[0]["id"],))
        )
    msg = InboundMessage(channel="cli", sender="user", chat_id="failure", content="")
    try:
        result = await window.inspect(
            session=session, context_view=None, msg=msg, compact=True
        )
        assert result["result"]["committed"] is False
        assert result["result"]["memory_committed"] is (failure != "memory")
        assert result["memory_version"] == result["result"]["memory_version"]
        assert result["window_start"] == 0 and result["compaction_count"] == 0
        assert result["budget"]["estimate"]["tokens"] == result["tokens"]
        assert history_start(session, None) == 0
        assert session.messages == original
        calls = len(h.prompts)
        h.fail = False
        window.controller.writer.generate = writer
        retried = await window.inspect(
            session=session, context_view=None, msg=msg, compact=True
        )
        assert retried["result"]["committed"]
        if failure != "memory":
            assert len(h.prompts) == calls
    finally:
        await provider.aclose()


async def test_manual_external_scope_keeps_other_threads_and_unfinished_input(
    memory_harness,
):
    h = memory_harness
    session = h.manager.get_or_create("role:mira")
    session.metadata["role_id"] = "mira"
    a, b = [network_thread_id("mira", "qq", name) for name in ("a", "b")]
    _turn(session, "group A task", a)
    _turn(session, "group B private task", b)
    session.add_message("user", "unfinished A", thread_id=a)
    h.manager.save(session)
    window, provider = _window(h, 0)
    view = turn_context_view(h.manager.workspace, "mira", a)
    msg = InboundMessage(
        channel="qq",
        sender="friend",
        chat_id="a",
        content="/compact",
        metadata={"thread_id": a},
    )
    try:
        result = await window.inspect(
            session=session, context_view=view, msg=msg, compact=True
        )
        assert result["result"]["committed"]
        assert history_start(session, view) == 4
        assert (
            history_start(session, turn_context_view(h.manager.workspace, "mira", b))
            == 0
        )
        assert "unfinished A" in str(
            session.get_history(start_index=4, include=view.includes)
        )
        assert len(session.messages) == 5
    finally:
        await provider.aclose()


async def test_no_complete_turn_is_unavailable_without_model_work(memory_harness):
    h = memory_harness
    session = h.manager.get_or_create("cli:empty")
    session.metadata["role_id"] = "mira"
    session.add_message("user", "unfinished")
    h.manager.save(session)
    window, provider = _window(h)
    try:
        result = await window.inspect(
            session=session,
            context_view=None,
            msg=InboundMessage(channel="cli", sender="u", chat_id="empty", content=""),
            compact=True,
        )
        assert not result["can_compact"] and result["result"] is None
        assert not h.prompts
        provider.chat.assert_not_awaited()
    finally:
        await provider.aclose()
