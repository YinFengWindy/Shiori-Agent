from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from bus.events import InboundMessage, OutboundMessage
from core.channels import ChannelHub
from core.common.channel_directory import ChannelDirectory
from core.roles import RoleAggregateService, RoleStore
from session.manager import SessionManager


def test_channel_hub_routes_bound_inbound_to_role_session(tmp_path: Path) -> None:
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
    _ = service.bindings.bind("telegram", "123", "mira", contact_id="u1")
    hub = ChannelHub(service, channel_directory=_directory_with_private_telegram())

    routed = hub.route_inbound(
        InboundMessage(
            channel="telegram",
            sender="u1",
            chat_id="123",
            content="hello",
            timestamp=datetime.now(),
        )
    )

    assert routed.session_key == "role:mira"
    assert routed.metadata["thread_id"] == "thread:mira:telegram:123"
    assert routed.metadata["sender_id"] == "u1"
    assert routed.metadata["chat_type"] == "private"
    role_session = session_manager.get_or_create("role:mira")
    assert role_session.metadata["role_name"] == "Mira"
    assert (
        not {
            "thread_id",
            "context_channel",
            "context_chat_id",
            "transport_channel",
            "transport_chat_id",
        }
        & role_session.metadata.keys()
    )
    assert session_manager._store.get_session_meta("thread:mira:telegram:123") is None


def _directory_with_private_telegram() -> ChannelDirectory:
    class _Telegram:
        default_chat_type = "private"

    directory = ChannelDirectory()
    directory.bind({"telegram": _Telegram()}.get)
    return directory


def test_channel_hub_chat_type_default_comes_from_the_channel(tmp_path: Path) -> None:
    session_manager = SessionManager(tmp_path)
    service = RoleAggregateService.from_runtime(
        workspace=tmp_path,
        role_store=RoleStore(tmp_path),
        session_manager=session_manager,
    )
    _ = service.create_role(role_id="mira", name="Mira", system_prompt="mira")
    _ = service.bindings.bind("telegram", "123", "mira", contact_id="u1")
    _ = service.bindings.bind("qqbot", "c2c:u2", "mira", contact_id="u2")
    hub = ChannelHub(service, channel_directory=_directory_with_private_telegram())

    def _route(channel: str, chat_id: str, sender: str, **metadata: str):
        return hub.route_inbound(
            InboundMessage(
                channel=channel,
                sender=sender,
                chat_id=chat_id,
                content="hello",
                metadata=dict(metadata),
            )
        ).metadata["chat_type"]

    assert _route("telegram", "123", "u1") == "private"
    assert _route("telegram", "123", "u1", chat_type="group") == "group"
    assert _route("qqbot", "c2c:u2", "u2") == "unknown"
    assert (
        ChannelHub(service)
        .route_inbound(
            InboundMessage(channel="telegram", sender="u1", chat_id="123", content="hi")
        )
        .metadata["chat_type"]
        == "unknown"
    )


def test_channel_hub_marks_delivery_by_role_session(tmp_path: Path) -> None:
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
    _ = service.bindings.bind("telegram", "123", role.id, contact_id="u1")
    routed = ChannelHub(service).route_inbound(
        InboundMessage(
            channel="telegram",
            sender="u1",
            chat_id="123",
            content="hello",
        )
    )
    session = session_manager.get_or_create(routed.session_key)
    session.add_message(
        "assistant",
        "reply",
        thread_id="thread:mira:telegram:123",
    )
    session_manager.save(session)
    committed_message_id = str(session.messages[-1]["id"])
    hub = ChannelHub(service)

    updated = hub.mark_delivery(
        OutboundMessage(
            channel="telegram",
            chat_id="123",
            content="reply",
            metadata={
                "role_id": "mira",
                "session_key_override": "role:mira",
                "thread_id": str(routed.metadata["thread_id"]),
            },
            committed_message_id=committed_message_id,
        ),
        default_channel="telegram",
        delivery_status="sent",
        external_message_id="tg-1",
    )

    assert updated is not None
    assert updated["id"] == committed_message_id
    assert updated["delivery_status"] == "sent"
    assert updated["external_message_id"] == "tg-1"


def test_channel_hub_skips_delivery_mark_when_outbound_has_no_committed_message(
    tmp_path: Path,
) -> None:
    """Regresses the #305 incident: a fallback outbound message built from reused

    inbound metadata (no reference to any persisted row, e.g. the "处理消息时出错，
    请稍后再试。" turn-failure notice) must never fall back to guessing "the
    thread's latest assistant message" and must leave that unrelated, already
    delivered message's bookkeeping untouched.
    """
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
    _ = service.bindings.bind("telegram", "123", role.id, contact_id="u1")
    routed = ChannelHub(service).route_inbound(
        InboundMessage(
            channel="telegram",
            sender="u1",
            chat_id="123",
            content="hello",
        )
    )
    thread_id = str(routed.metadata["thread_id"])
    session = session_manager.get_or_create(routed.session_key)
    # An unrelated, already-delivered proactive push sitting as the thread's
    # latest assistant message when the failed turn's fallback fires later.
    session.add_message("assistant", "unrelated proactive push", thread_id=thread_id)
    session_manager.save(session)
    unrelated_message_id = str(session.messages[-1]["id"])
    hub = ChannelHub(service)
    baseline = hub.mark_delivery(
        OutboundMessage(
            channel="telegram",
            chat_id="123",
            content="unrelated proactive push",
            metadata={
                "role_id": "mira",
                "session_key_override": "role:mira",
                "thread_id": thread_id,
            },
            committed_message_id=unrelated_message_id,
        ),
        default_channel="telegram",
        delivery_status="sent",
        external_message_id="tg-earlier",
    )
    assert baseline is not None
    assert baseline["delivery_status"] == "sent"
    assert baseline["external_message_id"] == "tg-earlier"

    # A later turn fails; its control-path fallback reuses the inbound
    # message's metadata (role_id/thread_id/session_key_override) but was
    # never persisted, so it carries no committed_message_id.
    fallback = OutboundMessage(
        channel="telegram",
        chat_id="123",
        content="处理消息时出错，请稍后再试。",
        metadata={
            "role_id": "mira",
            "session_key_override": "role:mira",
            "thread_id": thread_id,
        },
    )

    result = hub.mark_delivery(
        fallback,
        default_channel="telegram",
        delivery_status="sent",
        external_message_id="tg-inbound-id",
    )

    assert result is None
    after = session_manager._store.get_message(unrelated_message_id)
    assert after is not None
    assert after["delivery_status"] == "sent"
    assert after["external_message_id"] == "tg-earlier"


def test_channel_hub_skips_delivery_mark_without_running_thread_validation(
    tmp_path: Path,
) -> None:
    """The missing-committed-id early return must run before any thread checks.

    A channel outbound's ``finally`` block calls ``mark_delivery`` unguarded by
    a ``try``, so a ``ValueError`` raised from thread validation would escape
    straight out of the send path. A fallback message with no
    ``committed_message_id`` has nothing to mark regardless of whether its
    metadata even carries a usable thread_id, so it must return ``None``
    quietly instead of ever reaching those validations.
    """
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
    _ = service.bindings.bind("telegram", "123", role.id, contact_id="u1")
    hub = ChannelHub(service)

    # No committed_message_id and no thread_id metadata at all: a full-blown
    # thread validation would raise ValueError("出站消息缺少 thread_id"), but
    # since there is nothing to mark, mark_delivery must short-circuit first.
    result = hub.mark_delivery(
        OutboundMessage(
            channel="telegram",
            chat_id="123",
            content="处理消息时出错，请稍后再试。",
            metadata={"role_id": role.id},
        ),
        default_channel="telegram",
        delivery_status="sent",
    )

    assert result is None


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
    _ = service.bindings.bind("telegram", "123", role.id, contact_id="u1")
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


def test_channel_hub_resolves_control_actions_to_role_session(tmp_path: Path) -> None:
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
    _ = service.bindings.bind("telegram", "123", "mira", contact_id="u1")
    hub = ChannelHub(service)
    _ = hub.route_inbound(
        InboundMessage(
            channel="telegram",
            sender="u1",
            chat_id="123",
            content="hello",
        )
    )

    assert hub.resolve_runtime_session_key("telegram", "123") == "role:mira"


def test_channel_hub_rejects_unbound_control_actions(tmp_path: Path) -> None:
    session_manager = SessionManager(tmp_path)
    service = RoleAggregateService.from_runtime(
        workspace=tmp_path,
        role_store=RoleStore(tmp_path),
        session_manager=session_manager,
    )

    with pytest.raises(KeyError):
        ChannelHub(service).resolve_runtime_session_key("telegram", "123")


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
    _ = service.bindings.bind("telegram", "123", "mira", contact_id="u1")

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
    assert routed.session_key == "role:mira"
    assert routed.metadata["thread_id"] == "thread:mira:telegram:123"
    assert routed.metadata["role_config_version"]
    assert routed.metadata["request_id"] == "message-1"
    assert routed.metadata["delivery_key"]
    assert routed.metadata["role_work_kind"] == "passive_turn"


def test_channel_hub_only_authorizes_the_configured_contact(tmp_path: Path) -> None:
    service = RoleAggregateService.from_runtime(
        workspace=tmp_path,
        role_store=RoleStore(tmp_path),
        session_manager=SessionManager(tmp_path),
    )
    _ = service.create_role(role_id="mira", name="Mira", system_prompt="you are mira")
    _ = service.bindings.bind("telegram", "123", "mira", contact_id="owner")
    hub = ChannelHub(service)

    assert hub.is_sender_allowed(channel="telegram", chat_id="123", sender_id="owner")
    assert not hub.is_sender_allowed(
        channel="telegram", chat_id="123", sender_id="other"
    )
