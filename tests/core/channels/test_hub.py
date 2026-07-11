from __future__ import annotations

from datetime import datetime
from pathlib import Path

from bus.events import InboundMessage, OutboundMessage
from core.channels import ChannelHub
from core.roles import RoleAggregateService, RoleStore
from session.manager import SessionManager


def test_channel_hub_routes_bound_inbound_to_thread_session(tmp_path: Path) -> None:
    session_manager = SessionManager(tmp_path)
    service = RoleAggregateService.from_runtime(
        workspace=tmp_path,
        role_store=RoleStore(tmp_path),
        session_manager=session_manager,
    )
    _ = service.create_role(
        role_id="mira",
        name="Mira",
        description="bound role",
        system_prompt="you are mira",
    )
    _ = service.bindings.bind("telegram", "123", "mira")
    hub = ChannelHub(service)

    routed = hub.route_inbound(
        InboundMessage(
            channel="telegram",
            sender="u1",
            chat_id="123",
            content="hello",
            timestamp=datetime.now(),
        )
    )

    assert routed.session_key == "thread:mira:telegram:123"
    assert routed.metadata["thread_id"] == "thread:mira:telegram:123"
    thread_session = session_manager.get_or_create("thread:mira:telegram:123")
    assert thread_session.metadata["role_name"] == "Mira"


def test_channel_hub_marks_delivery_by_thread_session(tmp_path: Path) -> None:
    session_manager = SessionManager(tmp_path)
    service = RoleAggregateService.from_runtime(
        workspace=tmp_path,
        role_store=RoleStore(tmp_path),
        session_manager=session_manager,
    )
    role = service.create_role(
        role_id="mira",
        name="Mira",
        description="bound role",
        system_prompt="you are mira",
    ).role
    session = session_manager.sync_thread_session_metadata(
        "thread:mira:telegram:123",
        role_id=role.id,
        role_name=role.name,
        role_prompt=role.system_prompt,
        thread_id="thread:mira:telegram:123",
        role_runtime_config=role.runtime_config,
        context_channel="telegram",
        context_chat_id="123",
        transport_channel="telegram",
        transport_chat_id="123",
    )
    session.add_message(
        "assistant",
        "reply",
        thread_id="thread:mira:telegram:123",
    )
    session_manager.save(session)
    hub = ChannelHub(service)

    updated = hub.mark_delivery(
        OutboundMessage(
            channel="telegram",
            chat_id="123",
            content="reply",
            metadata={
                "session_key_override": "thread:mira:telegram:123",
                "thread_id": "thread:mira:telegram:123",
            },
        ),
        default_channel="telegram",
        delivery_status="sent",
        external_message_id="tg-1",
    )

    assert updated is not None
    assert updated["delivery_status"] == "sent"
    assert updated["external_message_id"] == "tg-1"


def test_channel_hub_marks_archived_external_messages_as_duplicates(
    tmp_path: Path,
) -> None:
    session_manager = SessionManager(tmp_path)
    service = RoleAggregateService.from_runtime(
        workspace=tmp_path,
        role_store=RoleStore(tmp_path),
        session_manager=session_manager,
    )
    role = service.create_role(
        role_id="mira",
        name="Mira",
        description="bound role",
        system_prompt="you are mira",
    ).role
    _ = service.bindings.bind("telegram", "123", role.id)
    hub = ChannelHub(service)
    first = hub.route_inbound(
        InboundMessage(
            channel="telegram",
            sender="u1",
            chat_id="123",
            content="hello",
            metadata={"external_message_id": "message-1"},
        )
    )
    session = session_manager.get_or_create(first.session_key)
    session.add_message(
        "user",
        "hello",
        thread_id=str(first.metadata["thread_id"]),
        external_message_id="message-1",
    )
    session_manager.save(session)

    duplicate = hub.route_inbound(
        InboundMessage(
            channel="telegram",
            sender="u1",
            chat_id="123",
            content="hello",
            metadata={"external_message_id": "message-1"},
        )
    )

    assert duplicate.metadata["conversation_duplicate"] is True


def test_channel_hub_resolves_control_actions_to_thread_session(tmp_path: Path) -> None:
    session_manager = SessionManager(tmp_path)
    service = RoleAggregateService.from_runtime(
        workspace=tmp_path,
        role_store=RoleStore(tmp_path),
        session_manager=session_manager,
    )
    _ = service.create_role(
        role_id="mira",
        name="Mira",
        description="bound role",
        system_prompt="you are mira",
    )
    _ = service.bindings.bind("telegram", "123", "mira")
    hub = ChannelHub(service)
    _ = hub.route_inbound(
        InboundMessage(
            channel="telegram",
            sender="u1",
            chat_id="123",
            content="hello",
        )
    )

    assert hub.resolve_runtime_session_key("telegram", "123") == "thread:mira:telegram:123"


def test_channel_hub_attaches_complete_role_execution_context(tmp_path: Path) -> None:
    session_manager = SessionManager(tmp_path)
    service = RoleAggregateService.from_runtime(
        workspace=tmp_path,
        role_store=RoleStore(tmp_path),
        session_manager=session_manager,
    )
    _ = service.create_role(
        role_id="mira",
        name="Mira",
        description="bound role",
        system_prompt="you are mira",
    )
    _ = service.bindings.bind("telegram", "123", "mira")

    routed = ChannelHub(service).route_inbound(
        InboundMessage(
            channel="telegram",
            sender="u1",
            chat_id="123",
            content="hello",
            metadata={"external_message_id": "message-1"},
        )
    )

    assert routed.metadata["role_id"] == "mira"
    assert routed.metadata["thread_id"] == "thread:mira:telegram:123"
    assert routed.metadata["role_config_version"]
    assert routed.metadata["request_id"] == "message-1"
    assert routed.metadata["delivery_key"]
    assert routed.metadata["role_work_kind"] == "passive_turn"
