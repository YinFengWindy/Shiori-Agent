"""The return path preserves original role/thread and rechecks user authority."""

from tests.support.chat_replies import chat_reply

import asyncio
from unittest.mock import AsyncMock

import pytest

from conversation.background_results import HostBackgroundResults
from agent.tools.turn_scope import tool_turn
from agent.tools.turn_origin import set_tool_origin
from shiori_sdk.messages import InboundMessage
from conversation.listening import GroupListeningControl
from conversation.service import (
    ConversationService,
    LegacySessionDescriptor,
    desktop_thread_id,
)
from tests.support.host_external_turns import ExternalTurnHost, USER_DM
from desktop_bridge.service import DesktopBridgeService
from core.channels.hub import ChannelHub
from shiori_sdk.accounts import AccountResponseRules
from shiori_sdk.accounts.routing import AccountRoute


@pytest.fixture
def host(tmp_path):
    fixture = ExternalTurnHost(tmp_path)
    fixture.roles.accounts.register(
        plugin_id="qq",
        platform="qq",
        platform_account_id="101",
        config_ref="101",
        token="fixture",
        role_id="mira",
    )
    conversations = ConversationService(fixture.manager)
    conversations.ensure_desktop_thread("mira")
    conversations.ensure_thread_for_session(
        LegacySessionDescriptor(
            session_key="qq:902",
            role_id="mira",
            channel="qq",
            chat_id="902",
        )
    )
    fixture.loop.bus.publish_outbound = AsyncMock()
    return fixture


@pytest.fixture
async def bridge(host, tmp_path):
    service = DesktopBridgeService(
        workspace=tmp_path,
        role_store=host.roles,
        session_manager=host.manager,
        agent_loop=host.loop,
        event_bus=host.loop._event_bus,
        group_environment=host.group_environment,
        group_listening=GroupListeningControl(
            ConversationService(host.manager), lambda _channel: False
        ),
    )
    yield service
    await service.aclose()


@tool_turn
async def capture(
    host, channel="desktop", chat_id="role:mira", sender="user", account_id=None
):
    host.loop.tools.set_context(
        role_id="mira",
        thread_id=desktop_thread_id("mira") if channel == "desktop" else USER_DM,
        transport_channel=channel,
        transport_chat_id=chat_id,
        sender_id=sender,
        sender_is_user="true",
        chat_type="private",
    )
    set_tool_origin(
        InboundMessage(
            channel=channel,
            chat_id=chat_id,
            sender=sender,
            content="原用户需求",
            metadata={
                "role_id": "mira",
                "thread_id": (
                    desktop_thread_id("mira") if channel == "desktop" else USER_DM
                ),
                "chat_type": "private",
                "message_thread_id": 27 if channel != "desktop" else None,
                **({"account_id": account_id} if account_id else {}),
            },
        )
    )
    return HostBackgroundResults(
        host.loop.tools,
        host.roles,
        ConversationService(host.manager),
        host.loop.process_background_result,
    ).capture()


@pytest.mark.parametrize("stage", ["generation", "pacing"])
async def test_natural_background_report_yields_to_desktop_input_without_losing_result(
    host, bridge, tmp_path, monkeypatch, stage
):
    from bootstrap.runtime.generations import RuntimeCandidate
    from bus.queue import MessageBus
    from core.common.runtime_scope import bind_runtime
    from agent.provider import LLMResponse
    from session.manager import SessionManager
    from session.manager.models import whole_session
    from types import SimpleNamespace

    entered, release = asyncio.Event(), asyncio.Event()
    requests = []

    async def model(**kwargs):
        if kwargs.get("response_format"):
            return LLMResponse(content='{"mood":"平静","thought":"我想说明结果。"}')
        index = len(requests)
        requests.append(kwargs)
        if index == 0 and stage == "generation":
            entered.set()
            await release.wait()
        return chat_reply(
            ["结果前缀", "未送达尾段"] if index == 0 else ["补充后的回复"],
            tools=kwargs.get("tools", []),
        )

    async def pause(_):
        entered.set()
        await release.wait()

    monkeypatch.setattr(host.provider, "chat", model)
    monkeypatch.setattr("agent.turns.reply_sequence.wait_between_messages", pause)
    candidate = RuntimeCandidate(1, SimpleNamespace(loop=host.loop), SimpleNamespace())
    target = await capture(host)
    # The capability is read when the result is ready, not frozen at capture.
    host.roles.update_role("mira", runtime_config={"natural_chat_enabled": True})
    emitted = []
    bridge.add_event_listener(emitted.append)

    async def report():
        async with candidate.acquire() as lease:
            with bind_runtime(lease), candidate.reply_sequences.bind(MessageBus()):
                return await target.report(
                    "background:finished", "原始完成事实：产物已验证"
                )

    reporting = asyncio.create_task(report())
    await asyncio.wait_for(entered.wait(), 3)
    async with candidate.acquire() as lease:
        with bind_runtime(lease):
            for turn in ("new-1", "new-2"):
                response = await bridge.handle(
                    {
                        "id": turn,
                        "method": "chat.send",
                        "payload": {"role_id": "mira", "content": turn},
                    },
                    emit_event=emitted.append,
                )
                assert response.error is None
    release.set()
    assert await asyncio.wait_for(reporting, 3)
    await asyncio.wait_for(bridge.chat_service._tasks_by_session["role:mira"].task, 3)
    rows = SessionManager(tmp_path).get_or_create("role:mira").messages
    assert not any("未送达尾段" in m["content"] for m in rows)
    assert [m["content"] for m in rows if m["content"] in {"new-1", "new-2"}] == [
        "new-1",
        "new-2",
    ]
    history = (
        SessionManager(tmp_path)
        .get_or_create("role:mira")
        .get_history(include=whole_session)
    )
    assert sum(m.get("content") == "原始完成事实：产物已验证" for m in history) == 1
    assert any(
        event["method"] == "chat.done" and event["payload"]["turn_id"] == "new-2"
        for event in emitted
    )
    if stage == "pacing":
        prefix = next(m for m in rows if m["content"] == "结果前缀")
        assert any(
            event["method"] == "session.updated"
            and event["payload"].get("message", {}).get("id") == prefix["id"]
            for event in emitted
        )
    async with asyncio.timeout(3):
        while candidate.references:
            await asyncio.sleep(0)


@pytest.mark.parametrize("ordinary_turns", [False, True])
async def test_natural_report_batch_reloads_and_does_not_change_eligible_undo_turn(
    host, tmp_path, monkeypatch, ordinary_turns
):
    from agent.provider import LLMResponse
    from agent.turns.channel_sequence import ChannelSequenceOwner
    from bus.queue import MessageBus
    from session.manager import SessionManager

    session = host.manager.get_or_create("role:mira")
    old_last_turn = [str(m["id"]) for m in session.messages[-2:]]
    if not ordinary_turns:
        session.clear()
        host.manager.save(session)
    target = await capture(host)
    host.roles.update_role("mira", runtime_config={"natural_chat_enabled": True})

    async def model(**kwargs):
        if kwargs.get("response_format"):
            return LLMResponse(content='{"mood":"平静","thought":"我想说明结果。"}')
        return chat_reply(["报告第一条", "报告第二条"], tools=kwargs.get("tools", []))

    monkeypatch.setattr(host.provider, "chat", model)
    monkeypatch.setattr("agent.turns.reply_sequence.wait_between_messages", AsyncMock())
    with ChannelSequenceOwner().bind(MessageBus()):
        assert await target.report("report:stable", "真实完成的后台事实")
    reloaded = SessionManager(tmp_path).get_or_create("role:mira")
    report_rows = [
        m
        for m in reloaded.messages
        if m.get("metadata", {}).get("source") == "background_result"
    ]
    assert len(report_rows) == 3
    assert [
        m["metadata"]["reply_sequence_id"] for m in report_rows if m["content"]
    ] == ["report:stable", "report:stable"]
    before_ids = {str(m["id"]) for m in report_rows}
    result = await host.manager.undo_last_turn("role:mira")
    if ordinary_turns:
        assert result is not None
        assert result.deleted_ids == old_last_turn
    else:
        assert result is None
    after = SessionManager(tmp_path).get_or_create("role:mira")
    assert before_ids.issubset({str(m["id"]) for m in after.messages})
    assert [m for m in after.messages if str(m["id"]) in before_ids] == report_rows


async def test_background_report_reads_disabled_role_without_sequence_protocol(
    host, monkeypatch
):
    from agent.provider import LLMResponse
    from agent.turns.channel_sequence import ChannelSequenceOwner
    from bus.queue import MessageBus
    from prompts.natural_chat import NATURAL_CHAT_PROMPT

    host.roles.update_role("mira", runtime_config={"natural_chat_enabled": True})
    target = await capture(host)
    host.roles.update_role("mira", runtime_config={"natural_chat_enabled": False})
    requests = []

    async def model(**kwargs):
        requests.append(kwargs)
        return LLMResponse(
            content=(
                '{"content":"普通报告", "mood":"平静", "thought":"我想说明结果。"}'
                if kwargs.get("response_format")
                else "普通报告"
            )
        )

    monkeypatch.setattr(host.provider, "chat", model)
    with ChannelSequenceOwner().bind(MessageBus()):
        assert await target.report("report:off", "已完成")
    rows = [
        m
        for m in host.manager.get_or_create("role:mira").messages
        if m.get("metadata", {}).get("source") == "background_result"
    ]
    assert [m["content"] for m in rows] == ["普通报告"]
    assert all("reply_sequence_id" not in m.get("metadata", {}) for m in rows)
    assert not any(NATURAL_CHAT_PROMPT in str(request) for request in requests)


@tool_turn
async def capture_bot(host):
    accounts = host.roles.accounts
    row = accounts.register(
        plugin_id="grok_bot",
        platform="grok_bot",
        platform_account_id="one",
        config_ref="one",
        token="bot-live",
        role_id="mira",
        response_rules=AccountResponseRules(allow_full_tools=True),
    )
    accounts.set_rules_handler("grok_bot", lambda *_: None)
    accounts.report(
        row.record.id,
        "bot-live",
        connection="online",
        capabilities=frozenset({"full_tools"}),
        tool_conversation=AccountRoute("grok_bot_one", "dm:peer"),
    )
    host.loop.tools.bind_accounts(accounts)
    hub = ChannelHub.from_workspace(
        host.roles.workspace, session_manager=host.manager, role_store=host.roles
    )
    origin = hub.route_account_inbound(
        InboundMessage(
            channel="grok_bot_one",
            sender="peer",
            chat_id="dm:peer",
            content="后台处理",
            metadata={"account_id": row.record.id, "chat_type": "private"},
        )
    )
    assert origin is not None
    host.loop.tools.set_context(
        role_id="mira",
        thread_id=origin.metadata["thread_id"],
        sender_id="peer",
        sender_is_user="false",
        account_full_tools="true",
    )
    set_tool_origin(origin)
    target = HostBackgroundResults(
        host.loop.tools,
        host.roles,
        ConversationService(host.manager),
        host.loop.process_background_result,
    ).capture()
    return target, row.record.id


async def test_natural_background_completion_keeps_shared_correction_raw_thinking_and_usage(
    host, monkeypatch
):
    from agent.provider import LLMResponse, ToolCall
    from shiori_sdk.memory.committed import TurnCommitted
    from agent.turns.channel_sequence import ChannelSequenceOwner
    from bus.queue import MessageBus
    from session.manager.models import whole_session

    target = await capture(host)
    host.roles.update_role("mira", runtime_config={"natural_chat_enabled": True})
    requests, observed = [], []
    raw = '{ "messages" : ["检查完成。", "原始结果已经保存。"] }'
    tool = host.loop.tools.get_tool("public")
    execute = AsyncMock(return_value="已经完成的检查事实")
    monkeypatch.setattr(tool, "execute", execute)

    async def chat(**kwargs):
        if kwargs.get("response_format"):
            return LLMResponse('{"mood":"平静","thought":"我想说明结果。"}')
        requests.append(kwargs)
        if len(requests) == 1:
            return LLMResponse("", [ToolCall("work", "public", {})], total_tokens=3)
        if len(requests) == 2:
            return LLMResponse(
                "",
                [ToolCall("draft", "finish_reply", {"messages": []})],
                thinking="完成报告的正常思考",
                total_tokens=5,
            )
        assert len(requests) == 3
        assert [tool["function"]["name"] for tool in kwargs["tools"]] == [
            "finish_reply"
        ]
        return LLMResponse(
            "",
            [
                ToolCall(
                    "fixed",
                    "finish_reply",
                    {"messages": ["检查完成。", "原始结果已经保存。"]},
                    raw,
                )
            ],
            total_tokens=7,
        )

    monkeypatch.setattr(host.provider, "chat", chat)
    monkeypatch.setattr("agent.turns.reply_sequence.wait_between_messages", AsyncMock())
    host.loop._event_bus.on(TurnCommitted, observed.append)
    with ChannelSequenceOwner().bind(MessageBus()):
        assert await target.report(
            "background:shared-protocol", "后台工作只执行一次的原始产物"
        )
    execute.assert_awaited_once()
    assert len(requests) == 3
    assert requests[2]["call_purpose"] == "auxiliary"
    assert any(
        "已经完成的检查事实" in str(message) for message in requests[2]["messages"]
    )
    [committed] = observed
    assert committed.raw_reply == raw
    assert committed.thinking == "完成报告的正常思考"
    assert committed.total_tokens == 15
    history = host.manager.get_or_create("role:mira").get_history(include=whole_session)
    assert sum(m.get("content") == "后台工作只执行一次的原始产物" for m in history) == 1
    assert any(m.get("content") == "已经完成的检查事实" for m in history)
    assert [
        m["content"]
        for m in host.manager.get_or_create("role:mira").messages
        if m.get("metadata", {}).get("reply_sequence_id")
        == "background:shared-protocol"
    ] == ["检查完成。", "原始结果已经保存。"]


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("reconnect", [False, True])
@pytest.mark.parametrize("stage", ["generation", "outbound", "post_commit"])
async def test_sdk_report_connection_fence_survives_generation_and_queued_delivery(
    host, monkeypatch, enabled, stage, reconnect
):
    from agent.provider import LLMResponse
    from agent.turns.channel_sequence import ChannelSequenceOwner
    from agent.turns.channel_sequence_commit import ChannelSequenceDeliveryError
    from bus.queue import MessageBus
    from shiori_sdk.messages import DeliveryOutcome

    accounts = host.roles.accounts
    accounts.report("qq:101", "fixture", connection="online")
    host.roles.update_role("mira", runtime_config={"natural_chat_enabled": enabled})
    target = await capture(host, "qq", "902", "902", account_id="qq:101")
    bus = MessageBus()
    host.loop.bus = bus
    host.loop._agent_core.pipeline._outbound_port._bus = bus
    entered, release = asyncio.Event(), asyncio.Event()
    delivered = []

    async def send(message):
        delivered.append(message.content)
        message.delivery_outcome = DeliveryOutcome("sent", "native:one")

    bus.subscribe_outbound("qq", send, supports_reply_sequence=True)

    async def chat(**kwargs):
        if kwargs.get("response_format"):
            return LLMResponse('{"mood":"平静","thought":"我想说明结果。"}')
        if stage == "generation":
            entered.set()
            await release.wait()
        return chat_reply(["private SDK report"], tools=kwargs.get("tools", []))

    monkeypatch.setattr(host.provider, "chat", chat)
    if stage == "post_commit":
        append = host.manager.append_messages

        async def append_and_pause(session, messages, **kwargs):
            result = await append(session, messages, **kwargs)
            if any(
                message.get("content") == "private SDK report" for message in messages
            ):
                # History is durable here; the reply is not queued yet. The
                # captured connection fence is attached when it is published.
                assert bus.outbound_size == 0
                entered.set()
                await release.wait()
            return result

        monkeypatch.setattr(host.manager, "append_messages", append_and_pause)
    if stage == "outbound":
        await bus.transport_lock.acquire()
    dispatcher = asyncio.create_task(bus.dispatch_outbound())
    try:
        with ChannelSequenceOwner().bind(bus):
            reporting = asyncio.create_task(
                target.report("sdk:revoked", "private completed fact")
            )
            if stage in {"generation", "post_commit"}:
                await asyncio.wait_for(entered.wait(), 3)
            else:
                async with asyncio.timeout(3):
                    while not bus.outbound_size:
                        await asyncio.sleep(0)
            if reconnect:
                accounts.release("qq:101", "fixture")
                new = accounts.register(
                    plugin_id="qq",
                    platform="qq",
                    platform_account_id="101",
                    config_ref="101",
                    role_id="mira",
                    token="replacement",
                )
                accounts.report(new.record.id, "replacement", connection="online")
            release.set()
            if stage == "outbound":
                bus.transport_lock.release()
            [result] = await asyncio.gather(reporting, return_exceptions=True)
            if enabled and reconnect:
                assert isinstance(result, ChannelSequenceDeliveryError)
            else:
                assert result is True
            await asyncio.wait_for(bus.drain_outbound(), 3)
        assert delivered == ([] if reconnect else ["private SDK report"])
        assert not bus._pending_outbound
        assert not bus._outbound_checks
        assert not bus._acknowledgements
        assert not bus._ack_started
    finally:
        release.set()
        if stage == "outbound" and bus.transport_lock.locked():
            bus.transport_lock.release()
        dispatcher.cancel()
        await asyncio.gather(dispatcher, return_exceptions=True)
