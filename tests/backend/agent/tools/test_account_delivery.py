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
)
from agent.turns.turn_pushes import current_turn_pushes
from bus.event_bus import EventBus
from conversation.push_sync import ExternalPushSyncService
from conversation.service import (
    ConversationService,
    LegacySessionDescriptor,
    network_thread_id,
)
from core.accounts import AccountRegistry
from core.accounts.delivery_ledger import AccountDeliveryLedger
from shiori_sdk.accounts.targets import AccountTarget
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
    metadata = stored["metadata"]
    assert metadata["source"] == "account_send"
    assert metadata["chat_type"] == "private"
    assert metadata["delivery_attempt_id"] == attempt.attempt_id
    assert metadata["external_message_id"] == "qq-9"
    assert metadata["via_account"] == _VIA


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
