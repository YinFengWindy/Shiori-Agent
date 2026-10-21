from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from desktop_bridge.chat_requests import DesktopChatRequestHandler
from desktop_bridge.chat_service import ChatTurnBusyError
from desktop_bridge.session_presenter import DesktopSessionPresenter
from session.manager import Session


async def test_failed_send_retry_and_undo_keep_original_turn_and_other_threads(
    tmp_path, monkeypatch
):
    from copy import deepcopy
    from agent.core.passive_turn.pipeline import AgentCoreDeps, PassiveTurnPipeline
    from agent.core.runtime_support import TurnRunResult
    from agent.core.types import ContextBundle
    from agent.tools.registry import ToolRegistry
    from bus.event_bus import EventBus
    from conversation.service import ConversationService, desktop_thread_id
    from core.roles import RoleAggregateService, RoleStore
    from desktop_bridge.app_service import DesktopAppService
    from desktop_bridge.chat_service import DesktopChatService
    from session.manager import SessionManager
    from shiori_sdk.channels.threads import network_thread_id
    from shiori_sdk.messages import InboundMessage
    from agent.turns.reply_sequence import ReplySequencePolicy

    manager, bus, roles = SessionManager(tmp_path), EventBus(), RoleStore(tmp_path)
    roles.create_role(role_id="mira", name="Mira", system_prompt="test")
    role_service = RoleAggregateService.from_runtime(
        workspace=tmp_path, role_store=roles, session_manager=manager
    )
    conversations = ConversationService(manager)
    app = DesktopAppService(
        role_service=role_service,
        session_manager=manager,
        conversation_service=conversations,
    )
    presenter = DesktopSessionPresenter(conversations)
    session = (await app.open_role_session("mira")).session
    thread = desktop_thread_id("mira")
    session.add_message("user", "earlier user", thread_id=thread)
    session.add_message("assistant", "earlier answer", thread_id=thread)
    manager.save(session)
    earlier_ids = [row["id"] for row in session.messages]
    pipeline = PassiveTurnPipeline(
        AgentCoreDeps(
            session=SimpleNamespace(
                session_manager=manager, presence=None, relationship_runtime=None
            ),
            context_store=SimpleNamespace(
                prepare=AsyncMock(return_value=ContextBundle())
            ),
            context=SimpleNamespace(
                render=Mock(return_value=SimpleNamespace(system_prompt="", messages=[]))
            ),
            tools=ToolRegistry(),
            event_bus=bus,
            reasoner=SimpleNamespace(
                run_turn=AsyncMock(
                    side_effect=[
                        RuntimeError("model failed"),
                        TurnRunResult(
                            reply="first\n<message-break/>\nsecond",
                            reply_sequence=ReplySequencePolicy("<message-break/>"),
                        ),
                    ]
                )
            ),
        )
    )
    accepted_metadata = []

    class Loop:
        async def process_direct(
            self, content, *, session_key, channel, chat_id, metadata, **kwargs
        ):
            accepted_metadata.append(dict(metadata))
            output = await pipeline.run(
                InboundMessage(
                    channel=channel,
                    chat_id=chat_id,
                    sender="user",
                    content=content,
                    metadata={**metadata, "omit_user_turn": True},
                ),
                session_key,
                dispatch_outbound=False,
            )
            return output.content

    async def emit_payload(emit_event, payload):
        result = emit_event(payload)
        if result is not None:
            await result

    async def emit_session_updated(*, request_id, session, emit_event, messages=None):
        result = emit_event(
            {
                "id": request_id,
                "method": "session.updated",
                "payload": {
                    "session": presenter.serialize_summary(session),
                    "messages": messages or [],
                },
            }
        )
        if result is not None:
            await result

    chat = DesktopChatService(
        agent_loop=Loop(),
        event_bus=bus,
        session_manager=manager,
        role_id_from_session_key=lambda _: "mira",
        sync_desktop_session_thread=app.sync_desktop_session_thread,
        emit_payload=emit_payload,
        emit_session_updated=emit_session_updated,
    )
    handler = DesktopChatRequestHandler(
        role_service=role_service,
        app_service=app,
        chat_service=chat,
        start_chat_turn=chat.start_chat_turn,
        session_presenter=presenter,
    )
    monkeypatch.setattr("agent.turns.reply_sequence.wait_between_messages", AsyncMock())
    events = []
    sent = await handler.handle(
        "chat.send",
        {
            "role_id": "mira",
            "content": "please answer",
            "turn_id": "failed-turn",
            "client_message_id": "original-client",
        },
        request_id="failed-request",
        emit_event=events.append,
    )
    await chat.drain()
    assert events[-1]["method"] == "chat.error"
    failed_user = sent["message"]
    original_metadata = deepcopy(
        manager.get_or_create(session.key).messages[-1]["metadata"]
    )
    group_thread = network_thread_id("mira", "qq", "group")
    session.add_message("user", "unrelated group question", thread_id=group_thread)
    session.add_message("assistant", "unrelated group reply", thread_id=group_thread)
    await manager.append_messages(session, session.messages[-2:])
    unrelated_ids = [row["id"] for row in session.messages[-2:]]
    await handler.handle(
        "chat.retry",
        {
            "role_id": "mira",
            "turn_id": "retry-turn",
            "user_message_id": failed_user["id"],
        },
        request_id="retry-request",
        emit_event=events.append,
    )
    await chat.drain()
    assert [event["method"] for event in events if event["method"].startswith("chat.")][
        -1
    ] == "chat.done"
    replies = session.messages[-2:]
    assert [row["content"] for row in replies] == ["first", "second"]
    original_user = next(
        row for row in session.messages if row["id"] == failed_user["id"]
    )
    assert original_user["metadata"] == original_metadata
    undone = await manager.undo_last_turn(session.key)
    assert undone is not None
    assert undone.deleted_ids == [failed_user["id"], *[row["id"] for row in replies]]
    assert [
        row["id"]
        for row in SessionManager(tmp_path).get_or_create(session.key).messages
    ] == [*earlier_ids, *unrelated_ids]
    assert [metadata["trigger_user_message_id"] for metadata in accepted_metadata] == [
        failed_user["id"],
        failed_user["id"],
    ]
    await chat.aclose()
    await bus.aclose()


async def test_compact_command_is_intercepted_before_persistence_and_turn_dispatch():
    context = Mock()
    context.invoke = AsyncMock(return_value={"tokens": 12, "result": None})
    app, roles, start = Mock(), Mock(), Mock()
    handler = DesktopChatRequestHandler(
        role_service=roles,
        app_service=app,
        chat_service=Mock(),
        start_chat_turn=start,
        session_presenter=Mock(),
        context_requests=context,
    )
    response = await handler.handle(
        "chat.send",
        {
            "role_id": "mira",
            "content": " /COMPACT@Bot ",
            "media": ["draft-image.png"],
            "reply_to_content": "draft quote",
        },
        request_id="command",
        emit_event=AsyncMock(),
    )
    assert response == {"context": {"tokens": 12, "result": None}}
    context.invoke.assert_awaited_once_with("mira", compact=True)
    app.persist_desktop_user_message.assert_not_called()
    roles.open_role_async.assert_not_called()
    start.assert_not_called()


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
        metadata={
            **app_service.persist_desktop_user_message.call_args.kwargs["metadata"],
            "trigger_user_message_id": "user-id",
        },
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
            "custom_input_kind": "plugin",
            "plugin_trace": "trace-1",
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
    assert kwargs["metadata"]["trigger_user_message_id"] == "user-id"
    assert kwargs["metadata"]["request_id"] == "request-retry"
    assert kwargs["metadata"]["source"] == "desktop"
    assert kwargs["metadata"]["plugin_trace"] == "trace-1"
    assert kwargs["metadata"]["custom_input_kind"] == "plugin"


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
async def test_retry_ignores_channel_messages_stored_after_the_failed_turn():
    session = _failed_turn_session()
    session.add_message(
        "user",
        "群里的新消息",
        id="group-id",
        seq=3,
        metadata={"thread_id": "thread:mira:qq:group-1"},
    )
    handler, _, start_chat_turn = _retry_handler(session)

    response = await handler.handle(
        "chat.retry",
        {"role_id": "mira", "turn_id": "turn-retry", "user_message_id": "user-id"},
        request_id="request-retry",
        emit_event=AsyncMock(),
    )

    assert response["message"]["id"] == "user-id"
    start_chat_turn.assert_called_once()


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
