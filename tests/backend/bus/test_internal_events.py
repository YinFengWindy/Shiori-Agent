from dataclasses import dataclass, field

import pytest

from bus.event_bus import EventBus


@dataclass
class _FakeLifecycleEvent:
    session_key: str
    channel: str
    chat_id: str
    content: str
    thinking: str | None = None
    media: list[str] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)


@pytest.mark.asyncio
async def test_event_bus_observe_and_intercept_are_ordered():
    event_bus = EventBus()
    observed: list[str] = []

    event_bus.on(
        _FakeLifecycleEvent,
        lambda event: observed.append(event.content),
    )
    event_bus.on(
        _FakeLifecycleEvent,
        lambda event: _FakeLifecycleEvent(
            session_key=event.session_key,
            channel=event.channel,
            chat_id=event.chat_id,
            content=event.content + "!",
            thinking=event.thinking,
            media=list(event.media),
            metadata=dict(event.metadata),
        ),
    )

    await event_bus.observe(
        _FakeLifecycleEvent(
            session_key="telegram:123",
            channel="telegram",
            chat_id="123",
            content="ok",
        )
    )
    dispatch = await event_bus.emit(
        _FakeLifecycleEvent(
            session_key="telegram:123", channel="telegram", chat_id="123", content="ok"
        )
    )

    assert observed == ["ok", "ok"]
    assert dispatch.content == "ok!"


@pytest.mark.asyncio
async def test_event_bus_fanout_keeps_other_observers_when_one_fails(caplog):
    event_bus = EventBus()
    observed: list[str] = []

    def _bad(_event: _FakeLifecycleEvent) -> None:
        raise RuntimeError("boom")

    event_bus.on(_FakeLifecycleEvent, _bad)
    event_bus.on(_FakeLifecycleEvent, lambda event: observed.append(event.content))

    await event_bus.fanout(
        _FakeLifecycleEvent(
            session_key="telegram:123",
            channel="telegram",
            chat_id="123",
            content="ok",
        )
    )

    assert observed == ["ok"]
    assert "fanout completed with observer errors" in caplog.text


@pytest.mark.asyncio
async def test_event_bus_enqueue_runs_observers_in_background():
    event_bus = EventBus()
    observed: list[str] = []

    event_bus.on(_FakeLifecycleEvent, lambda event: observed.append(event.content))
    event_bus.enqueue(
        _FakeLifecycleEvent(
            session_key="telegram:123",
            channel="telegram",
            chat_id="123",
            content="ok",
        )
    )
    await event_bus.drain()

    assert observed == ["ok"]
    await event_bus.aclose()
