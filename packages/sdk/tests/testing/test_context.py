"""Contract fakes exercise setup, capability gates and cleanup without host storage."""

from pathlib import Path

import pytest

from shiori_sdk import CapabilityNotGranted, PluginRuntimeContext
from shiori_sdk.testing import FakePluginContext


@pytest.fixture
def sdk_plugin_dir(tmp_path: Path) -> Path:
    package = tmp_path / "package"
    package.mkdir()
    (package / "manifest.yaml").write_text(
        "id: probe\ncapabilities:\n  - lifecycle\n", encoding="utf-8"
    )
    return package


async def test_sdk_fixture_is_a_usable_setup_context(
    sdk_context: FakePluginContext, sdk_plugin_dir: Path
) -> None:
    context: PluginRuntimeContext = sdk_context
    api = object()
    context.expose(api)
    assert sdk_context.exported is api
    # The manifest is only read; setup writes land in an isolated directory.
    assert sdk_context.plugin_dir.is_dir()
    assert sdk_context.plugin_dir != sdk_plugin_dir
    assert not (sdk_context.plugin_dir / "manifest.yaml").exists()


async def test_sdk_fixture_grants_only_manifest_capabilities(
    sdk_context: FakePluginContext,
) -> None:
    assert sdk_context.plugin_id == "probe"
    assert sdk_context.granted == ("lifecycle",)
    _ = sdk_context.lifecycle
    with pytest.raises(
        CapabilityNotGranted, match="插件 probe 未声明 capability 'events'"
    ):
        _ = sdk_context.events


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
    context = FakePluginContext(capabilities=("rpc", "lifecycle"))
    assert context.granted == ("lifecycle", "rpc")
    _ = context.lifecycle
    with pytest.raises(CapabilityNotGranted, match="events"):
        _ = context.events


def test_unknown_capability_names_are_rejected_like_the_host() -> None:
    with pytest.raises(
        ValueError, match=r"manifest 声明了未知 capability \['host_storage'\]"
    ):
        FakePluginContext(capabilities=("lifecycle", "host_storage"))
