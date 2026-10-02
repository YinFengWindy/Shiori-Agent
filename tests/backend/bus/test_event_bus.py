import pytest

from shiori_sdk.event_binding import EventBinding
from bus.event_bus import EventBus


@pytest.mark.asyncio
async def test_mixed_bindings_remove_captured_bound_methods_and_can_rebind():
    seen = []

    class Receiver:
        def text(self, event: str) -> None:
            seen.append(event)

        def number(self, event: int) -> None:
            seen.append(event)

    receiver = Receiver()
    bindings = (EventBinding(str, receiver.text), EventBinding(int, receiver.number))
    bus = EventBus()
    try:
        for binding in bindings:
            binding.bind(bus)
        await bus.emit("first")
        await bus.emit(1)
        for binding in bindings:
            binding.unbind(bus)
        await bus.emit("detached")
        await bus.emit(2)
        assert seen == ["first", 1]
        for binding in bindings:
            binding.bind(bus)
        await bus.emit("restored")
        assert seen == ["first", 1, "restored"]
    finally:
        await bus.aclose()
