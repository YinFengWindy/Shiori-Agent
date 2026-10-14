"""The return path preserves original role/thread and rechecks user authority."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from agent.plugin_host.background_results import HostBackgroundResults
from agent.tools.turn_scope import tool_turn
from agent.tools.turn_origin import set_tool_origin
from shiori_sdk.messages import InboundMessage
from shiori_sdk.tools import Tool
from conversation.service import (
    ConversationService,
    LegacySessionDescriptor,
    desktop_thread_id,
)
from tests.support.external_turns import ExternalTurnHost, USER_DM


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
