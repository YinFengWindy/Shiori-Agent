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
from session.manager.consolidation import ConsolidationCommitRequest
from agent.tools.base import Tool


class _ArchivedTool(Tool):
    name = "archived_tool"
    description = "A tool discovered by an older turn"
    parameters = {"type": "object", "properties": {}}

    async def execute(self, **kwargs):
        return "ok"


@pytest.mark.parametrize(
    "case",
    [
        "normal",
        "minimal",
        "image",
        "too_large",
        "memory_failure",
        "consumer_failure",
        "summary_failure",
        "provider_limit",
        "provider_error",
        "unexpected_tool",
        "external",
    ],
)
async def test_minimal_request_uses_real_prompt_controller_and_transport(
    memory_harness, monkeypatch, case
):
    import json
    from agent.context import ContextBuilder
    from agent.provider import LLMProvider
    from agent.prompting.input_budget import BudgetPolicy
    from bus.event_bus import EventBus
    from conversation.context_scope import history_start, turn_context_view
    from conversation.service import network_thread_id
    from core.compaction import CompactionFailedError
    from core.roles import RoleStore
    from shiori_sdk.context import ContextBudgetObserved

    h = memory_harness
    roles = RoleStore(h.manager.workspace)
    roles.create_role(role_id="mira", name="Mira", system_prompt="保留角色约束")
    session = h.manager.get_or_create(
        "role:mira" if case == "external" else "cli:minimal"
    )
    session.metadata["role_id"] = "mira"
    thread = network_thread_id("mira", "qq", "group") if case == "external" else ""
    view = turn_context_view(h.manager.workspace, "mira", thread) if thread else None
    for index in range(3):
        session.add_message("user", f"old task {index}", thread_id=thread)
        session.add_message("assistant", "done", thread_id=thread)
    if thread:
        session.add_message(
            "user",
            "OTHER_GROUP_SECRET",
            thread_id=network_thread_id("mira", "qq", "other"),
        )
        session.add_message(
            "assistant",
            "other reply",
            thread_id=network_thread_id("mira", "qq", "other"),
        )
    h.manager.save(session)
    original = deepcopy(session.messages)
    context = ContextBuilder(
        h.manager.workspace, h.maintenance._store, runtime_roles=roles
    )
    tool = _ArchivedTool()
    tool.description = "工具目录 " * 3000
    tool.execute = AsyncMock(return_value="must not execute")
    registry = ToolRegistry()
    registry.register(tool, always_on=True)
    provider = LLMProvider(
        api_key="test",
        model_context_window=100000 if case == "normal" else 20000,
        default_max_tokens=2000,
        budget_policy=BudgetPolicy(safety_margin_tokens=100),
    )
    events = []
    bus = EventBus()
    bus.on(ContextBudgetObserved, lambda event: events.append(event))
    reasoner = DefaultReasoner(
        LLMServices(provider, provider),
        LLMConfig(model="controlled", max_tokens=300),
        registry,
        ToolDiscoveryState(),
        tool_search_enabled=False,
        memory_window=40,
        context=context,
        session_manager=h.manager,
        compaction_memory=h.maintenance,
        event_bus=bus,
    )
    monkeypatch.setattr(
        "agent.core.passive_turn.reasoning_loop.fetch_role_mood",
        AsyncMock(return_value=None),
    )
    if case == "memory_failure":
        h.fail = True
    if case == "consumer_failure":
        h.maintenance._after_consolidation = AsyncMock(
            side_effect=RuntimeError("consumer failed")
        )
    sent = []

    async def transport(kwargs, **unused):
        if "Rewrite the current working state" in kwargs["messages"][0]["content"]:
            if case == "summary_failure":
                raise RuntimeError("summary unavailable")
            data = json.loads(kwargs["messages"][-1]["content"])
            text = json.dumps(
                {
                    "tasks": "continue tea plan",
                    "constraints": "keep intent",
                    "decisions": "",
                    "unfinished": "next",
                    "tool_state": "",
                    "entities": "tea",
                    "source_message_ids": [data["messages"][0]["id"]],
                }
            )
        else:
            sent.append(deepcopy(kwargs))
            if case == "provider_limit":
                raise ContextLengthError("real provider limit")
            if case == "provider_error":
                raise OSError("model connection failed")
            text = "continue tea plan"
        calls = (
            [
                SimpleNamespace(
                    id="forbidden",
                    function=SimpleNamespace(name="archived_tool", arguments="{}"),
                )
            ]
            if case == "unexpected_tool" and sent
            else []
        )
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=text, tool_calls=calls),
                    finish_reason="stop",
                )
            ],
            usage=None,
        )

    provider._create_with_retry = transport
    current = "保留当前意图" + ("巨大的输入" * 5000 if case == "too_large" else "")
    media = []
    if case == "image":
        image = h.manager.workspace / "input.png"
        image.write_bytes(b"fake-image" * 20000)
        media = [str(image)]
    msg = InboundMessage(
        channel="qq" if thread else "cli",
        sender="friend" if thread else "user",
        chat_id="group" if thread else "minimal",
        content=current,
        media=media,
    )
    expected = {
        "too_large": "minimal_budget",
        "memory_failure": "memory",
        "summary_failure": "summary",
        "provider_limit": "provider",
    }
    try:
        if case in expected:
            with pytest.raises(CompactionFailedError) as caught:
                await reasoner.run_turn(
                    msg=msg,
                    session=session,
                    context_view=view,
                    retrieved_memory_block="OPTIONAL_RETRIEVAL " * 1500,
                    extra_hints=["OPTIONAL_HINT call archived_tool " * 300],
                )
            assert caught.value.result.failure_stage == expected[case]
            if case not in {"memory_failure"}:
                assert caught.value.result.memory_committed
            if case in {"memory_failure", "summary_failure"}:
                assert caught.value.result.degradation_attempts == 0
            if case == "provider_limit":
                assert len(sent) == 1
                assert caught.value.result.failure_kind == "provider_context_length"
            else:
                assert not sent
        elif case == "provider_error":
            # Ordinary provider failures keep their type for the pipeline boundary.
            with pytest.raises(OSError, match="model connection failed"):
                await reasoner.run_turn(
                    msg=msg,
                    session=session,
                    context_view=view,
                    retrieved_memory_block="OPTIONAL_RETRIEVAL " * 1500,
                    extra_hints=["OPTIONAL_HINT call archived_tool " * 300],
                )
            assert len(sent) == 1
            latest = reasoner._compaction.latest(session.key, view)
            assert latest is not None and latest["phase"] != "failed"
        elif case == "unexpected_tool":
            with pytest.raises(CompactionFailedError) as caught:
                await reasoner.run_turn(
                    msg=msg,
                    session=session,
                    retrieved_memory_block="OPTIONAL_RETRIEVAL " * 1500,
                )
        else:
            result = await reasoner.run_turn(
                msg=msg,
                session=session,
                context_view=view,
                retrieved_memory_block=(
                    "" if case == "normal" else "OPTIONAL_RETRIEVAL " * 1500
                ),
                extra_hints=(
                    []
                    if case == "normal"
                    else ["OPTIONAL_HINT call archived_tool " * 3000]
                ),
            )
            assert result.reply == "continue tea plan"
            if case == "normal":
                assert not result.context_retry["compaction"]
            else:
                final = sent[-1]
                text = json.dumps(final, ensure_ascii=False)
                assert not final.get("tools")
                assert (
                    "保留角色约束" in text
                    and current in text
                    and "continue tea plan" in text
                )
                assert "OPTIONAL_RETRIEVAL" not in text and "OPTIONAL_HINT" not in text
                assert "工具目录 " * 3 not in text and "OTHER_GROUP_SECRET" not in text
                outcomes = result.context_retry["compaction"]
                assert isinstance(outcomes, list) and outcomes[-1]["degraded"]
                if case == "image":
                    assert "data:image/png;base64," in text and len(text) > 200000
                final_fact = events[-1].status
                assert final_fact["after_source"] == "local"
                assert final_fact["final_budget"]["schema_tokens"] == 0
                assert final_fact["final_budget"]["output_reservation_tokens"] == 300
                assert (
                    final_fact["request_usage"]["last_request"]["prompt_tokens"] is None
                )
                assert "base64" not in json.dumps(final_fact)
        assert history_start(session, view) == 0
        assert session.messages == original
        tool.execute.assert_not_awaited()
    finally:
        await provider.aclose()


@pytest.mark.parametrize("error_type", [ContentSafetyError])
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
    session.consolidation_requested = True
    await manager.save_async(session)
    if last_consolidated:
        await manager.commit_consolidation(
            ConsolidationCommitRequest(
                session.key,
                tuple(m["id"] for m in session.messages),
                expected_last_consolidated=0,
                last_consolidated=last_consolidated,
            ),
            AsyncMock(),
        )
        prepared = await manager.prepare_window(session.key, None, keep_turns=2)
        assert prepared is not None and await manager.commit_window(
            prepared, "state", prepared.removed_message_ids
        )
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
        from agent.core.passive_turn.compaction import with_working_summary

        assert call.args[0] == with_working_summary(
            [
                *expected_history,
                {"role": "user", "content": msg.content},
            ],
            "state" if last_consolidated else "",
        )
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
            thread_id="qq:group-1",
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
        api_key="test", model_context_window=128000, default_max_tokens=32768
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


@pytest.mark.parametrize(
    "boundary",
    [
        "initial",
        "tool",
        "recovery",
        "finalize",
        "unfit",
        "safety_after_tool",
        "provider_retry",
        "provider_retry_safety",
        "provider_retry_failure",
        "provider_retry_tool",
    ],
)
async def test_all_request_boundaries_compact_without_replaying_current_tools(
    memory_harness, boundary, monkeypatch
):
    import json
    from agent.provider import LLMProvider
    from agent.prompting.input_budget import BudgetPolicy
    from conversation.context_scope import history_start

    h = memory_harness
    session = h.manager.get_or_create("cli:four-boundaries")
    session.metadata["role_id"] = "mira"
    monkeypatch.setattr(
        "agent.core.passive_turn.reasoning_loop.fetch_role_mood",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "agent.core.passive_turn.reasoning_result.fetch_role_mood",
        AsyncMock(return_value=None),
    )
    width = {
        "initial": 5000,
        "tool": 3000,
        "recovery": 3000,
        "finalize": 3000,
        "unfit": 3000,
        "safety_after_tool": 3000,
        "provider_retry": 3000,
        "provider_retry_safety": 3000,
        "provider_retry_failure": 3000,
        "provider_retry_tool": 3000,
    }[boundary]
    for index in range(5):
        session.add_message("user", f"task {index} " + "x" * width)
        session.add_message(
            "assistant",
            "noted",
            tool_chain=(
                [
                    {
                        "calls": [
                            {
                                "call_id": "past",
                                "name": "archived_tool",
                                "arguments": {},
                                "result": "OLD_TOOL_HISTORY_MUST_NOT_REAPPEAR",
                            }
                        ]
                    }
                ]
                if index == 0
                else []
            ),
        )
    h.manager.save(session)

    class SideEffectTool(Tool):
        name = "side_effect"
        description = "Execute the current operation"
        parameters = {"type": "object", "properties": {}}

        def __init__(self):
            self.calls = 0

        async def execute(self, **kwargs):
            self.calls += 1
            return "result " + "y" * 9000

    tool = SideEffectTool()
    registry = ToolRegistry()
    if boundary != "recovery":
        registry.register(tool, always_on=True)
        registry.register(_ArchivedTool())
    provider = LLMProvider(
        api_key="test",
        model_context_window=10000,
        default_max_tokens=200,
        budget_policy=BudgetPolicy(safety_margin_tokens=20),
    )
    sent, summary_inputs = [], []

    async def create(kwargs, **unused):
        calls = []
        if "Rewrite the current working state" in kwargs["messages"][0]["content"]:
            data = json.loads(kwargs["messages"][-1]["content"])
            summary_inputs.append(data)
            if boundary == "initial":
                # A concurrent settings save cannot change this execution's policy.
                reasoner._llm_config.compaction_retained_turns = 0
            text = json.dumps(
                {
                    "tasks": "continue the original task",
                    "constraints": "preserve operation",
                    "decisions": "",
                    "unfinished": "next step",
                    "tool_state": "past tool completed",
                    "entities": "task",
                    "source_message_ids": [data["messages"][0]["id"]],
                }
            )
            tokens = 200
        else:
            sent.append(deepcopy(kwargs))
            if len(sent) == 1 and boundary in {
                "tool",
                "finalize",
                "unfit",
                "safety_after_tool",
                "provider_retry",
                "provider_retry_safety",
                "provider_retry_failure",
                "provider_retry_tool",
            }:
                text = "working"
                calls = [
                    SimpleNamespace(
                        id="current-call",
                        function=SimpleNamespace(name="side_effect", arguments="{}"),
                    )
                ]
            elif boundary.startswith("provider_retry") and len(sent) == 2:
                raise ContextLengthError("actual provider rejected request")
            elif boundary == "provider_retry_tool" and len(sent) == 3:
                text = "must not execute twice"
                calls = [
                    SimpleNamespace(
                        id="again",
                        function=SimpleNamespace(name="side_effect", arguments="{}"),
                    )
                ]
            elif boundary == "provider_retry_safety" and len(sent) == 3:
                raise ContentSafetyError("degraded result rejected")
            elif boundary == "provider_retry_failure" and len(sent) == 3:
                raise OSError("network unavailable")
            elif len(sent) == 2 and boundary == "safety_after_tool":
                raise ContentSafetyError("current tool output rejected")
            elif len(sent) == 1 and boundary == "recovery":
                text = ""
            else:
                text = "continued the original task"
            tokens = (
                7480
                if boundary == "recovery" and len(sent) == 1
                else provider._budget_for_request(kwargs).estimate.tokens
            )
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=text, tool_calls=calls),
                    finish_reason="tool_calls" if calls else "stop",
                )
            ],
            usage=SimpleNamespace(
                prompt_tokens=tokens, completion_tokens=5, total_tokens=tokens + 5
            ),
        )

    provider._create_with_retry = create
    reasoner = DefaultReasoner(
        llm=LLMServices(provider, provider),
        llm_config=LLMConfig(
            model="controlled",
            max_tokens=200,
            max_iterations=1 if boundary == "finalize" else 5,
            # Leave no turns for the forced retry, so a rejection must degrade.
            compaction_retained_turns=0 if boundary.startswith("provider_retry") else 2,
        ),
        tools=registry,
        discovery=ToolDiscoveryState(),
        tool_search_enabled=True,
        memory_window=40,
        context=AsyncMock(),
        session_manager=h.manager,
        compaction_memory=h.maintenance,
    )
    reasoner.render_prompt = AsyncMock(
        side_effect=lambda request: PromptRenderResult(
            messages=[
                {"role": "system", "content": "system constraint"},
                *request.history,
                {"role": "user", "content": request.content},
            ]
        )
    )
    try:
        if boundary == "safety_after_tool":
            with pytest.raises(
                ContentSafetyError, match="current tool output rejected"
            ):
                await reasoner.run_turn(
                    msg=InboundMessage(
                        channel="cli",
                        sender="user",
                        chat_id="four-boundaries",
                        content="current input",
                    ),
                    session=session,
                )
            assert tool.calls == 1 and len(sent) == 2
            assert history_start(session, None) > 0
            assert session.maintenance_progress.summaries
            return
        if boundary.startswith("provider_retry"):
            from core.compaction import CompactionFailedError

            args = dict(
                msg=InboundMessage(
                    channel="cli",
                    sender="user",
                    chat_id="four-boundaries",
                    content="do once",
                ),
                session=session,
            )
            if boundary == "provider_retry_tool":
                with pytest.raises(CompactionFailedError):
                    await reasoner.run_turn(**args)
                latest = reasoner._compaction.latest(session.key, None)
                assert (
                    latest["phase"] == "failed"
                    and latest["failure_stage"] == "response"
                )
                assert latest["tools_disabled"]
            elif boundary == "provider_retry_safety":
                with pytest.raises(
                    ContentSafetyError, match="degraded result rejected"
                ):
                    await reasoner.run_turn(**args)
            elif boundary == "provider_retry_failure":
                with pytest.raises(OSError, match="network unavailable"):
                    await reasoner.run_turn(**args)
                compaction = reasoner._compaction.latest(session.key, None)
                assert compaction is not None and compaction["phase"] != "failed"
                latest = reasoner._compaction.latest(session.key, None, request=True)
                assert latest is not None
                assert latest["failure_kind"] == "provider_error"
                assert latest["request_usage"]["last_request"]["prompt_tokens"] is None
                assert (
                    latest["request_usage"]["cumulative"]["prompt_tokens_unknown_calls"]
                    == 2
                )
                assert latest["request_usage"]["cumulative"]["prompt_tokens"] > 0
            else:
                result = await reasoner.run_turn(**args)
                outcomes = result.context_retry["compaction"]
                assert isinstance(outcomes, list)
                assert outcomes[-1]["degraded"] and outcomes[-1]["memory_committed"]
                assert any(item["committed"] for item in outcomes)
                usage = result.context_retry["request_usage"]
                assert isinstance(usage, dict)
                assert usage["cumulative"]["prompt_tokens_unknown_calls"] == 1
            assert tool.calls == 1 and len(sent) == 3
            assert not sent[-1].get("tools")
            assert "OLD_TOOL_HISTORY_MUST_NOT_REAPPEAR" not in str(sent[-1]["messages"])
            assert "y" * 9000 in str(sent[-1]["messages"])
            assert not any(
                m.get("tool_calls") or m.get("role") == "tool"
                for m in sent[-1]["messages"]
            )
            return
        if boundary == "unfit":
            result = await reasoner.run_turn(
                msg=InboundMessage(
                    channel="cli",
                    sender="user",
                    chat_id="four-boundaries",
                    content="current" + "z" * 3000,
                ),
                session=session,
            )
            outcomes = result.context_retry["compaction"]
            assert isinstance(outcomes, list)
            outcome = outcomes[-1]
            # Over the target but within the hard limit: commit, keep tools.
            assert outcome["committed"] and not outcome["degraded"]
            assert outcome["memory_committed"] and not outcome["tools_disabled"]
            assert tool.calls == 1 and len(sent) == 2
            assert sent[-1].get("tools")
            assert "OLD_TOOL_HISTORY_MUST_NOT_REAPPEAR" not in str(sent[-1]["messages"])
            assert "y" * 9000 in str(sent[-1]["messages"])
            budget = provider.input_budget(
                messages=sent[-1]["messages"],
                tools=sent[-1]["tools"],
                model="controlled",
                max_tokens=200,
            )
            assert budget is not None
            assert budget.target_tokens <= budget.estimate.tokens
            assert budget.estimate.tokens < budget.input_limit_tokens
            assert history_start(session, None) > 0
            return
        result = await reasoner.run_turn(
            msg=InboundMessage(
                channel="cli",
                sender="user",
                chat_id="four-boundaries",
                content="current input must survive",
            ),
            session=session,
        )
        assert result.reply == "continued the original task"
        outcomes = result.context_retry["compaction"]
        assert isinstance(outcomes, list) and outcomes[-1]["committed"]
        assert outcomes[-1]["configured_retained_turns"] == 2
        assert summary_inputs and history_start(session, None) > 0
        assert len(session.messages) == 10
        final = sent[-1]
        serialized = json.dumps(final)
        assert (
            "current input must survive" in serialized
            and "[working_state]" in serialized
        )
        assert "archived_tool" not in [
            schema["function"]["name"] for schema in final.get("tools", [])
        ]
        if boundary in {"tool", "finalize", "unfit", "safety_after_tool"}:
            assert tool.calls == 1
            assert "current-call" in serialized and "y" * 9000 in serialized
        else:
            assert tool.calls == 0
        if boundary == "recovery":
            assert final["messages"][-1]["role"] == "user"
            assert "正式回复" in final["messages"][-1]["content"]
        budget = provider.input_budget(
            messages=final["messages"],
            tools=final.get("tools", []),
            model="controlled",
            max_tokens=200,
        )
        assert budget.estimate.tokens < budget.input_limit_tokens
    finally:
        await provider.aclose()


async def test_real_prompt_renderer_continues_with_working_state_and_bounded_originals(
    memory_harness, monkeypatch
):
    import json
    from agent.context import ContextBuilder
    from agent.provider import LLMProvider
    from agent.prompting.input_budget import BudgetPolicy
    from core.roles import RoleStore

    h = memory_harness
    roles = RoleStore(h.manager.workspace)
    roles.create_role(role_id="mira", name="Mira", system_prompt="必须保留的角色约束")
    session = h.manager.get_or_create("cli:real-render")
    session.metadata["role_id"] = "mira"
    for index in range(5):
        session.add_message("user", f"phase {index}: " + "work " * 6000)
        session.add_message("assistant", f"completed phase {index}")
    h.manager.save(session)
    monkeypatch.setattr(
        "agent.core.passive_turn.reasoning_loop.fetch_role_mood",
        AsyncMock(return_value=None),
    )
    provider = LLMProvider(
        api_key="test",
        model_context_window=64000,
        default_max_tokens=2000,
        budget_policy=BudgetPolicy(safety_margin_tokens=200),
    )
    spoken = []

    async def create(kwargs, **unused):
        if "Rewrite the current working state" in kwargs["messages"][0]["content"]:
            source = json.loads(kwargs["messages"][-1]["content"])
            content = json.dumps(
                {
                    "tasks": "deliver original report",
                    "constraints": "do not repeat write",
                    "decisions": "use report.txt",
                    "unfinished": "verify report",
                    "tool_state": "write finished",
                    "entities": "report.txt",
                    "source_message_ids": [source["messages"][0]["id"]],
                }
            )
        else:
            spoken.append(deepcopy(kwargs))
            content = "verify report.txt"
        tokens = provider._budget_for_request(kwargs).estimate.tokens
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=content, tool_calls=[]),
                    finish_reason="stop",
                )
            ],
            usage=SimpleNamespace(
                prompt_tokens=tokens, completion_tokens=50, total_tokens=tokens + 50
            ),
        )

    provider._create_with_retry = create
    reasoner = DefaultReasoner(
        llm=LLMServices(provider, provider),
        llm_config=LLMConfig(model="controlled", max_tokens=2000),
        tools=ToolRegistry(),
        discovery=ToolDiscoveryState(),
        tool_search_enabled=False,
        memory_window=40,
        context=ContextBuilder(
            h.manager.workspace, h.maintenance._store, runtime_roles=roles
        ),
        session_manager=h.manager,
        compaction_memory=h.maintenance,
    )
    try:
        result = await reasoner.run_turn(
            msg=InboundMessage(
                channel="cli",
                sender="user",
                chat_id="real-render",
                content="请接着完成报告",
            ),
            session=session,
            retrieved_memory_block="检索内容也计入完整预算",
        )
        outcomes = result.context_retry["compaction"]
        assert result.reply == "verify report.txt"
        assert isinstance(outcomes, list) and outcomes[-1]["committed"]
        request = spoken[-1]
        text = json.dumps(request, ensure_ascii=False)
        assert "必须保留的角色约束" in text
        assert "deliver original report" in text and "verify report" in text
        assert "请接着完成报告" in text and "检索内容也计入完整预算" in text
        assert "phase 4" in text and "phase 0:" not in text
        budget = provider.input_budget(
            messages=request["messages"], tools=[], model="controlled", max_tokens=2000
        )
        assert budget.estimate.tokens < budget.target_tokens
    finally:
        await provider.aclose()


async def test_provider_context_rejection_after_tools_never_restarts_turn(
    memory_harness,
):
    from agent.provider import LLMResponse, ToolCall
    from core.compaction import CompactionFailedError

    h = memory_harness
    session = h.manager.get_or_create("cli:reject")
    tool = _ArchivedTool()
    tool.execute = AsyncMock(return_value="side effect finished")
    registry = ToolRegistry()
    registry.register(tool)
    provider = AsyncMock()
    provider.chat.side_effect = [
        LLMResponse(content="", tool_calls=[ToolCall("once", "archived_tool", {})]),
        ContextLengthError("provider rejected input"),
    ]
    reasoner = DefaultReasoner(
        llm=LLMServices(provider, provider),
        llm_config=LLMConfig(),
        tools=registry,
        discovery=ToolDiscoveryState(),
        tool_search_enabled=False,
        memory_window=40,
        context=AsyncMock(),
        session_manager=h.manager,
    )
    reasoner.render_prompt = AsyncMock(
        return_value=PromptRenderResult(
            messages=[{"role": "user", "content": "do once"}]
        )
    )
    with pytest.raises(CompactionFailedError) as caught:
        await reasoner.run_turn(
            msg=InboundMessage(
                channel="cli", sender="user", chat_id="reject", content="do once"
            ),
            session=session,
        )
    assert caught.value.result.failure_stage == "provider"
    assert tool.execute.await_count == 1 and provider.chat.await_count == 2


@pytest.mark.parametrize("scope", ["session", "external"])
async def test_safety_retry_reads_committed_compaction_with_frozen_input_and_history(
    memory_harness, monkeypatch, scope
):
    import json
    from agent.provider import LLMProvider
    from agent.prompting.input_budget import BudgetPolicy
    from conversation.context_scope import history_start, turn_context_view
    from conversation.service import network_thread_id
    from session.maintenance_progress import window_key

    h = memory_harness
    key = "role:mira" if scope == "external" else "cli:safety-compaction"
    session = h.manager.get_or_create(key)
    session.metadata["role_id"] = "mira"
    thread = network_thread_id("mira", "qq", "group") if scope == "external" else ""
    view = turn_context_view(h.manager.workspace, "mira", thread) if thread else None
    session.add_message(
        "user",
        "x" * 24000,
        thread_id=thread,
        metadata={"message_source": {"sender_id": "old-member", "group_name": "group"}},
    )
    session.add_message(
        "assistant",
        "keep this task",
        thread_id=thread,
        tool_chain=[
            {
                "calls": [
                    {
                        "call_id": "historic",
                        "name": "archived_tool",
                        "arguments": {},
                        "result": "historic operation finished",
                    }
                ]
            }
        ],
    )
    h.manager.save(session)
    initial_ids = [message["id"] for message in session.messages]
    registry = ToolRegistry()
    registry.register(_ArchivedTool(), external_allowed=True)
    monkeypatch.setattr(
        "agent.core.passive_turn.reasoning_loop.fetch_role_mood",
        AsyncMock(return_value=None),
    )
    provider = LLMProvider(
        api_key="test",
        model_context_window=10000,
        default_max_tokens=200,
        budget_policy=BudgetPolicy(safety_margin_tokens=20),
    )
    msg = InboundMessage(
        channel="qq" if thread else "cli",
        sender="friend",
        chat_id="group" if thread else "safety-compaction",
        content="continue the task",
        media=["original.png"],
    )
    sent, renders = [], []
    summary_calls = 0

    async def create(kwargs, **unused):
        nonlocal summary_calls
        if "Rewrite the current working state" in kwargs["messages"][0]["content"]:
            summary_calls += 1
            source = json.loads(kwargs["messages"][-1]["content"])
            text = json.dumps(
                {
                    "tasks": "continue the task",
                    "constraints": "do not repeat historic operation",
                    "decisions": "",
                    "unfinished": "next step",
                    "tool_state": "historic operation done",
                    "entities": "task",
                    "source_message_ids": [source["messages"][0]["id"]],
                }
            )
        else:
            sent.append(deepcopy(kwargs))
            if len(sent) == 1:
                # New arrivals belong to the next execution, even during a safety retry.
                session.add_message(
                    "user",
                    "future message must stay out",
                    thread_id=thread,
                    metadata={"message_source": {"sender_id": "future-member"}},
                )
                session.add_message("assistant", "future answer", thread_id=thread)
                await h.manager.save_async(session)
                msg.content = "mutated input must stay out"
                msg.media[:] = ["changed.png"]
                reasoner._llm_config.compaction_retained_turns = 0
                raise ContentSafetyError("reject once after successful compaction")
            text = "continued from working state"
        tokens = provider._budget_for_request(kwargs).estimate.tokens
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=text, tool_calls=[]),
                    finish_reason="stop",
                )
            ],
            usage=SimpleNamespace(
                prompt_tokens=tokens, completion_tokens=20, total_tokens=tokens + 20
            ),
        )

    async def render(request):
        renders.append(deepcopy(request))
        current = [
            {
                "type": "image_url",
                "image_url": {
                    "url": "data:image/png;base64," + request.media[0],
                    "detail": "low",
                },
            },
            {"type": "text", "text": request.content},
        ]
        return PromptRenderResult(
            messages=[
                {
                    "role": "system",
                    "content": "constraint; members="
                    + ",".join(source.sender_id for source in request.window_sources)
                    + request.turn_injection_prompt,
                },
                *request.history,
                {"role": "user", "content": current},
            ]
        )

    provider._create_with_retry = create
    reasoner = DefaultReasoner(
        llm=LLMServices(provider, provider),
        llm_config=LLMConfig(model="controlled", max_tokens=200),
        tools=registry,
        discovery=ToolDiscoveryState(),
        tool_search_enabled=True,
        memory_window=40,
        context=AsyncMock(),
        session_manager=h.manager,
        compaction_memory=h.maintenance,
    )
    reasoner.render_prompt = render
    try:
        result = await reasoner.run_turn(msg=msg, session=session, context_view=view)
        assert result.reply == "continued from working state"
        assert len(sent) == 2 and summary_calls == 1
        # Initial, one retention estimate, the compacted request, the safety retry.
        assert [len(request.history) for request in renders] == [4, 0, 0, 0]
        assert renders[-1].window_sources == ()
        assert sent[0]["messages"][-1] == sent[1]["messages"][-1]
        for request in sent:
            text = json.dumps(request, ensure_ascii=False)
            assert "[working_state]" in text and "continue the task" in text
            assert "original.png" in text
            assert (
                "future message" not in text
                and "mutated input" not in text
                and "changed.png" not in text
            )
            assert "x" * 1000 not in text
            assert request.get("tools", []) == []
        outcomes = result.context_retry["compaction"]
        assert isinstance(outcomes, list) and len(outcomes) == 1
        assert (
            outcomes[0]["committed"] and outcomes[0]["configured_retained_turns"] == 2
        )
        assert history_start(session, view) == 2
        reloaded = SessionManager(h.manager.workspace).get_or_create(key)
        assert [message["id"] for message in reloaded.messages[:2]] == initial_ids
        assert len(reloaded.messages) == 4
        assert reloaded.maintenance_progress.summaries[window_key(view)]
        assert reloaded.messages[2]["content"] == "future message must stay out"
    finally:
        await provider.aclose()
