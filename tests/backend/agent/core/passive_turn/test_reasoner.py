from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agent.core.passive_turn.reasoner import DefaultReasoner
from agent.core.runtime_support import ToolDiscoveryState
from agent.core.types import ReasonerResult
from agent.lifecycle.types import PromptRenderResult
from agent.looping.ports import LLMConfig, LLMServices
from agent.provider import ContentSafetyError, ContextLengthError
from agent.tools.registry import ToolRegistry
from session.manager import SessionManager


@pytest.mark.parametrize("error_type", [ContentSafetyError, ContextLengthError])
@pytest.mark.parametrize("last_consolidated", [0, 6])
@pytest.mark.parametrize(
    "success_attempt", [1, 5, 6, None], ids=["catalog", "half", "empty", "exhausted"]
)
async def test_run_turn_retry_preserves_persisted_history(
    tmp_path, error_type, last_consolidated, success_attempt
):
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("cli:retry")
    total_messages = last_consolidated + 6
    for index in range(total_messages):
        role = "user" if index % 2 == 0 else "assistant"
        if index == total_messages - 1:
            role = "user"
        session.add_message(role, f"message-{index}", metadata={"index": index})
    session.last_consolidated = last_consolidated
    session.consolidation_requested = True
    await manager.save_async(session)
    original_messages = deepcopy(session.messages)
    source_history = session.get_history(start_index=last_consolidated)
    msg = SimpleNamespace(
        channel="cli",
        chat_id="retry",
        content=original_messages[-1]["content"],
        media=[],
        timestamp=datetime.now(timezone.utc),
    )
    reasoner = DefaultReasoner(
        llm=LLMServices(provider=AsyncMock(), light_provider=AsyncMock()),
        llm_config=LLMConfig(),
        tools=ToolRegistry(),
        discovery=ToolDiscoveryState(),
        tool_search_enabled=False,
        memory_window=40,
        context=AsyncMock(),
        session_manager=manager,
    )
    reasoner.render_prompt = AsyncMock(
        side_effect=lambda request: PromptRenderResult(
            messages=[
                *request.history,
                {"role": "user", "content": request.content},
            ]
        )
    )
    failure_count = 7 if success_attempt is None else success_attempt
    responses = [error_type("retry required") for _ in range(failure_count)]
    if success_attempt is not None:
        responses.append(ReasonerResult(reply="recovered"))
    reasoner.run = AsyncMock(side_effect=responses)

    result = await reasoner.run_turn(msg=msg, session=session)

    # Each request can shrink its context while the current user input remains.
    expected_windows = [6, 6, 6, 6, 6, 3, 0][: len(responses)]
    for call, window in zip(
        reasoner.run.await_args_list, expected_windows, strict=True
    ):
        expected_history = source_history[-window:] if window else []
        assert call.args[0] == [
            *expected_history,
            {"role": "user", "content": msg.content},
        ]
    attempts = result.context_retry["attempts"]
    assert isinstance(attempts, list)
    assert [attempt["history_window"] for attempt in attempts] == expected_windows
    assert isinstance(result.reply, str)
    if success_attempt is None:
        expected_reply = (
            "安全审查" if error_type is ContentSafetyError else "上下文过长"
        )
        assert expected_reply in result.reply
        assert result.context_retry["selected_plan"] is None
    else:
        assert result.reply == "recovered"
        assert result.context_retry["selected_plan"] == (
            "trim_skills_catalog"
            if success_attempt == 1
            else "trim_retrieved_memory_history"
        )

    # Reload independently before and after the caller persists the turn result.
    reloaded = SessionManager(tmp_path).get_or_create(session.key)
    assert reloaded.messages == original_messages
    assert reloaded.last_consolidated == last_consolidated
    assert session.messages == original_messages
    assert session.last_consolidated == last_consolidated
    assert session.consolidation_requested is True

    session.add_message("assistant", result.reply)
    await manager.save_async(session)
    reloaded = SessionManager(tmp_path).get_or_create(session.key)
    assert reloaded.messages[:-1] == original_messages
    assert reloaded.messages[-1]["content"] == result.reply
    assert reloaded.messages[-1]["seq"] == total_messages
    assert reloaded.last_consolidated == last_consolidated


async def test_run_turn_repairs_rendered_input_budget_before_reasoning(tmp_path):
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("cli:budget")
    session.add_message("user", "x" * 1000)
    await manager.save_async(session)
    msg = SimpleNamespace(
        channel="cli",
        chat_id="budget",
        content="hello",
        media=[],
        timestamp=datetime.now(timezone.utc),
    )

    async def consolidate(_session_key: str, _content: str) -> bool:
        session.last_consolidated = len(session.messages)
        return True

    reasoner = DefaultReasoner(
        llm=LLMServices(provider=AsyncMock(), light_provider=AsyncMock()),
        llm_config=LLMConfig(),
        tools=ToolRegistry(),
        discovery=ToolDiscoveryState(),
        tool_search_enabled=False,
        memory_window=40,
        context=AsyncMock(),
        session_manager=manager,
        memory_consolidator=SimpleNamespace(
            ensure_memory_consolidation=AsyncMock(side_effect=consolidate)
        ),
        memory_input_token_threshold=100,
    )
    reasoner.render_prompt = AsyncMock(
        side_effect=lambda request: PromptRenderResult(
            messages=[
                *request.history,
                {"role": "user", "content": request.content},
            ]
        )
    )
    reasoner.run = AsyncMock(return_value=ReasonerResult(reply="ok"))

    result = await reasoner.run_turn(msg=msg, session=session)

    assert result.reply == "ok"
    reasoner._memory_consolidator.ensure_memory_consolidation.assert_awaited_once_with(
        "cli:budget", "hello"
    )
    assert reasoner.run.await_args.args[0] == [{"role": "user", "content": "hello"}]
