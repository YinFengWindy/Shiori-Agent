"""In-generation reload: closure, call draining, process resources and rollback."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import ModuleType

import pytest
from shiori_sdk.rpc import PluginRpcError

from agent.plugin_host import (
    HostServices,
    PluginKernel,
    PluginReloadFailed,
    PluginReloadUnsupported,
    PluginState,
)
from agent.plugin_host.process_resources import ProcessResourceOwner
from agent.tools.registry import ToolRegistry
from bus.event_bus import EventBus

_PROVIDER = """
import sys
from shiori_sdk.tools import Tool

probe = sys.modules["reload_probe"]


class Slow(Tool):
    name = "provider_slow"
    description = "waits for the test"
    parameters = {"type": "object", "properties": {}}

    def __init__(self, label):
        self.label = label

    async def execute(self, **kwargs):
        probe.events.append(("call-start", self.label))
        await probe.release.wait()
        probe.events.append(("call-end", self.label))
        return self.label


async def setup(ctx):
    label = ctx.config.get("label")
    if label == "broken":
        raise RuntimeError("broken config")
    probe.events.append(
        ("setup", "provider", label, ctx.runtime.was_active, ctx.runtime.is_reload)
    )
    probe.resources.append(ctx.process_resources.acquire("shared-v1", probe.Resource))
    tool = Slow(label)
    ctx.tools.register(tool)

    async def echo(payload):
        return {"label": label}

    ctx.rpc.register("echo", echo)
    ctx.services.register(
        "labels", contract="labels-v1", label="Labels", methods={"echo": echo}
    )

    async def drain():
        probe.events.append(("drain", "provider", label))

    ctx.runtime.on_drain(drain)
    ctx.effect("dispose", lambda: probe.events.append(("dispose", "provider", label)))
    ctx.expose(tool)
"""

_CONSUMER = """
import sys

probe = sys.modules["reload_probe"]


async def setup(ctx):
    provider = ctx.dependencies.require("provider")
    probe.events.append(("setup", "consumer", provider.label, ctx.runtime.was_active))
    ctx.effect("dispose", lambda: probe.events.append(("dispose", "consumer")))
    ctx.expose({"provider": provider})
"""

_BYSTANDER = """
import sys

probe = sys.modules["reload_probe"]


async def setup(ctx):
    probe.events.append(("setup", "bystander"))
    ctx.effect("dispose", lambda: probe.events.append(("dispose", "bystander")))
"""


class _Resource:
    def __init__(self) -> None:
        self.closed = 0

    async def close(self) -> None:
        self.closed += 1


def _write(root: Path, plugin_id: str, manifest: str, source: str) -> None:
    package = root / plugin_id
    (package / "backend").mkdir(parents=True)
    (package / "manifest.yaml").write_text(
        f"api: 2\nid: {plugin_id}\n{manifest}", encoding="utf-8"
    )
    (package / "backend/plugin.py").write_text(source, encoding="utf-8")


@pytest.fixture
def probe(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    module = ModuleType("reload_probe")
    module.events = []
    module.resources = []
    module.release = asyncio.Event()
    module.Resource = _Resource
    monkeypatch.setitem(sys.modules, "reload_probe", module)
    return module


async def _kernel(
    tmp_path: Path, *, consumer_capabilities: str = "", consumer_manifest: str = ""
) -> tuple[PluginKernel, HostServices, ToolRegistry]:
    _write(
        tmp_path,
        "provider",
        "capabilities: [tools, rpc, services, process_resources, config, runtime]\n",
        _PROVIDER,
    )
    _write(
        tmp_path,
        "consumer",
        f"capabilities: [dependencies, runtime, {consumer_capabilities}]\n"
        f"dependencies: [provider]\n{consumer_manifest}",
        _CONSUMER,
    )
    _write(tmp_path, "bystander", "capabilities: []\n", _BYSTANDER)
    tools = ToolRegistry()
    services = HostServices(
        event_bus=EventBus(),
        tool_registry=tools,
        workspace=tmp_path / "workspace",
        plugin_configs={"provider": {"label": "v1"}},
        raw_plugin_configs={"provider": {"label": "v1"}},
        process_resources=ProcessResourceOwner(),
    )
    kernel = PluginKernel([tmp_path], services=services)
    await kernel.load_all()
    kernel.publish_process_resources()
    return kernel, services, tools


@pytest.mark.asyncio
async def test_reload_reruns_only_the_closure_with_new_config(probe, tmp_path):
    kernel, services, _ = await _kernel(tmp_path)
    probe.events.clear()

    result = await kernel.reload(
        "provider", values={"label": "v2"}, raw_values={"label": "v2"}
    )

    assert result.plugin_ids == ("provider", "consumer")
    assert result.cleanup_errors == ()
    # Dependents retire first and come back after the new provider;
    # the reloaded instances see the reload, and the bystander is untouched.
    assert probe.events == [
        ("dispose", "consumer"),
        ("drain", "provider", "v1"),
        ("dispose", "provider", "v1"),
        ("setup", "provider", "v2", True, True),
        ("setup", "consumer", "v2", True),
    ]
    new_provider = kernel._dependency_api("provider")
    assert kernel._dependency_api("consumer")["provider"] is new_provider
    assert services.plugin_configs["provider"] == {"label": "v2"}
    assert services.raw_plugin_configs["provider"] == {"label": "v2"}
    # The shared process resource is the same object and was never closed.
    assert probe.resources[0] is probe.resources[1]
    assert probe.resources[0].closed == 0
    await kernel.terminate_all(force=True)


@pytest.mark.asyncio
async def test_reload_waits_for_in_flight_calls_and_rejects_new_ones(probe, tmp_path):
    kernel, _, tools = await _kernel(tmp_path)
    old_tool = tools.get_tool("provider_slow")
    resolved = kernel.rpc.resolve("plugin.provider.echo")
    assert old_tool is not None and resolved is not None
    old_rpc = resolved[1]
    in_flight = asyncio.create_task(tools.execute("provider_slow", {}))
    while ("call-start", "v1") not in probe.events:
        await asyncio.sleep(0)

    reload = asyncio.create_task(
        kernel.reload("provider", values={"label": "v2"}, raw_values={"label": "v2"})
    )
    for _ in range(20):
        await asyncio.sleep(0)
    # Draining: the old instance is still set up while its call runs, but no
    # new call reaches it through any route.
    assert not reload.done()
    assert ("dispose", "provider", "v1") not in probe.events
    with pytest.raises(PluginRpcError, match="正在重载"):
        await asyncio.wait_for(old_tool.execute(), 1)
    with pytest.raises(PluginRpcError, match="正在重载"):
        await old_rpc({})
    with pytest.raises(PluginRpcError) as service:
        await kernel.rpc.services.call(
            "provider", "labels", "echo", {}, caller_active=lambda: True
        )
    assert service.value.code == "plugin_unavailable"

    probe.release.set()
    assert await in_flight == "v1"
    await reload
    assert probe.events.index(("call-end", "v1")) < probe.events.index(
        ("drain", "provider", "v1")
    )
    assert await tools.execute("provider_slow", {}) == "v2"
    assert await kernel.rpc.services.call(
        "provider", "labels", "echo", {}, caller_active=lambda: True
    ) == {"label": "v2"}
    await kernel.terminate_all(force=True)


@pytest.mark.asyncio
async def test_failed_reload_restores_the_old_config_instance(probe, tmp_path):
    kernel, services, tools = await _kernel(tmp_path)
    old_tables = services.plugin_configs["provider"]
    probe.events.clear()

    with pytest.raises(PluginReloadFailed) as caught:
        await kernel.reload(
            "provider", values={"label": "broken"}, raw_values={"label": "broken"}
        )

    assert caught.value.failed == ("provider", "consumer")
    assert caught.value.restore_failed == ()
    assert str(caught.value.__cause__) == "broken config"
    assert services.plugin_configs["provider"] is old_tables
    assert services.raw_plugin_configs["provider"] == {"label": "v1"}
    states = {row["id"]: row["state"] for row in kernel.states()}
    assert states == {"provider": "ACTIVE", "consumer": "ACTIVE", "bystander": "ACTIVE"}
    assert ("setup", "provider", "v1", True, True) in probe.events
    assert ("setup", "bystander") not in probe.events
    assert kernel._dependency_api("consumer")["provider"].label == "v1"
    probe.release.set()
    assert await tools.execute("provider_slow", {}) == "v1"
    # Every attempt re-acquired the one resource; none closed it.
    assert {id(resource) for resource in probe.resources} == {id(probe.resources[0])}
    assert probe.resources[0].closed == 0
    await kernel.terminate_all(force=True)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("consumer_manifest", "reason"),
    [
        (
            "channels:\n  - {name: relay, label: Relay, chat_types:"
            " [{type: private, label: Private, chat_id_label: ID}]}\n",
            "channels",
        ),
        ("supports_hot_unload: false\n", "hot_unload"),
    ],
)
async def test_reload_refuses_generation_only_closures_before_any_change(
    probe, tmp_path, consumer_manifest, reason
):
    kernel, services, _ = await _kernel(
        tmp_path,
        consumer_capabilities="channels" if reason == "channels" else "",
        consumer_manifest=consumer_manifest,
    )
    probe.events.clear()

    with pytest.raises(PluginReloadUnsupported) as caught:
        await kernel.reload(
            "provider", values={"label": "v2"}, raw_values={"label": "v2"}
        )

    assert caught.value.reason == reason
    assert caught.value.plugin_ids == ("consumer",)
    assert probe.events == []
    assert services.plugin_configs["provider"] == {"label": "v1"}
    assert all(row["state"] == PluginState.ACTIVE.name for row in kernel.states())
    await kernel.terminate_all(force=True)
