"""Passive turns own same-role desktop pushes until their ordered SQL commit."""

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from agent.core.passive_turn.pipeline import AgentCoreDeps, PassiveTurnPipeline
from agent.core.runtime_support import TurnRunResult
from agent.core.types import ContextBundle
from agent.tool_hooks import ToolExecutionRequest
from agent.tool_hooks.executor import ToolExecutor
from agent.tools.message_push import MessagePushTool
from agent.tools.registry import ToolRegistry
from bus.event_bus import EventBus
from bus.events import InboundMessage
from core.roles import RoleStore
from core.roles.reply_state import RoleReply
from desktop_bridge.service import DesktopBridgeService
from session.manager import SessionManager


@pytest.fixture
async def runtime(tmp_path):
    roles = RoleStore(tmp_path)
    roles.create_role(role_id="mira", name="Mira", system_prompt="test")
    manager = SessionManager(tmp_path)
    bus = EventBus()
    push = MessagePushTool()
    bridge = DesktopBridgeService(
        workspace=tmp_path,
        role_store=roles,
        session_manager=manager,
        agent_loop=SimpleNamespace(),
        event_bus=bus,
        push_tool=push,
    )
    session = (await bridge.app_service.open_role_session("mira")).session
    tools = ToolRegistry()
    tools.register(push)
    emitted = []
    bridge.add_event_listener(emitted.append)

    async def call(**payload):
        result = await ToolExecutor().execute(
            ToolExecutionRequest(
                call_id="push",
                tool_name="message_push",
                source="passive",
                arguments={"channel": "desktop", "chat_id": "role:mira", **payload},
                session_key=session.key,
            ),
            tools.execute,
        )
        return str(result.output)

    def pipeline(reasoning):
        return PassiveTurnPipeline(
            AgentCoreDeps(
                session=SimpleNamespace(session_manager=manager, presence=None),
                context_store=SimpleNamespace(
                    prepare=AsyncMock(return_value=ContextBundle())
                ),
                context=SimpleNamespace(
                    render=Mock(
                        return_value=SimpleNamespace(system_prompt="", messages=[])
                    )
                ),
                tools=tools,
                reasoner=SimpleNamespace(run_turn=reasoning),
                event_bus=bus,
            )
        )

    yield SimpleNamespace(
        manager=manager,
        bridge=bridge,
        session=session,
        emitted=emitted,
        call=call,
        pipeline=pipeline,
        push=push,
    )
    await bridge.aclose()


def incoming():
    return InboundMessage(
        channel="qqbot",
        chat_id="friend",
        sender="user",
        content="send to desktop",
        timestamp=datetime(2026, 9, 26, 0, 21, 44, tzinfo=timezone.utc),
        metadata={"role_id": "mira"},
    )


def reply(formal=True):
    return TurnRunResult(
        reply="done",
        tools_used=["message_push"],
        context_retry={"formal_role_reply": formal},
        role_reply=RoleReply(content="done", mood="平静", thought="完成了"),
    )


@pytest.mark.parametrize("formal", [True, False])
async def test_pipeline_commits_ordered_pushes_and_emits_complete_turn(
    runtime, tmp_path, formal
):
    observed = {}

    async def reasoning(**_kwargs):
        # The actual executor/registry path must keep the passive turn identity.
        observed["first"] = await runtime.call(message="first", image="first.png")
        observed["second"] = await runtime.call(message="second")
        observed["messages"] = list(runtime.session.messages)
        observed["persisted"] = runtime.manager._store.fetch_session_messages(
            runtime.session.key
        )
        observed["events"] = list(runtime.emitted)
        return reply(formal)

    msg = incoming()
    result = await runtime.pipeline(reasoning).run(
        msg, runtime.session.key, dispatch_outbound=False
    )
    expected = ["send to desktop", "first", "", "second", "done"]
    reloaded = SessionManager(tmp_path).get_or_create(runtime.session.key)
    assert [row["content"] for row in reloaded.messages] == expected
    assert observed == {
        "first": "文本已排队，回合成功后发送；图片已排队，回合成功后发送",
        "second": "文本已排队，回合成功后发送",
        "messages": [],
        "persisted": [],
        "events": [],
    }
    assert len({row["id"] for row in reloaded.messages}) == 5
    assert datetime.fromisoformat(reloaded.messages[0]["timestamp"]) == msg.timestamp
    assert reloaded.messages[2]["media"] == ["first.png"]
    assert result.committed_message_id == reloaded.messages[-1]["id"]
    assert len(runtime.emitted) == 1
    assert [
        row["content"] for row in runtime.emitted[0]["payload"]["messages"]
    ] == expected
    # Older pages retain the same authoritative sequence after reopening.
    newest = runtime.manager._store.fetch_messages_page(runtime.session.key, limit=2)
    older = runtime.manager._store.fetch_messages_page(
        runtime.session.key, limit=3, before_seq=newest["next_before_seq"]
    )
    assert [
        row["content"] for row in older["messages"] + newest["messages"]
    ] == expected


@pytest.mark.parametrize("failure_stage", ["reasoning", "append"])
@pytest.mark.parametrize("cancelled", [False, True])
async def test_pipeline_discards_push_drafts_on_failure_or_cancellation(
    runtime, monkeypatch, failure_stage, cancelled
):
    failure = asyncio.CancelledError() if cancelled else OSError("failed")

    async def reasoning(**_kwargs):
        assert "已排队" in await runtime.call(message="must not survive")
        if failure_stage == "reasoning":
            raise failure
        return reply()

    if failure_stage == "append":
        monkeypatch.setattr(
            runtime.manager, "append_messages", AsyncMock(side_effect=failure)
        )
    operation = runtime.pipeline(reasoning).run(
        incoming(), runtime.session.key, dispatch_outbound=False
    )
    if cancelled or failure_stage == "append":
        with pytest.raises(type(failure)):
            await operation
    else:
        assert (await operation).content == "处理消息时出错，请稍后再试。"
    assert runtime.session.messages == []
    assert runtime.manager._store.fetch_session_messages(runtime.session.key) == []
    assert runtime.emitted == []
    # A later independent push must not be captured by the abandoned turn.
    assert "已发送" in await runtime.call(message="later")
    assert [row["content"] for row in runtime.session.messages] == ["later"]


async def test_pipeline_keeps_background_other_role_and_external_sends_independent(
    runtime,
):
    external = AsyncMock()
    runtime.push.register_channel("external", text=external)

    async def reasoning(**_kwargs):
        assert "已发送" in await asyncio.create_task(runtime.call(message="background"))
        assert "已发送" in await runtime.call(chat_id="role:other", message="other")
        assert "已发送" in await runtime.call(
            channel="external", chat_id="friend", message="external"
        )
        assert "已排队" in await runtime.call(message="queued")
        assert [row["content"] for row in runtime.session.messages] == ["background"]
        raise RuntimeError("turn failed")

    await runtime.pipeline(reasoning).run(
        incoming(), runtime.session.key, dispatch_outbound=False
    )
    assert [row["content"] for row in runtime.session.messages] == ["background"]
    assert [
        row["content"] for row in runtime.manager.get_or_create("role:other").messages
    ] == ["other"]
    external.assert_awaited_once_with("friend", "external")


async def test_cancel_while_waiting_to_commit_cannot_leak_pushes_into_queued_save(
    runtime, monkeypatch
):
    append_entered = asyncio.Event()
    original_append = runtime.manager.append_messages

    async def append(*args, **kwargs):
        append_entered.set()
        return await original_append(*args, **kwargs)

    async def reasoning(**_kwargs):
        await runtime.call(message="private")
        return reply()

    monkeypatch.setattr(runtime.manager, "append_messages", append)
    async with runtime.manager._lock(runtime.session.key):
        task = asyncio.create_task(
            runtime.pipeline(reasoning).run(
                incoming(), runtime.session.key, dispatch_outbound=False
            )
        )
        await append_entered.wait()
        runtime.manager.save(runtime.session)
        assert runtime.manager._store.fetch_session_messages(runtime.session.key) == []
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert runtime.session.messages == []
    assert runtime.emitted == []
