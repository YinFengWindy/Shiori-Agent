"""Contract fakes exercise setup, capability gates and cleanup without host storage."""

import pytest

from shiori_sdk import CapabilityNotGranted, PluginRuntimeContext
from shiori_sdk.testing import FakePluginContext


async def test_sdk_fixture_is_a_usable_setup_context(
    sdk_context: FakePluginContext,
) -> None:
    context: PluginRuntimeContext = sdk_context
    api = object()
    context.expose(api)
    assert sdk_context.exported is api
    assert sdk_context.plugin_dir.is_dir()


async def test_cleanup_is_lifo_stops_events_first_and_rejects_cached_registrations() -> (
    None
):
    context = FakePluginContext()
    events, lifecycle = context.events, context.lifecycle
    seen: list[str] = []

    def handler(event: str) -> None:
        seen.append(event)

    events.on(str, handler)
    context.effect("first", lambda: seen.append("first"))

    async def close() -> None:
        await events.emit("must not be delivered")
        seen.append("second")

    context.effect("second", close)
    await context.aclose()
    assert seen == ["second", "first"]
    with pytest.raises(RuntimeError, match="closed"):
        events.on(str, handler)
    with pytest.raises(RuntimeError, match="closed"):
        lifecycle.contribute("after_step", [])
    with pytest.raises(RuntimeError, match="closed"):
        context.effect("late", lambda: None)
    await context.aclose()
    assert seen == ["second", "first"]


async def test_cleanup_continues_after_a_failure() -> None:
    context = FakePluginContext()
    seen: list[str] = []
    context.effect("first", lambda: seen.append("first"))

    def fail() -> None:
        raise ValueError("cleanup failed")

    context.effect("failure", fail)
    with pytest.raises(ExceptionGroup, match="Plugin cleanup failed"):
        await context.aclose()
    assert seen == ["first"]


def test_only_requested_capabilities_are_accessible() -> None:
    context = FakePluginContext(capabilities=("lifecycle",))
    assert context.granted == ("lifecycle",)
    with pytest.raises(CapabilityNotGranted, match="events"):
        _ = context.events
    with pytest.raises(ValueError, match="Unsupported"):
        FakePluginContext(capabilities=("host_storage",))
