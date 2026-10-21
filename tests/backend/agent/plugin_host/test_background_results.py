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
from core.channels.hub import ChannelHub
from shiori_sdk.accounts import AccountResponseRules
from shiori_sdk.accounts.conversation import AccountConversation
from tests.support.external_turns import SECRETS, request_text


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
        tool_conversation=AccountConversation("grok_bot_one", "dm:peer"),
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


async def test_authorized_bot_background_result_keeps_external_identity_and_history(
    host,
):
    target, _ = await capture_bot(host)
    assert await target.report("bot-result", "完成了")
    sent = host.loop.bus.publish_outbound.call_args.args[0]
    assert (sent.channel, sent.chat_id) == ("grok_bot_one", "dm:peer")
    assert not sent.metadata.get("sender_is_user")
    assert all(
        secret not in request_text(host.provider.requests[-1]) for secret in SECRETS
    )


@pytest.mark.parametrize("revoke", ["permission", "disconnect", "reload"])
async def test_bot_result_rechecks_current_permission_connection_and_generation(
    host, revoke
):
    target, account_id = await capture_bot(host)
    if revoke == "permission":
        host.roles.accounts.set_response_rules(account_id, AccountResponseRules())
    elif revoke == "disconnect":
        host.roles.accounts.report(
            account_id,
            "bot-live",
            connection="offline",
            capabilities=frozenset({"full_tools"}),
        )
    else:
        host.roles.accounts.release(account_id, "bot-live")
        host.roles.accounts.register(
            plugin_id="grok_bot",
            platform="grok_bot",
            platform_account_id="one",
            config_ref="one",
            token="new-generation",
            role_id="mira",
            response_rules=AccountResponseRules(allow_full_tools=True),
        )
        host.roles.accounts.report(
            account_id,
            "new-generation",
            connection="online",
            capabilities=frozenset({"full_tools"}),
            tool_conversation=AccountConversation("grok_bot_one", "dm:peer"),
        )
    with pytest.raises(PermissionError, match="连接或工具授权"):
        await target.report("late-result", "不能发")
    assert host.provider.requests == []


async def test_bot_revocation_while_waiting_is_checked_inside_the_role_gate(host):
    target, account_id = await capture_bot(host)
    gate = asyncio.Event()
    host.provider.gates.append(gate)
    foreground = host.desktop_turn("继续聊")
    await host.provider.started.wait()
    report = asyncio.create_task(target.report("late-result", "完成"))
    await asyncio.sleep(0)
    host.roles.accounts.set_response_rules(account_id, AccountResponseRules())
    gate.set()
    await foreground
    with pytest.raises(PermissionError, match="连接或工具授权"):
        await report
    assert len(host.provider.requests) == 1


async def test_old_bot_background_result_stays_revoked_after_new_bot_is_granted(host):
    target, account_id = await capture_bot(host)
    accounts = host.roles.accounts
    accounts.set_response_rules(account_id, AccountResponseRules())
    accounts.report(
        account_id,
        "bot-live",
        connection="online",
        capabilities=frozenset({"full_tools"}),
        tool_conversation=AccountConversation("grok_bot_one", "dm:replacement"),
    )
    accounts.set_response_rules(account_id, AccountResponseRules(allow_full_tools=True))
    assert target.account_access is not None and accounts.validate_access(
        target.account_access
    )
    with pytest.raises(PermissionError, match="连接或工具授权"):
        await target.report("old-bot-result", "不能恢复旧Bot的权限")
    assert host.provider.requests == []
