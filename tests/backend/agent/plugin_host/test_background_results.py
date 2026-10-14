"""The return path preserves original role/thread and rechecks user authority."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from agent.plugin_host.background_results import HostBackgroundResults
from agent.tools.turn_scope import tool_turn
from agent.tools.turn_origin import set_tool_origin
from shiori_sdk.messages import InboundMessage
from shiori_sdk.tools import Tool
from conversation.listening import GroupListeningControl
from conversation.service import (
    ConversationService,
    LegacySessionDescriptor,
    desktop_thread_id,
)
from tests.support.external_turns import ExternalTurnHost, USER_DM
from desktop_bridge.service import DesktopBridgeService


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
async def capture(host, channel="desktop", chat_id="role:mira", sender="user"):
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
                "message_thread_id": 27,
            },
        )
    )
    return HostBackgroundResults(
        host.loop.tools,
        host.roles,
        ConversationService(host.manager),
        host.loop.process_background_result,
    ).capture()


async def test_report_uses_original_role_thread_and_deduplicates(host):
    target = await capture(host)
    assert await target.report(
        "task:run", "改动验证完成，Draft PR: https://example.test/1"
    )
    assert not await target.report("task:run", "重复")
    assert len(host.provider.requests) == 1
    sent = host.loop.bus.publish_outbound.call_args.args[0]
    assert (sent.channel, sent.chat_id) == ("desktop", "role:mira")
    assert sent.metadata["role_id"] == "mira"
    assert sent.metadata["thread_id"] == desktop_thread_id("mira")
    assert host.stored(desktop_thread_id("mira"))[-1] == ("assistant", "reply-1")
    assert not any(
        "[后台任务结果]" in content
        for role, content in host.stored(desktop_thread_id("mira"))
    )


@pytest.mark.parametrize(
    "channel, chat_id, sender, thread_id",
    [
        ("desktop", "role:mira", "user", desktop_thread_id("mira")),
        ("qq", "902", "902", USER_DM),
    ],
)
async def test_report_publishes_committed_result_to_its_desktop_or_phone_thread(
    host, bridge, channel, chat_id, sender, thread_id
):
    emitted = []
    bridge.add_event_listener(emitted.append)
    target = await capture(host, channel, chat_id, sender)
    before = host.stored(thread_id)

    assert await target.report("task:run", "改动已验证")
    assert not await target.report("task:run", "不要重复发送")

    assert host.stored(thread_id) == [*before, ("assistant", "reply-1")]
    updates = [event for event in emitted if event["method"] == "session.updated"]
    assert len(updates) == 1
    update = updates[0]
    assert update["id"] == "task:run"
    assert update["payload"]["session_key"] == "role:mira"
    phone = [
        event for event in emitted if event["method"] == "phone.conversation.updated"
    ]
    if channel == "desktop":
        assert phone == []
        [message] = update["payload"]["messages"]
        assert message["content"] == "reply-1"
        stored = next(
            row
            for row in host.manager.get_or_create("role:mira").messages
            if row["id"] == message["id"]
        )
        assert stored["thread_id"] == thread_id
    else:
        assert update["payload"]["messages"] == []
        assert len(phone) == 1
        assert phone[0]["payload"]["thread_id"] == thread_id
        [message] = phone[0]["payload"]["messages"]
        assert message["content"] == "reply-1"


async def test_ordinary_desktop_turn_is_published_once_by_chat_service(host, bridge):
    emitted = []
    bridge.add_event_listener(emitted.append)
    response = await bridge.handle(
        {
            "id": "chat-1",
            "method": "chat.send",
            "payload": {"role_id": "mira", "content": "继续聊"},
        },
        emit_event=emitted.append,
    )
    assert response.error is None
    assert response.payload["message"]["content"] == "继续聊"
    async with asyncio.timeout(5):
        await bridge.chat_service._tasks_by_session["role:mira"].task

    updates = [event for event in emitted if event["method"] == "session.updated"]
    assert [
        (event["payload"]["message"]["role"], event["payload"]["message"]["content"])
        for event in updates
    ] == [("assistant", "reply-1")]


async def test_report_waits_for_role_then_uses_original_transport(host):
    target = await capture(host, "qq", "902", "902")
    gate = asyncio.Event()
    host.provider.gates.append(gate)
    foreground = host.desktop_turn("继续聊")
    await host.provider.started.wait()
    report = asyncio.create_task(target.report("result-1", "已完成"))
    await asyncio.sleep(0)
    assert not report.done()
    gate.set()
    await foreground
    assert await report
    sent = host.loop.bus.publish_outbound.call_args.args[0]
    assert (sent.channel, sent.chat_id) == ("qq", "902")
    assert sent.metadata["thread_id"] == USER_DM
    assert sent.metadata["message_thread_id"] == 27
    assert host.stored(USER_DM)[-1] == ("assistant", "reply-2")


async def test_unbound_while_waiting_is_rejected_inside_role_gate(host):
    target = await capture(host, "qq", "902", "902")
    gate = asyncio.Event()
    host.provider.gates.append(gate)
    foreground = host.desktop_turn("继续聊")
    await host.provider.started.wait()
    report = asyncio.create_task(target.report("result-1", "已完成"))
    await asyncio.sleep(0)
    for identity in host.roles.identities.list():
        host.roles.identities.unbind(identity.id)
    gate.set()
    await foreground
    with pytest.raises(PermissionError, match="绑定"):
        await report
    assert len(host.provider.requests) == 1
    assert not await target.report("result-1", "不应重发")


async def test_capture_requires_live_turn_and_trusted_sender(host):
    results = HostBackgroundResults(
        host.loop.tools,
        host.roles,
        ConversationService(host.manager),
        host.loop.process_background_result,
    )
    with pytest.raises(RuntimeError, match="工具回合"):
        results.capture()

    @tool_turn
    async def unauthenticated():
        host.loop.tools.set_context(sender_is_user="false")
        with pytest.raises(PermissionError, match="用户本人"):
            results.capture()

    await unauthenticated()


async def test_result_model_turn_cannot_capture_a_new_authorized_task(host):
    target = await capture(host)
    results = HostBackgroundResults(
        host.loop.tools,
        host.roles,
        ConversationService(host.manager),
        host.loop.process_background_result,
    )
    calls = []

    class CaptureTool(Tool):
        name = "public"
        description = "Try to create more work"
        parameters = {"type": "object", "properties": {}}

        async def execute(self, **kwargs):
            calls.append("capture")
            with pytest.raises(PermissionError, match="结果汇报"):
                results.capture()
            return "拒绝从结果回合派活"

    host.loop.tools.register(CaptureTool(), always_on=True)
    host.provider.tool_steps = 1
    assert await target.report("run-1", "任务结果")
    assert calls == ["capture"]
