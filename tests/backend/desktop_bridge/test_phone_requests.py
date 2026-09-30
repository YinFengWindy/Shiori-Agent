"""The phone lists a role's channel conversations under the account carrying each."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from conversation.listening import GroupListeningControl
from conversation.models import ThreadRecord
from conversation.service import ConversationService, LegacySessionDescriptor
from core.accounts import AccountRecord, AccountRegistry
from core.channel_avatars import AvatarKey, ChannelAvatarStore
from core.common.message_source import MessageSource
from core.identity import IdentityChat, UserIdentityStore
from desktop_bridge.phone_requests import DesktopPhoneRequestHandler
from desktop_bridge.session_presenter import DesktopSessionPresenter
from session.manager import SessionManager


def _thread(
    conversation: ConversationService,
    *,
    role_id: str,
    channel: str,
    chat_id: str,
    name: str | None = None,
) -> ThreadRecord:
    thread = conversation.ensure_thread_for_session(
        LegacySessionDescriptor(
            session_key=f"{channel}:{chat_id}",
            role_id=role_id,
            channel=channel,
            chat_id=chat_id,
        )
    )
    if name is not None:
        conversation.remember_contact_name(thread, name)
    return thread


def _listening(conversation: ConversationService) -> GroupListeningControl:
    """Only the QQ plugin declares group listening."""
    return GroupListeningControl(conversation, {"qq"}.__contains__)


def _metadata(
    thread: ThreadRecord, *, chat_type: str, sender_name: str | None = None
) -> dict[str, Any]:
    source = MessageSource(
        channel=thread.channel,
        chat_id=thread.external_thread_id,
        chat_type=chat_type,
        sender_id="sender",
        sender_name=sender_name,
    )
    return {
        "thread_id": thread.id,
        "chat_type": chat_type,
        "message_source": source.to_metadata(),
    }


@pytest.mark.asyncio
async def test_lists_the_roles_channel_conversations_newest_first(
    tmp_path: Path,
) -> None:
    manager = SessionManager(tmp_path)
    conversation = ConversationService(manager)
    accounts = AccountRegistry({"mira", "other"}.__contains__)
    telegram = accounts.register(
        plugin_id="telegram",
        platform="telegram",
        platform_account_id="bot1",
        config_ref="bot1",
        token="t",
        role_id="mira",
    )
    qq = accounts.register(
        plugin_id="qq",
        platform="qq",
        platform_account_id="10001",
        config_ref="qq-1",
        token="q",
        role_id="mira",
    )
    # Feishu names its channel ``feishu:<ref>``, the ref being ``<domain>:<app_id>``.
    feishu = accounts.register(
        plugin_id="feishu",
        platform="feishu",
        platform_account_id="feishu:cli_a",
        config_ref="feishu:cli_a",
        token="f",
        role_id="mira",
    )
    _ = accounts.register(
        plugin_id="qq",
        platform="qq",
        platform_account_id="10002",
        config_ref="qq-2",
        token="q2",
        role_id="other",
    )
    identities = UserIdentityStore(tmp_path)
    _ = identities.pair(
        identities.create_pairing_code().code,
        record=telegram.record,
        user_id="owner",
        scope="account",
        chat=IdentityChat(telegram.record.id, "telegram_bot1", "100"),
    )
    private = _thread(
        conversation,
        role_id="mira",
        channel="telegram_bot1",
        chat_id="100",
        name="小明",
    )
    group = _thread(
        conversation, role_id="mira", channel="qq", chat_id="gqq:5", name="摸鱼群"
    )
    feishu_chat = _thread(
        conversation,
        role_id="mira",
        channel="feishu:feishu:cli_a",
        chat_id="oc_1",
        name="项目群",
    )
    # The role has no QQBot account, so this conversation belongs to no app.
    orphan = _thread(conversation, role_id="mira", channel="qqbot", chat_id="c2c:7")
    _ = _thread(conversation, role_id="mira", channel="qq", chat_id="silent")
    others = _thread(conversation, role_id="other", channel="qq", chat_id="gqq:9")

    session = manager.get_or_create("role:mira")
    session.add_message("user", "桌面消息", timestamp="2026-09-29T12:00:00+08:00")
    session.add_message(
        "assistant",
        "晚安",
        timestamp="2026-09-29T09:00:00+08:00",
        metadata=_metadata(private, chat_type="private"),
    )
    session.add_message(
        "user",
        "谁来开黑",
        media=["photo.png"],
        timestamp="2026-09-29T10:00:00+08:00",
        metadata=_metadata(group, chat_type="group", sender_name="阿花"),
    )
    # The role's reply records no chat type; the group message before it does.
    session.add_message(
        "assistant",
        "我来",
        timestamp="2026-09-29T10:30:00+08:00",
        metadata={"thread_id": group.id},
    )
    session.add_message(
        "user",
        "周会改到三点",
        timestamp="2026-09-28T20:00:00+08:00",
        metadata=_metadata(feishu_chat, chat_type="group", sender_name="老王"),
    )
    session.add_message(
        "user",
        "在吗",
        # A naive legacy time is local time.
        timestamp="2026-09-28T08:00:00",
        metadata=_metadata(orphan, chat_type="unknown", sender_name="小红"),
    )
    manager.save(session)
    other_session = manager.get_or_create("role:other")
    other_session.add_message(
        "user", "别人的群", metadata=_metadata(others, chat_type="group")
    )
    manager.save(other_session)
    handler = DesktopPhoneRequestHandler(
        conversations=conversation,
        accounts=accounts,
        identities=identities,
        messages=DesktopSessionPresenter(conversation),
        avatars=ChannelAvatarStore(tmp_path),
        listening=_listening(conversation),
    )

    result = await handler.handle("phone.conversations.list", {"role_id": "mira"})

    assert result == {
        "conversations": [
            {
                "thread_id": group.id,
                "account_id": qq.record.id,
                "channel": "qq",
                "chat_type": "group",
                "display_name": "摸鱼群",
                "avatar_abs": None,
                "is_user_chat": False,
                # A QQ group: its plugin declares listening.
                "listening_supported": True,
                "last_message": {
                    "role": "assistant",
                    "content": "我来",
                    "timestamp": "2026-09-29T10:30:00+08:00",
                    "has_media": False,
                    "sender_name": None,
                },
            },
            {
                "thread_id": private.id,
                "account_id": telegram.record.id,
                "channel": "telegram_bot1",
                "chat_type": "private",
                "display_name": "小明",
                "avatar_abs": None,
                "is_user_chat": True,
                "listening_supported": False,
                "last_message": {
                    "role": "assistant",
                    "content": "晚安",
                    "timestamp": "2026-09-29T09:00:00+08:00",
                    "has_media": False,
                    "sender_name": None,
                },
            },
            {
                "thread_id": feishu_chat.id,
                "account_id": feishu.record.id,
                "channel": "feishu:feishu:cli_a",
                "chat_type": "group",
                "display_name": "项目群",
                "avatar_abs": None,
                "is_user_chat": False,
                # A group, but Feishu declares no listening: no 旁听 block.
                "listening_supported": False,
                "last_message": {
                    "role": "user",
                    "content": "周会改到三点",
                    "timestamp": "2026-09-28T20:00:00+08:00",
                    "has_media": False,
                    "sender_name": "老王",
                },
            },
            {
                "thread_id": orphan.id,
                "account_id": None,
                "channel": "qqbot",
                # Only an ``unknown`` type was recorded: no guess.
                "chat_type": None,
                "display_name": "c2c:7",
                "avatar_abs": None,
                "is_user_chat": False,
                "listening_supported": False,
                "last_message": {
                    "role": "user",
                    "content": "在吗",
                    "timestamp": "2026-09-28T08:00:00",
                    "has_media": False,
                    "sender_name": "小红",
                },
            },
        ]
    }


@pytest.mark.asyncio
async def test_requires_a_role_and_leaves_other_methods_alone(
    tmp_path: Path,
) -> None:
    manager = SessionManager(tmp_path)
    conversation = ConversationService(manager)
    handler = DesktopPhoneRequestHandler(
        conversations=conversation,
        accounts=AccountRegistry({"mira"}.__contains__),
        identities=UserIdentityStore(tmp_path),
        messages=DesktopSessionPresenter(conversation),
        avatars=ChannelAvatarStore(tmp_path),
        listening=_listening(conversation),
    )

    with pytest.raises(ValueError, match="role_id"):
        _ = await handler.handle("phone.conversations.list", {"role_id": " "})
    assert await handler.handle("accounts.list", {}) is None


def _handler(tmp_path: Path, conversation: ConversationService):
    """A handler whose role ``mira`` has a QQ account, and that account's record."""
    accounts = AccountRegistry({"mira", "other"}.__contains__)
    qq = accounts.register(
        plugin_id="qq",
        platform="qq",
        platform_account_id="10001",
        config_ref="qq-1",
        token="q",
        role_id="mira",
        display_name="小栞",
    )
    handler = DesktopPhoneRequestHandler(
        conversations=conversation,
        accounts=accounts,
        identities=UserIdentityStore(tmp_path),
        messages=DesktopSessionPresenter(conversation),
        avatars=ChannelAvatarStore(tmp_path),
        listening=_listening(conversation),
    )
    return handler, qq.record


def _bind(tmp_path: Path, record: AccountRecord, user_id: str) -> str:
    """Binds ``user_id`` on the QQ platform as the desktop user; its binding ID."""
    identities = UserIdentityStore(tmp_path)
    identity = identities.pair(
        identities.create_pairing_code().code,
        record=record,
        user_id=user_id,
        scope="platform",
        chat=IdentityChat(record.id, "qq", user_id),
    )
    assert identity is not None
    return identity.id


def _group_message(
    thread: ThreadRecord,
    *,
    sender_id: str,
    name: str,
    is_user: bool = False,
    mentioned_ids: tuple[str, ...] = (),
) -> dict[str, Any]:
    source = MessageSource(
        channel=thread.channel,
        chat_id=thread.external_thread_id,
        chat_type="group",
        sender_id=sender_id,
        sender_name=name,
        sender_is_user=is_user,
        mentioned_ids=mentioned_ids,
    )
    return {"thread_id": thread.id, "message_source": source.to_metadata()}


@pytest.mark.asyncio
async def test_reads_one_conversation_page_by_page_from_the_roles_view(
    tmp_path: Path,
) -> None:
    manager = SessionManager(tmp_path)
    conversation = ConversationService(manager)
    group = _thread(conversation, role_id="mira", channel="qq", chat_id="gqq:5")
    other_group = _thread(conversation, role_id="mira", channel="qq", chat_id="gqq:6")
    session = manager.get_or_create("role:mira")
    session.add_message(
        "user",
        "谁来开黑",
        timestamp="2026-09-29T10:00:00+08:00",
        # Flagged as the user's when it arrived; no binding recognises 42 now.
        metadata=_group_message(group, sender_id="42", name="阿花", is_user=True),
    )
    session.add_message("user", "桌面消息")
    session.add_message(
        "user", "别的群", metadata=_group_message(other_group, sender_id="7", name="x")
    )
    session.add_message(
        "user",
        "我也来",
        media=["photo.png"],
        timestamp="2026-09-29T10:01:00+08:00",
        # Stored before 100 was bound.
        metadata=_group_message(group, sender_id="100", name="主人"),
    )
    session.add_message(
        "assistant",
        "我来",
        timestamp="2026-09-29T10:02:00+08:00",
        metadata={"thread_id": group.id},
    )
    manager.save(session)
    handler, qq = _handler(tmp_path, conversation)
    _ = _bind(tmp_path, qq, "100")

    newest = await handler.handle(
        "phone.conversation.messages",
        {"role_id": "mira", "thread_id": group.id, "limit": 2},
    )
    assert newest is not None
    assert newest["has_more"] is True
    assert [
        {key: row[key] for key in row if key not in {"id", "seq"}}
        for row in newest["messages"]
    ] == [
        {
            "sender": "other",
            "sender_id": "100",
            "sender_name": "主人",
            "sender_is_user": True,
            "sender_avatar_abs": None,
            "mentions": [],
            "quote": None,
            "content": "我也来",
            "media": ["photo.png"],
            "timestamp": "2026-09-29T10:01:00+08:00",
            "listened": False,
        },
        {
            "sender": "role",
            "sender_id": None,
            "sender_name": None,
            "sender_is_user": False,
            "sender_avatar_abs": None,
            "mentions": [],
            "quote": None,
            "content": "我来",
            "media": [],
            "timestamp": "2026-09-29T10:02:00+08:00",
            "listened": False,
        },
    ]
    assert newest["next_before_seq"] == newest["messages"][0]["seq"]

    older = await handler.handle(
        "phone.conversation.messages",
        {
            "role_id": "mira",
            "thread_id": group.id,
            "before_seq": newest["next_before_seq"],
            "limit": 2,
        },
    )
    assert older is not None
    # Only this conversation's rows: the desktop and the other group's are skipped.
    assert [row["content"] for row in older["messages"]] == ["谁来开黑"]
    assert older["messages"][0]["sender_name"] == "阿花"
    assert older["messages"][0]["sender_is_user"] is False
    assert older["has_more"] is False


@pytest.mark.asyncio
async def test_rows_name_the_members_a_message_mentions(tmp_path: Path) -> None:
    manager = SessionManager(tmp_path)
    conversation = ConversationService(manager)
    group = _thread(conversation, role_id="mira", channel="qq", chat_id="gqq:5")
    session = manager.get_or_create("role:mira")
    session.add_message(
        "user", "在吗", metadata=_group_message(group, sender_id="42", name="阿花")
    )
    session.add_message(
        "user",
        "ping",
        # 平台码入库前已剥掉，只剩 mentioned_ids（#553）。
        metadata=_group_message(
            group, sender_id="7", name="路人", mentioned_ids=("10001", "42", "99")
        ),
    )
    manager.save(session)
    handler, _ = _handler(tmp_path, conversation)

    page = await handler.handle(
        "phone.conversation.messages", {"role_id": "mira", "thread_id": group.id}
    )
    assert page is not None
    # 角色自己的账号用账号名，群友用本群记下的昵称，都没有时只有 ID。
    assert page["messages"][-1]["mentions"] == [
        {"id": "10001", "name": "小栞"},
        {"id": "42", "name": "阿花"},
        {"id": "99", "name": None},
    ]


@pytest.mark.asyncio
async def test_row_carries_the_message_it_quotes_apart_from_its_own(
    tmp_path: Path,
) -> None:
    manager = SessionManager(tmp_path)
    conversation = ConversationService(manager)
    group = _thread(conversation, role_id="mira", channel="qq", chat_id="gqq:5")
    session = manager.get_or_create("role:mira")
    metadata = _group_message(group, sender_id="42", name="阿花")
    metadata["message_source"]["reply_to_sender_id"] = "10001"
    session.add_message(
        "user",
        "这是啥",
        media=["own.png"],
        metadata={
            **metadata,
            "reply_to_content": "看",
            "reply_to_media": ["quoted.png"],
        },
    )
    manager.save(session)
    handler, _ = _handler(tmp_path, conversation)

    page = await handler.handle(
        "phone.conversation.messages", {"role_id": "mira", "thread_id": group.id}
    )
    assert page is not None
    [row] = page["messages"]
    # 引用角色自己的消息时用账号名，与 @ 的名字规则一致（#555）。
    assert row["quote"] == {
        "sender_id": "10001",
        "name": "小栞",
        "content": "看",
        "media": ["quoted.png"],
    }
    assert (row["content"], row["media"]) == ("这是啥", ["own.png"])


@pytest.mark.asyncio
async def test_reads_only_the_roles_own_channel_conversations(
    tmp_path: Path,
) -> None:
    manager = SessionManager(tmp_path)
    conversation = ConversationService(manager)
    others = _thread(conversation, role_id="other", channel="qq", chat_id="gqq:9")
    desktop = conversation.ensure_desktop_thread("mira")
    handler, _ = _handler(tmp_path, conversation)

    for thread_id in (others.id, desktop.id, "thread:mira:qq:missing"):
        with pytest.raises(ValueError, match="不属于"):
            _ = await handler.handle(
                "phone.conversation.messages",
                {"role_id": "mira", "thread_id": thread_id},
            )


@pytest.mark.asyncio
async def test_the_user_mark_follows_the_current_bindings(tmp_path: Path) -> None:
    manager = SessionManager(tmp_path)
    conversation = ConversationService(manager)
    group = _thread(conversation, role_id="mira", channel="qq", chat_id="gqq:5")
    session = manager.get_or_create("role:mira")
    session.add_message(
        "user", "早", metadata=_group_message(group, sender_id="100", name="主人")
    )
    manager.save(session)
    handler, qq = _handler(tmp_path, conversation)

    async def marked() -> bool:
        page = await handler.handle(
            "phone.conversation.messages", {"role_id": "mira", "thread_id": group.id}
        )
        assert page is not None
        return page["messages"][0]["sender_is_user"]

    assert await marked() is False
    identity_id = _bind(tmp_path, qq, "100")
    assert await marked() is True
    # Live rows are marked the same way.
    [update] = handler.conversation_updates("mira", session.messages)
    assert update["messages"][0]["sender_is_user"] is True
    UserIdentityStore(tmp_path).unbind(identity_id)
    assert await marked() is False


def _png() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (8, 8), "pink").save(output, format="PNG")
    return output.getvalue()


@pytest.mark.asyncio
async def test_cached_avatars_come_with_rows_messages_and_live_updates(
    tmp_path: Path,
) -> None:
    manager = SessionManager(tmp_path)
    conversation = ConversationService(manager)
    group = _thread(
        conversation, role_id="mira", channel="qq", chat_id="gqq:5", name="摸鱼群"
    )
    private = _thread(
        conversation, role_id="mira", channel="qq", chat_id="42", name="阿花"
    )
    session = manager.get_or_create("role:mira")
    session.add_message(
        "user", "谁来开黑", metadata=_group_message(group, sender_id="42", name="阿花")
    )
    session.add_message(
        "user", "我也来", metadata=_group_message(group, sender_id="7", name="小明")
    )
    session.add_message("assistant", "我来", metadata={"thread_id": group.id})
    session.add_message(
        "user", "在吗", metadata=_metadata(private, chat_type="private")
    )
    manager.save(session)
    avatars = ChannelAvatarStore(tmp_path)
    avatars.save(AvatarKey("sender", "qq", "42"), _png(), plugin_id="qq")
    avatars.save(AvatarKey("chat", "qq", "gqq:5"), _png(), plugin_id="qq")
    sender = avatars.index().sender("qq", "42")
    group_avatar = avatars.index().chat("qq", "gqq:5")
    assert sender is not None and group_avatar is not None
    handler = DesktopPhoneRequestHandler(
        conversations=conversation,
        accounts=AccountRegistry({"mira"}.__contains__),
        identities=UserIdentityStore(tmp_path),
        messages=DesktopSessionPresenter(conversation),
        avatars=avatars,
        listening=_listening(conversation),
    )

    listed = await handler.handle("phone.conversations.list", {"role_id": "mira"})
    page = await handler.handle(
        "phone.conversation.messages", {"role_id": "mira", "thread_id": group.id}
    )
    [update] = handler.conversation_updates("mira", session.messages[:1])

    assert listed is not None and page is not None
    # The private chat's avatar is not cached yet: its row keeps the placeholder.
    assert {row["thread_id"]: row["avatar_abs"] for row in listed["conversations"]} == {
        group.id: group_avatar,
        private.id: None,
    }
    assert [row["sender_avatar_abs"] for row in page["messages"]] == [
        sender,
        None,
        None,
    ]
    assert update["conversation"]["avatar_abs"] == group_avatar
    assert update["messages"][0]["sender_avatar_abs"] == sender
