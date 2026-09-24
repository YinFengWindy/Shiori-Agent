from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from desktop_bridge.chat_requests import DesktopChatRequestHandler
from desktop_bridge.chat_service import ChatTurnBusyError
from desktop_bridge.session_presenter import DesktopSessionPresenter
from session.manager import Session


@pytest.mark.asyncio
async def test_send_serializes_returned_user_message_when_session_tail_has_changed():
    session = Session(key="role:mira")
    session.add_message(
        "user",
        "my message",
        id="user-id",
        seq=1,
        media=["photo.png"],
        metadata={"client_message_id": "client-user", "turn_id": "turn-user"},
    )
    persisted = session.messages[0]
    session.add_message("assistant", "proactive reply", id="assistant-id", seq=2)
    app_service = Mock()
    app_service.build_desktop_user_message_metadata.side_effect = (
        lambda metadata, **kwargs: metadata
    )
    app_service.persist_desktop_user_message = AsyncMock(return_value=persisted)
    role_service = Mock()
    role_service.open_role_async = AsyncMock(
        return_value=SimpleNamespace(
            role=SimpleNamespace(id="mira"),
            session=session,
        )
    )
    chat_service = Mock()
    chat_service.is_busy.return_value = False
    start_chat_turn = Mock()
    handler = DesktopChatRequestHandler(
        role_service=role_service,
        app_service=app_service,
        chat_service=chat_service,
        start_chat_turn=start_chat_turn,
        session_presenter=DesktopSessionPresenter(Mock()),
        sanitize_voice_metrics=Mock(),
    )
    emit_event = AsyncMock()

    response = await handler.handle(
        "chat.send",
        {
            "role_id": "mira",
            "content": "my message",
            "media": ["photo.png"],
            "client_message_id": "client-user",
            "turn_id": "turn-user",
        },
        request_id="request-user",
        emit_event=emit_event,
    )

    assert response["message"]["id"] == "user-id"
    assert response["message"]["seq"] == 1
    assert response["message"]["role"] == "user"
    assert response["message"]["content"] == "my message"
    assert response["message"]["media"] == ["photo.png"]
    assert response["message"]["metadata"]["client_message_id"] == "client-user"
    assert response["turn_id"] == "turn-user"
    assert response["session"]["key"] == session.key
    app_service.persist_desktop_user_message.assert_awaited_once()
    start_chat_turn.assert_called_once_with(
        request_id="request-user",
        turn_id="turn-user",
        session_key=session.key,
        content="my message",
        media=["photo.png"],
        metadata=app_service.persist_desktop_user_message.call_args.kwargs["metadata"],
        omit_user_turn=True,
        emit_event=emit_event,
    )


def _retry_handler(session: Session, *, busy: bool = False):
    app_service = Mock()
    app_service.persist_desktop_user_message = AsyncMock()
    role_service = Mock()
    role_service.open_role_async = AsyncMock(
        return_value=SimpleNamespace(role=SimpleNamespace(id="mira"), session=session)
    )
    chat_service = Mock()
    chat_service.is_busy.return_value = busy
    start_chat_turn = Mock()
    handler = DesktopChatRequestHandler(
        role_service=role_service,
        app_service=app_service,
        chat_service=chat_service,
        start_chat_turn=start_chat_turn,
        session_presenter=DesktopSessionPresenter(Mock()),
        sanitize_voice_metrics=Mock(),
    )
    return handler, app_service, start_chat_turn


def _failed_turn_session() -> Session:
    session = Session(key="role:mira")
    session.add_message("assistant", "earlier reply", id="assistant-id", seq=1)
    session.add_message(
        "user",
        "看看这张图",
        id="user-id",
        seq=2,
        media=["photo.png"],
        metadata={
            "turn_id": "turn-failed",
            "request_id": "request-failed",
            "reply_to_content": "earlier reply",
            "reply_to_sender": "Mira",
            "input_method": "voice",
            "voice_turn_id": "voice-1",
            "source": "desktop",
        },
    )
    return session


@pytest.mark.asyncio
async def test_retry_reruns_the_failed_turn_on_the_persisted_user_message():
    session = _failed_turn_session()
    handler, app_service, start_chat_turn = _retry_handler(session)
    emit_event = AsyncMock()

    response = await handler.handle(
        "chat.retry",
        {"role_id": "mira", "turn_id": "turn-retry", "user_message_id": "user-id"},
        request_id="request-retry",
        emit_event=emit_event,
    )

    # No new user message: the timeline keeps the one the failed turn stored.
    app_service.persist_desktop_user_message.assert_not_awaited()
    assert len(session.messages) == 2
    assert response["message"]["id"] == "user-id"
    assert response["turn_id"] == "turn-retry"
    kwargs = start_chat_turn.call_args.kwargs
    assert kwargs["omit_user_turn"] is True
    assert kwargs["turn_id"] == "turn-retry"
    assert kwargs["media"] == ["photo.png"]
    assert "看看这张图" in kwargs["content"]
    assert "earlier reply" in kwargs["content"]
    assert kwargs["metadata"]["turn_id"] == "turn-retry"
    assert kwargs["metadata"]["request_id"] == "request-retry"
    assert kwargs["metadata"]["source"] == "desktop"
    assert "voice_turn_id" not in kwargs["metadata"]
    assert "input_method" not in kwargs["metadata"]


@pytest.mark.asyncio
async def test_retry_refuses_a_turn_the_conversation_has_moved_past():
    session = _failed_turn_session()
    session.add_message("assistant", "a reply arrived", id="later-id", seq=3)
    handler, _, start_chat_turn = _retry_handler(session)

    with pytest.raises(ValueError, match="只能重试最近一次失败的回合"):
        await handler.handle(
            "chat.retry",
            {"role_id": "mira", "turn_id": "turn-retry", "user_message_id": "user-id"},
            request_id="request-retry",
            emit_event=AsyncMock(),
        )
    start_chat_turn.assert_not_called()


@pytest.mark.asyncio
async def test_retry_refuses_a_stale_user_message_id():
    handler, _, start_chat_turn = _retry_handler(_failed_turn_session())

    with pytest.raises(ValueError, match="只能重试最近一次失败的回合"):
        await handler.handle(
            "chat.retry",
            {"role_id": "mira", "turn_id": "turn-retry", "user_message_id": "old-id"},
            request_id="request-retry",
            emit_event=AsyncMock(),
        )
    start_chat_turn.assert_not_called()


@pytest.mark.asyncio
async def test_retry_refuses_while_a_turn_is_running():
    handler, _, start_chat_turn = _retry_handler(_failed_turn_session(), busy=True)

    with pytest.raises(ChatTurnBusyError):
        await handler.handle(
            "chat.retry",
            {"role_id": "mira", "turn_id": "turn-retry", "user_message_id": "user-id"},
            request_id="request-retry",
            emit_event=AsyncMock(),
        )
    start_chat_turn.assert_not_called()
