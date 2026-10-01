"""runtime_context.py 行为：capability 授予门控与自定义 effect 登记。"""

from __future__ import annotations

from pathlib import Path
from shiori_sdk.testing import FakeEvents
from shiori_sdk.runtime import EventsCapability

import pytest

from agent.plugin_host.effects import EffectScope
from agent.plugin_host.manifest import PluginManifest
from agent.plugin_host.runtime_context import (
    CapabilityNotGranted,
    PluginRuntimeContext,
)


def _make_context(
    capabilities: dict[str, object],
    *,
    effects: EffectScope | None = None,
    events: EventsCapability | None = None,
) -> PluginRuntimeContext:
    scope = effects or EffectScope("demo")
    return PluginRuntimeContext(
        plugin_id="demo",
        plugin_dir=Path("plugins/demo"),
        manifest=PluginManifest(id="demo", capabilities=tuple(capabilities)),
        effects=scope,
        capabilities=capabilities,
        events=events,
    )


def test_granted_capability_is_accessible():
    sentinel = FakeEvents()
    context = _make_context({"events": sentinel}, events=sentinel)
    # 属性访问必须拿到宿主注入的同一实例，而不是替身
    assert context.events is sentinel


def test_ungranted_capability_raises_with_diagnostic():
    context = _make_context({"events": object()})
    with pytest.raises(CapabilityNotGranted) as excinfo:
        _ = context.tools
    message = str(excinfo.value)
    assert "tools" in message
    assert "demo" in message
    # 诊断信息要列出已授予能力，便于插件作者修 manifest
    assert "events" in message


def test_capability_not_granted_is_attribute_error():
    """getattr 默认值等惯用法依赖 AttributeError 子类语义。"""
    context = _make_context({})
    assert issubclass(CapabilityNotGranted, AttributeError)
    assert getattr(context, "tools", "fallback") == "fallback"


def test_granted_reports_sorted_capability_names():
    context = _make_context({"kv": object(), "events": object()})
    assert context.granted == ("events", "kv")


def test_identity_fields_exposed():
    context = _make_context({})
    assert context.plugin_id == "demo"
    assert context.plugin_dir == Path("plugins/demo")
    assert context.manifest.id == "demo"


@pytest.mark.asyncio
async def test_effect_registration_disposed_with_scope():
    scope = EffectScope("demo")
    context = _make_context({}, effects=scope)
    closed: list[str] = []

    context.effect("connection", lambda: closed.append("closed"))
    assert closed == []
    assert scope.labels == ["custom:connection"]

    _ = await scope.dispose_all()
    assert closed == ["closed"]


@pytest.mark.asyncio
async def test_async_effect_is_awaited():
    scope = EffectScope("demo")
    context = _make_context({}, effects=scope)
    closed: list[str] = []

    async def close() -> None:
        closed.append("async-closed")

    context.effect("async-connection", close)
    _ = await scope.dispose_all()
    assert closed == ["async-closed"]
