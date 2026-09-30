"""The phone's 旁听 block switches a group's listening and caps, as the user."""

from __future__ import annotations

from pathlib import Path

import pytest

from conversation.listening import GroupListeningControl
from conversation.service import ConversationService, LegacySessionDescriptor
from desktop_bridge.phone_listening_requests import DesktopPhoneListeningRequestHandler
from session.manager import SessionManager


def _conversation(
    manager: SessionManager, conversation: ConversationService, **chats: str
) -> dict[str, str]:
    """One stored message per ``channel:chat_id`` of role ``mira``, by chat type."""
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
    handler = DesktopPhoneListeningRequestHandler(
        GroupListeningControl(conversation, {"qq"}.__contains__)
    )
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
    with pytest.raises(ValueError):
        _ = await handler.handle("phone.listening.cap.set", {**group, "daily_cap": 0})
    # A private chat, and a group whose channel declares no listening, cannot be listened to.
    for key in ("qq__902", "feishu__oc_1"):
        with pytest.raises(ValueError, match="不支持旁听"):
            _ = await handler.handle(
                "phone.listening.set",
                {"role_id": "mira", "thread_id": threads[key], "enabled": True},
            )
