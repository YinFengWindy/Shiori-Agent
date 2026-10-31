"""Host-owned pushes announce the text they stored."""

from __future__ import annotations

from bus.event_bus import EventBus
from bus.events_lifecycle import ExternalTextPushed, InitiatedMessageCommitted
from conversation.push_sync import ExternalPushSyncService
from session.manager import SessionManager


class _Drafts:
    def __init__(self) -> None:
        self.items: list[object] = []

    def append(self, message, *, owner, if_abandoned=None) -> None:
        del owner, if_abandoned
        self.items.append(message)


def _push(**overrides) -> ExternalTextPushed:
    fields = {
        "session_key": "telegram:cats",
        "role_id": "mira",
        "channel": "telegram",
        "chat_id": "cats",
        "text": "带伞",
        "tool": "account_send",
    }
    fields.update(overrides)
    return ExternalTextPushed(**fields)


async def test_host_owned_push_fills_the_committed_event(tmp_path) -> None:
    manager = SessionManager(tmp_path)
    bus = EventBus()
    events: list[InitiatedMessageCommitted] = []
    bus.on(InitiatedMessageCommitted, events.append)
    ExternalPushSyncService(
        session_manager=manager,
        event_bus=bus,
        live_turn_pushes=lambda _session_key: None,
    )
    try:
        await bus.fanout(_push())
    finally:
        await bus.aclose()
    rows = manager._store.fetch_session_messages(manager.role_session_key("mira"))
    assert len(events) == 1
    event = events[0]
    assert event.assistant_response == "带伞"
    assert event.chat_id == "cats"
    assert event.source == "push"
    assert event.tools_used == ("account_send",)
    assert event.message_id == rows[0]["id"]


async def test_in_turn_push_is_not_announced_immediately(tmp_path) -> None:
    manager = SessionManager(tmp_path)
    bus = EventBus()
    events: list[InitiatedMessageCommitted] = []
    bus.on(InitiatedMessageCommitted, events.append)
    drafts = _Drafts()
    ExternalPushSyncService(
        session_manager=manager,
        event_bus=bus,
        live_turn_pushes=lambda _session_key: drafts,
    )
    try:
        await bus.fanout(_push(in_turn=True))
    finally:
        await bus.aclose()
    assert events == []
    assert len(drafts.items) == 1
    assert manager._store.fetch_session_messages(manager.role_session_key("mira")) == []
