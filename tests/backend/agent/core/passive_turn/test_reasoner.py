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
from agent.tools.turn_scope import current_tool_turn
from bus.events import InboundMessage
from conversation.context_scope import ContextView, UserContextThreads
from core.common.message_source import SENDER_IS_USER_KEY, MessageSource
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
    msg = InboundMessage(
        channel="cli",
        sender="user",
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
    scopes, released = [], []
    pending = iter(responses)

    async def attempt(*args, **kwargs):
        scope = current_tool_turn()
        scopes.append(scope)
        assert not released

        async def release():
            released.append(scope)

        scope.own("desktop", release)
        response = next(pending)
        if isinstance(response, Exception):
            raise response
        return response

    reasoner.run = AsyncMock(side_effect=attempt)

    result = await reasoner.run_turn(msg=msg, session=session)
    assert all(scope is scopes[0] for scope in scopes)
    assert released == [scopes[0]] and scopes[0].closed

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
    msg = InboundMessage(
        channel="cli",
        sender="user",
        chat_id="budget",
        content="hello",
        media=[],
        timestamp=datetime.now(timezone.utc),
    )

    async def consolidate(
        _session_key: str, _content: str, _scope: object, **kwargs
    ) -> bool:
        session.last_consolidated = len(session.messages)
        return True

    from agent.provider import LLMProvider
    from agent.prompting.input_budget import BudgetPolicy

    provider = LLMProvider(
        api_key="test",
        context_window_tokens=400,
        max_output_tokens=50,
        budget_policy=BudgetPolicy(safety_margin_tokens=10),
    )
    reasoner = DefaultReasoner(
        llm=LLMServices(provider=provider, light_provider=provider),
        llm_config=LLMConfig(max_tokens=50),
        tools=ToolRegistry(),
        discovery=ToolDiscoveryState(),
        tool_search_enabled=False,
        memory_window=40,
        context=AsyncMock(),
        session_manager=manager,
        memory_consolidator=SimpleNamespace(
            ensure_memory_consolidation=AsyncMock(side_effect=consolidate)
        ),
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
        "cli:budget", "hello", None, input_token_threshold=160
    )
    assert reasoner.run.await_args.args[0] == [{"role": "user", "content": "hello"}]
    await provider.aclose()


@pytest.mark.parametrize(
    "scope,sender_is_user,expected",
    [
        ("external", False, True),
        ("external", True, False),
        ("user", False, False),
        (None, False, False),
    ],
    ids=["external-other", "external-bound-user", "user-context", "no-view"],
)
async def test_run_turn_restricts_tools_only_for_external_non_user_sender(
    tmp_path, scope, sender_is_user, expected
):
    """#489：只有外部上下文里非已绑定用户发起的回合受工具白名单限制。"""
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("qq:group-1")
    msg = InboundMessage(
        channel="qq",
        sender="someone",
        chat_id="group-1",
        content="hi",
        media=[],
        timestamp=datetime.now(timezone.utc),
        metadata={SENDER_IS_USER_KEY: True} if sender_is_user else {},
    )
    context_view = (
        ContextView(
            scope=scope,
            user_threads=UserContextThreads(
                role_id="mira", bound_chat_thread_ids=frozenset()
            ),
        )
        if scope is not None
        else None
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
        return_value=PromptRenderResult(messages=[{"role": "user", "content": "hi"}])
    )
    reasoner.run = AsyncMock(return_value=ReasonerResult(reply="ok"))

    await reasoner.run_turn(msg=msg, session=session, context_view=context_view)

    assert reasoner.run.await_args.kwargs["external_restricted"] is expected


async def test_real_turn_history_append_uses_usage_anchor_with_replaced_context_frame(
    tmp_path, monkeypatch
):
    from agent.context import ContextBuilder
    from agent.provider import LLMProvider
    from core.roles import RoleStore

    class Memory:
        def read_profile(self):
            return ""

        def read_self(self):
            return ""

        def read_recent_context(self):
            return ""

        def get_memory_context(self):
            return ""

    manager = SessionManager(tmp_path)
    roles = RoleStore(tmp_path)
    roles.create_role(role_id="mira", name="Mira", system_prompt="固定角色约束")
    session = manager.get_or_create("cli:anchor")
    session.metadata["role_id"] = "mira"
    monkeypatch.setattr(
        "agent.core.passive_turn.reasoning_loop.fetch_role_mood",
        AsyncMock(return_value=None),
    )
    provider = LLMProvider(
        api_key="test", context_window_tokens=128000, max_output_tokens=32768
    )
    estimates = []
    sent = []

    async def create(kwargs, **unused):
        estimates.append(provider._budget_for_request(kwargs).estimate)
        sent.append(deepcopy(kwargs))
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="收到", tool_calls=[]),
                    finish_reason="stop",
                )
            ],
            usage=SimpleNamespace(
                prompt_tokens=5000, completion_tokens=10, total_tokens=5010
            ),
        )

    provider._create_with_retry = create
    reasoner = DefaultReasoner(
        llm=LLMServices(provider=provider, light_provider=provider),
        llm_config=LLMConfig(model="explicit"),
        tools=ToolRegistry(),
        discovery=ToolDiscoveryState(),
        tool_search_enabled=False,
        memory_window=40,
        context=ContextBuilder(tmp_path, Memory(), runtime_roles=RoleStore(tmp_path)),
        session_manager=manager,
    )
    first = InboundMessage(
        channel="cli",
        sender="user",
        chat_id="anchor",
        content="记住我们正在编写测试",
        timestamp=datetime(2026, 10, 2, 10, 0, tzinfo=timezone.utc),
    )
    result = await reasoner.run_turn(
        msg=first, session=session, retrieved_memory_block="旧检索"
    )
    session.add_message(
        "user",
        first.content,
        llm_user_content=result.context_retry["llm_user_content"],
        metadata={"message_source": MessageSource.from_inbound(first).to_metadata()},
    )
    session.add_message("assistant", result.reply)
    second = InboundMessage(
        channel="cli",
        sender="user",
        chat_id="anchor",
        content="继续下一步",
        timestamp=datetime(2026, 10, 2, 10, 1, tzinfo=timezone.utc),
    )
    result = await reasoner.run_turn(
        msg=second, session=session, retrieved_memory_block="新的检索候选，比原来更长"
    )
    assert [item.source for item in estimates] == ["local", "anchor_delta"]
    assert estimates[1].tokens > 5000
    assert sent[1]["messages"][1] == sent[0]["messages"][-1]
    usage = result.context_retry["request_usage"]
    assert isinstance(usage, dict)
    assert usage["last_request"]["prompt_tokens"] == 5000
    assert usage["cumulative"]["completion_tokens"] == 10
    await provider.aclose()


async def test_model_budget_forces_existing_consolidation_even_below_old_history_threshold(
    tmp_path,
):
    from agent.provider import LLMProvider
    from agent.prompting.input_budget import BudgetPolicy

    manager = SessionManager(tmp_path)
    session = manager.get_or_create("cli:small-model")
    session.add_message("user", "中文" * 250)
    provider = LLMProvider(
        api_key="test",
        context_window_tokens=1200,
        max_output_tokens=200,
        budget_policy=BudgetPolicy(safety_margin_tokens=20),
    )
    calls = []

    async def consolidate(key, content, scope, *, input_token_threshold):
        calls.append((key, input_token_threshold))
        session.last_consolidated = len(session.messages)
        return True

    reasoner = DefaultReasoner(
        llm=LLMServices(provider=provider, light_provider=provider),
        llm_config=LLMConfig(model="small", max_tokens=100),
        tools=ToolRegistry(),
        discovery=ToolDiscoveryState(),
        tool_search_enabled=False,
        memory_window=40,
        context=AsyncMock(),
        session_manager=manager,
        memory_consolidator=SimpleNamespace(ensure_memory_consolidation=consolidate),
    )
    reasoner.render_prompt = AsyncMock(
        side_effect=lambda request: PromptRenderResult(
            messages=[*request.history, {"role": "user", "content": request.content}]
        )
    )
    reasoner.run = AsyncMock(return_value=ReasonerResult(reply="ok"))
    result = await reasoner.run_turn(
        msg=InboundMessage(
            channel="cli", sender="user", chat_id="small-model", content="继续"
        ),
        session=session,
    )
    assert result.reply == "ok"
    assert calls == [(session.key, 480)]
    assert reasoner.run.call_args.args[0] == [{"role": "user", "content": "继续"}]
    await provider.aclose()
