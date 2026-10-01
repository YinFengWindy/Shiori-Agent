"""The standalone event fake preserves the public bus dispatch behavior."""

from dataclasses import dataclass, replace

from shiori_sdk.testing import FakeEvents


@dataclass
class Event:
    value: int


@dataclass
class ChildEvent(Event):
    pass


async def test_events_use_exact_type_and_ordered_replacement_then_unsubscribe() -> None:
    events = FakeEvents()
    seen: list[int] = []

    async def increment(event: Event) -> Event:
        return replace(event, value=event.value + 1)

    def record(event: Event) -> None:
        seen.append(event.value)

    events.on(Event, increment)
    events.on(Event, record)
    assert await events.emit(Event(1)) == Event(2)
    assert await events.emit(ChildEvent(1)) == ChildEvent(1)
    assert seen == [2]
    events.off(Event, increment)
    assert await events.emit(Event(5)) == Event(5)
    assert seen == [2, 5]
