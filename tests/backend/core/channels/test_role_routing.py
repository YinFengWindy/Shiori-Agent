"""RoleTurnRouter: a turn context first, routing only when asked (#721)."""

import pytest

from conversation.service import ConversationService
from core.channels.role_routing import RoleTurnRouter
from core.common.channel_directory import ChannelDirectory
from core.roles import RoleStore
from session.manager import SessionManager
from shiori_sdk.channels.threads import network_thread_id
from shiori_sdk.messages import InboundMessage

ROOM = network_thread_id("mira", "bilibili", "room-1")


def _router(tmp_path):
    roles = RoleStore(tmp_path)
    roles.create_role(role_id="mira", name="Mira", system_prompt="test")
    manager = SessionManager(tmp_path)
    router = RoleTurnRouter.from_workspace(
        tmp_path,
        session_manager=manager,
        role_store=roles,
        channel_directory=ChannelDirectory(),
    )
    return router, ConversationService(manager)


def _message(chat_id: str = "room-1") -> InboundMessage:
    return InboundMessage(
        channel="bilibili",
        sender="uid-7",
        chat_id=chat_id,
        content="主播好",
        metadata={
            "chat_type": "group",
            "group_name": "直播间",
            "external_message_id": "m1",
            "source": "external_turn",
        },
    )


def test_turn_context_touches_nothing_and_routing_carries_it(tmp_path):
    router, conversation = _router(tmp_path)
    message = _message()

    context = router.network_turn_context(message, "mira", source="external_turn")

    assert (context.thread_id, context.request_id) == (ROOM, "m1")
    assert conversation.get_thread(ROOM) is None
    routed = router.route(message, "mira", dict(message.metadata), context=context)
    thread = conversation.get_thread(ROOM)
    assert thread is not None
    assert conversation.contacts_by_id("mira")[thread.contact_id].display_name == (
        "直播间"
    )
    assert routed.metadata["request_id"] == "m1"
    assert routed.metadata["role_context_created_at"] == context.created_at


def test_routing_refuses_a_context_of_another_thread(tmp_path):
    router, _ = _router(tmp_path)
    context = router.network_turn_context(
        _message("room-2"), "mira", source="external_turn"
    )

    with pytest.raises(ValueError, match="不一致"):
        router.route(_message(), "mira", dict(_message().metadata), context=context)
