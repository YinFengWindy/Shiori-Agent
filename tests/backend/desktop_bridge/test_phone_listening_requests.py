"""The phone reads a group's listening records and switches and caps it, as the user."""

from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path

import pytest
from PIL import Image

from conversation.listening import GroupListeningControl
from conversation.service import ConversationService, LegacySessionDescriptor
from core.accounts import AccountRegistry
from core.channel_avatars import AvatarKey, ChannelAvatarStore
from shiori_sdk.channels.message_source import MessageSource
from core.identity import IdentityChat, UserIdentityStore
from desktop_bridge.phone_listening_requests import DesktopPhoneListeningRequestHandler
from desktop_bridge.phone_requests import DesktopPhoneRequestHandler
from desktop_bridge.session_presenter import DesktopSessionPresenter
from session.manager import SessionManager


def _conversation(
    manager: SessionManager, conversation: ConversationService, **chats: str
) -> dict[str, str]:
    """One stored message per ``channel__chat_id`` of role ``mira``, by chat type."""
    session = manager.get_or_create("role:mira")
    thread_ids: dict[str, str] = {}
    for key, chat_type in chats.items():
        channel, chat_id = key.split("__")
        thread = conversation.ensure_thread_for_session(
            LegacySessionDescriptor(
                session_key=f"{channel}:{chat_id}",
                role_id="mira",
                channel=channel,
                chat_id=chat_id,
            )
        )
        session.add_message(
            "user", "hi", metadata={"thread_id": thread.id, "chat_type": chat_type}
        )
        thread_ids[key] = thread.id
    manager.save(session)
    return thread_ids


def _handler(
    tmp_path: Path,
    conversation: ConversationService,
    accounts: AccountRegistry | None = None,
    avatars: ChannelAvatarStore | None = None,
) -> DesktopPhoneListeningRequestHandler:
    """Listening requests where only the QQ plugin declares group listening."""
    listening = GroupListeningControl(conversation, {"qq"}.__contains__)
    phone = DesktopPhoneRequestHandler(
        conversations=conversation,
        accounts=accounts or AccountRegistry({"mira"}.__contains__),
        identities=UserIdentityStore(tmp_path),
        messages=DesktopSessionPresenter(conversation),
        avatars=avatars or ChannelAvatarStore(tmp_path),
        listening=listening,
    )
    return DesktopPhoneListeningRequestHandler(listening, phone)


def _png() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (8, 8), "pink").save(output, format="PNG")
    return output.getvalue()


@pytest.mark.asyncio
async def test_the_user_switches_and_caps_a_listenable_group(tmp_path: Path) -> None:
    manager = SessionManager(tmp_path)
    conversation = ConversationService(manager)
    threads = _conversation(
        manager,
        conversation,
        qq__gqq_5="group",
        qq__902="private",
        feishu__oc_1="group",
    )
    handler = _handler(tmp_path, conversation)
    group = {"role_id": "mira", "thread_id": threads["qq__gqq_5"]}

    on = await handler.handle("phone.listening.set", {**group, "enabled": True})
    capped = await handler.handle("phone.listening.cap.set", {**group, "daily_cap": 20})
    saved = await handler.handle(
        "phone.listening.defaults.save", {"default_daily_cap": 50}
    )
    state = await handler.handle("phone.listening.state", group)

    assert on is not None and on["enabled"] is True
    assert capped is not None and capped["daily_cap"] == 20
    assert saved == {"default_daily_cap": 50}
    assert state is not None
    assert (state["enabled"], state["daily_cap"], state["default_daily_cap"]) == (
        True,
        20,
        50,
    )
    [toggle] = state["toggles"]
    assert (toggle["enabled"], toggle["operator"]) == (True, "user")
    for bad in (0, "20", True):
        with pytest.raises(ValueError):
            _ = await handler.handle(
                "phone.listening.cap.set", {**group, "daily_cap": bad}
            )
    # A private chat, and a group whose channel declares no listening, cannot be listened to.
    for key in ("qq__902", "feishu__oc_1"):
        with pytest.raises(ValueError, match="不支持旁听"):
            _ = await handler.handle(
                "phone.listening.set",
                {"role_id": "mira", "thread_id": threads[key], "enabled": True},
            )


@pytest.mark.asyncio
async def test_reads_a_groups_listening_records_after_listening_is_off(
    tmp_path: Path,
) -> None:
    manager = SessionManager(tmp_path)
    conversation = ConversationService(manager)
    group_id = _conversation(manager, conversation, qq__gqq_5="group")["qq__gqq_5"]
    group = conversation.get_thread(group_id)
    assert group is not None
    accounts = AccountRegistry({"mira"}.__contains__)
    qq = accounts.register(
        plugin_id="qq",
        platform="qq",
        platform_account_id="10001",
        config_ref="qq-1",
        token="q",
        role_id="mira",
    )
    identities = UserIdentityStore(tmp_path)
    _ = identities.pair(
        identities.create_pairing_code().code,
        record=qq.record,
        user_id="100",
        scope="platform",
        chat=IdentityChat(qq.record.id, "qq", "100"),
    )
    avatars = ChannelAvatarStore(tmp_path)
    avatars.save(AvatarKey("sender", "qq", "100"), _png(), plugin_id="qq")
    handler = _handler(tmp_path, conversation, accounts, avatars)
    listening = conversation.listening
    listening.switches.set_enabled(group.id, True, operator="user")
    source = MessageSource(
        channel="qq",
        chat_id="gqq_5",
        chat_type="group",
        sender_id="100",
        sender_name="主人",
    )
    heard = listening.hear(
        group.id,
        sender_id="100",
        content="今晚开黑",
        source=source.to_metadata(),
        external_message_id="",
        timestamp=datetime(2026, 9, 30, 20, 0).astimezone(),
    )
    assert heard is not None
    listening.switches.set_enabled(group.id, False, operator="user")

    page = await handler.handle(
        "phone.listening.messages", {"role_id": "mira", "thread_id": group.id}
    )

    assert page is not None
    [row] = page["messages"]
    assert (row["content"], row["sender_name"], row["listened"]) == (
        "今晚开黑",
        "主人",
        True,
    )
    assert row["sender_is_user"] is True
    # The sender's cached avatar shows as on conversation rows.
    assert row["sender_avatar_abs"] == avatars.index().sender("qq", "100")
    assert page["has_more"] is False
    # The live event carries the same row.
    assert handler.heard_update(heard) == {
        "role_id": "mira",
        "thread_id": group.id,
        "message": row,
    }
