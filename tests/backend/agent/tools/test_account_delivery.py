"""Account model tools select a channel and never show the model account IDs."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agent.account_delivery import AccountDelivery, AccountSendReceipt
from agent.tools.account_delivery import (
    AccountListTool,
    AccountSendTool,
    AccountTargetsTool,
    record_delivered_push,
)
from agent.turns.turn_pushes import current_turn_pushes
from bus.event_bus import EventBus
from bus.events_lifecycle import ExternalTextPushed
from conversation.push_sync import ExternalPushSyncService
from conversation.service import ConversationService, LegacySessionDescriptor
from shiori_sdk.channels.threads import network_thread_id
from core.accounts import AccountRegistry
from core.accounts.delivery_ledger import AccountDeliveryLedger
from shiori_sdk.accounts.targets import AccountTarget
from shiori_sdk.accounts.routing import AccountRoute
from core.identity import IdentityChat, UserIdentityStore
from session.manager import SessionManager


@pytest.mark.asyncio
async def test_account_tools_pass_the_channel_and_hide_account_ids() -> None:
    delivery = SimpleNamespace(
        list_channels=lambda role_id: [{"channel": "qq", "online": True}],
        targets=AsyncMock(return_value={"scope": "known", "items": [{"id": "42"}]}),
        send=AsyncMock(
            return_value=AccountSendReceipt(
                attempt_id="attempt-1",
                account_id="qq:101",
                channel="qq",
                target_kind="group",
                target_id="42",
                platform_message_id="platform-9",
                ownership_current=True,
            )
        ),
    )
    listed = json.loads(await AccountListTool(delivery).execute(role_id="mira"))
    targets = json.loads(
        await AccountTargetsTool(delivery).execute(
            channel="qq", role_id="mira", kind="known"
        )
    )
    receipt = json.loads(
        await AccountSendTool(delivery, EventBus()).execute(
            channel="qq",
            role_id="mira",
            target_kind="group",
            target_id="42",
            message="hello",
            mention_ids=["902"],
        )
    )
    assert listed == [{"channel": "qq", "online": True}]
    assert targets["items"] == [{"id": "42"}]
    delivery.targets.assert_awaited_once_with("qq", "mira", "known", "", "")
    assert receipt["platform_message_id"] == "platform-9"
    assert receipt["channel"] == "qq"
    assert "qq:101" not in json.dumps(receipt)
    delivery.send.assert_awaited_once_with(
        "qq",
        "mira",
        AccountTarget("group", "42", mention_ids=("902",)),
        "hello",
        media=[],
    )
    for tool in (AccountTargetsTool, AccountSendTool):
        assert "account_id" not in tool.parameters["properties"]
        assert "channel" in tool.parameters["required"]


@pytest.mark.asyncio
async def test_account_send_passes_images_without_text() -> None:
    receipt = AccountSendReceipt(
        attempt_id="attempt-1",
        account_id="qq:101",
        channel="qq",
        target_kind="private",
        target_id="42",
        platform_message_id="platform-9",
        ownership_current=True,
    )
    delivery = SimpleNamespace(send=AsyncMock(return_value=receipt))
    await AccountSendTool(delivery, EventBus()).execute(
        channel="qq",
        role_id="mira",
        target_kind="private",
        target_id="42",
        media=["D:/media/scene.png", "https://example.test/a.png"],
    )
    delivery.send.assert_awaited_once_with(
        "qq",
        "mira",
        AccountTarget("private", "42"),
        "",
        media=["D:/media/scene.png", "https://example.test/a.png"],
    )
    with pytest.raises(ValueError, match="media"):
        await AccountSendTool(delivery, EventBus()).execute(
            channel="qq",
            role_id="mira",
            target_kind="private",
            target_id="42",
            media="D:/media/scene.png",
        )


_VIA = {
    "platform": "qq",
    "platform_account_id": "101",
    "display_name": "Mira",
    "prefix": "QQ「Mira」",
}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "channel,transport,target_id,chat_id,message_id",
    [
        ("grok_bot", "grok_bot_bridge", "peer-id", "dm:peer-id", ""),
        ("qq", "qq", "902", "902", "qq-1"),
        ("telegram", "telegram_first", "123", "123", "tg-1"),
        ("qqbot", "qqbot", "opaque", "c2c:100:opaque", "qqbot-1"),
        ("feishu", "feishu:feishu:app", "ou_a", "oc_a", "om-1"),
    ],
)
async def test_private_bot_first_contact_is_recorded_in_canonical_network_thread(
    tmp_path,
    channel,
    transport,
    target_id,
    chat_id,
    message_id,
):
    """A bot does not need to be paired as the desktop user to have a history."""
    accounts = AccountRegistry(lambda role_id: role_id == "mira")
    account = accounts.register(
        plugin_id=channel,
        platform=channel,
        platform_account_id="bridge",
        config_ref="bridge",
        token="live",
        role_id="mira",
    )
    accounts.report(account.record.id, "live", connection="online")

    async def send(payload):
        assert payload["target_id"] == target_id
        return {
            "message_id": message_id,
            "accepted": True,
            "conversation": AccountRoute(transport, chat_id).to_payload(),
        }

    ledger = AccountDeliveryLedger(tmp_path)
    delivery = AccountDelivery(
        accounts,
        SimpleNamespace(resolve=lambda name: (channel, send)),
        ledger,
        UserIdentityStore(tmp_path),
    )
    sessions = SessionManager(tmp_path)
    sessions.open_role_session("mira", role_name="Mira")
    bus = EventBus()
    _ = ExternalPushSyncService(
        live_turn_pushes=current_turn_pushes, session_manager=sessions, event_bus=bus
    )
    tool = AccountSendTool(delivery, bus)
    await tool.execute(
        channel=channel,
        role_id="mira",
        target_kind="private",
        target_id=target_id,
        message="我先来找你",
    )
    [stored] = sessions._store.fetch_session_messages("role:mira")
    assert stored["content"] == "我先来找你"
    assert stored["thread_id"] == network_thread_id("mira", transport, chat_id)
    assert (stored["metadata"].get("external_message_id") or "") == message_id
    [attempt] = ledger.list_for_role("mira")
    assert stored["metadata"]["delivery_attempt_id"] == attempt.attempt_id


def _user_send_setup(
    tmp_path, *, plugin_id="qq", user_id="3174898512", chat_channel="qq"
):
    """Mira's online account, the user bound to it with a private chat on
    transport ``chat_channel``, and a recording session."""
    accounts = AccountRegistry(lambda role_id: role_id == "mira")
    record = accounts.register(
        plugin_id=plugin_id,
        platform=plugin_id,
        platform_account_id="101",
        config_ref="101",
        token="live",
        role_id="mira",
    ).record
    accounts.report(record.id, "live", connection="online")
    identities = UserIdentityStore(tmp_path)
    identity = identities.pair(
        identities.create_pairing_code().code,
        record=record,
        user_id=user_id,
        scope="platform",
        chat=IdentityChat(record.id, chat_channel, user_id),
    )
    assert identity is not None
    sent: list[dict] = []

    async def send(payload: dict) -> dict:
        sent.append(payload)
        return {"message_id": "qq-9", "via_account": _VIA}

    ledger = AccountDeliveryLedger(tmp_path)
    delivery = AccountDelivery(
        accounts,
        SimpleNamespace(resolve=lambda name: (plugin_id, send)),
        ledger,
        identities,
    )
    session_manager = SessionManager(tmp_path)
    session_manager.open_role_session("mira", role_name="Mira")
    event_bus = EventBus()
    _ = ExternalPushSyncService(
        live_turn_pushes=current_turn_pushes,
        session_manager=session_manager,
        event_bus=event_bus,
    )
    return AccountSendTool(delivery, event_bus), sent, ledger, session_manager


@pytest.mark.asyncio
async def test_user_target_reaches_the_users_private_chat_and_is_recorded(
    tmp_path,
) -> None:
    tool, sent, ledger, session_manager = _user_send_setup(tmp_path)
    image = "https://example.test/a.png"

    receipt = json.loads(
        await tool.execute(
            channel="qq",
            role_id="mira",
            session_key="role:mira",
            target_kind="user",
            message="我在 QQ 上找你啦",
            media=[image],
        )
    )

    assert [(row["target_kind"], row["target_id"]) for row in sent] == [
        ("private", "3174898512")
    ]
    assert receipt["target_id"] == "3174898512"
    [attempt] = ledger.list_for_role("mira")
    assert (attempt.status, attempt.platform_message_id) == ("sent", "qq-9")
    # Stored in the role session under the QQ private chat's thread, so the
    # chat (and the phone) shows it, with the account delivery facts.
    [stored] = session_manager._store.fetch_session_messages("role:mira")
    assert stored["content"] == "我在 QQ 上找你啦"
    assert stored["media"] == [image]
    assert stored["thread_id"] == network_thread_id("mira", "qq", "3174898512")
    assert stored["tools_used"] == ["account_send"]
    assert stored["proactive"] is True
    metadata = stored["metadata"]
    assert (metadata["source"], metadata["sender_id"]) == (
        "account_send",
        "account_send",
    )
    assert metadata["chat_type"] == "private"
    assert metadata["delivery_attempt_id"] == attempt.attempt_id
    assert metadata["external_message_id"] == "qq-9"
    assert metadata["via_account"] == _VIA


@pytest.mark.asyncio
@pytest.mark.parametrize("transport", ["qq", "qq_bot_instance"])
async def test_supplement_uses_exact_bound_chat_and_is_not_proactive(
    tmp_path, transport
):
    tool, sent, ledger, sessions = _user_send_setup(tmp_path, chat_channel=transport)
    await tool.execute(
        channel=transport,
        role_id="mira",
        session_key="role:mira",
        target_kind="user",
        push_chat_id="3174898512",
        push_proactive=False,
        media=["https://example.test/cg.png"],
    )
    assert len(sent) == 1
    assert sent[0]["target_id"] == "3174898512"
    [message] = sessions._store.fetch_session_messages("role:mira")
    assert message.get("proactive", False) is False
    assert message["thread_id"] == network_thread_id("mira", transport, "3174898512")
    assert message["media"] == ["https://example.test/cg.png"]
    [attempt] = ledger.list_for_role("mira")
    assert attempt.status == "sent"


@pytest.mark.asyncio
async def test_supplement_never_retargets_an_unbound_original_chat(tmp_path):
    tool, sent, ledger, sessions = _user_send_setup(tmp_path)
    with pytest.raises(LookupError, match="绑定用户的私聊"):
        await tool.execute(
            channel="qq",
            role_id="mira",
            target_kind="user",
            push_chat_id="old-peer",
            push_proactive=False,
            media=["https://example.test/cg.png"],
        )
    assert sent == []
    assert ledger.list_for_role("mira") == []
    assert sessions._store.fetch_session_messages("role:mira") == []


@pytest.mark.asyncio
async def test_model_cannot_forge_supplement_flags_or_original_chat(tmp_path):
    from agent.tools.registry import ToolRegistry

    tool, sent, _, sessions = _user_send_setup(tmp_path)
    registry = ToolRegistry()
    registry.register(tool)
    await registry.execute(
        "account_send",
        {
            "channel": "qq",
            "target_kind": "user",
            "message": "hi",
            "push_chat_id": "forged",
            "push_proactive": False,
        },
        context={"role_id": "mira", "session_key": "role:mira"},
    )
    assert len(sent) == 1
    [message] = sessions._store.fetch_session_messages("role:mira")
    assert message["proactive"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "flags",
    [
        {"push_proactive": "false", "push_chat_id": "3174898512"},
        {"push_proactive": False},
        {
            "push_proactive": False,
            "push_chat_id": "3174898512",
            "target_kind": "private",
        },
        {"push_chat_id": "3174898512"},
    ],
)
async def test_invalid_host_supplement_arguments_are_rejected_before_sending(
    tmp_path, flags
):
    tool, sent, _, _ = _user_send_setup(tmp_path)
    arguments = {
        "channel": "qq",
        "role_id": "mira",
        "target_kind": "user",
        "message": "hi",
        **flags,
    }
    with pytest.raises(ValueError):
        await tool.execute(**arguments)
    assert sent == []


@pytest.mark.asyncio
async def test_user_target_refuses_a_specific_target_or_an_unbound_channel(
    tmp_path,
) -> None:
    tool, sent, ledger, session_manager = _user_send_setup(tmp_path)
    with pytest.raises(ValueError, match="target_id"):
        await tool.execute(
            channel="qq",
            role_id="mira",
            target_kind="user",
            target_id="42",
            message="hi",
        )
    store = UserIdentityStore(tmp_path)
    for identity in store.list():
        store.unbind(identity.id)
    with pytest.raises(LookupError, match="没有在渠道 qq 绑定身份"):
        await tool.execute(
            channel="qq", role_id="mira", target_kind="user", message="hi"
        )
    assert sent == []
    assert ledger.list_for_role("mira") == []
    assert session_manager._store.fetch_session_messages("role:mira") == []


@pytest.mark.asyncio
async def test_user_target_on_a_telegram_bot_is_recorded_in_its_inbound_thread(
    tmp_path,
) -> None:
    # A Telegram Bot names its transport channel per instance (telegram_<ref>).
    tool, sent, _ledger, session_manager = _user_send_setup(
        tmp_path, plugin_id="telegram", user_id="555", chat_channel="telegram_mira"
    )

    await tool.execute(
        channel="telegram", role_id="mira", target_kind="user", message="在吗"
    )

    assert [(row["target_kind"], row["target_id"]) for row in sent] == [
        ("private", "555")
    ]
    # The thread the user's own messages in that chat are routed to.
    inbound_thread = ConversationService(session_manager).ensure_thread_for_session(
        LegacySessionDescriptor(
            session_key="telegram_mira:555",
            role_id="mira",
            channel="telegram_mira",
            chat_id="555",
        )
    )
    [stored] = session_manager._store.fetch_session_messages("role:mira")
    assert stored["thread_id"] == inbound_thread.id


async def test_a_failure_to_record_never_fails_the_delivered_send():
    event_bus = EventBus()
    event_bus.on(ExternalTextPushed, AsyncMock(side_effect=OSError("disk")))

    # The send already happened: the recording failure is logged, not raised.
    await record_delivered_push(
        event_bus,
        ExternalTextPushed(
            session_key="role:mira",
            role_id="mira",
            channel="qq",
            chat_id="gqq:5",
            text="该喝水啦",
            tool="account_send",
        ),
    )
