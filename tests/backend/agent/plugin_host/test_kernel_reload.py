"""In-generation reload: closure, call draining, cancellation and rollback."""

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
    PluginReloadTimeout,
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
    if label == "slow-setup":
        probe.events.append(("setup-waiting",))
        await probe.setup_gate.wait()
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
from shiori_sdk.tools import Tool

probe = sys.modules["reload_probe"]


class Relay(Tool):
    name = "consumer_relay"
    description = "calls the provider once the test lets it"
    parameters = {"type": "object", "properties": {}}

    def __init__(self, provider):
        self.provider = provider

    async def execute(self, **kwargs):
        probe.events.append(("relay-start",))
        await probe.relay_gate.wait()
        return await self.provider.execute()


async def setup(ctx):
    provider = ctx.dependencies.require("provider")
    ctx.tools.register(Relay(provider))
    probe.events.append(
        (
            "setup",
            "consumer",
            provider.label,
            ctx.runtime.was_active,
            ctx.runtime.is_reload,
        )
    )

    async def drain():
        probe.events.append(("drain", "consumer"))

    ctx.runtime.on_drain(drain)
    ctx.effect("dispose", lambda: probe.events.append(("dispose", "consumer")))
    ctx.expose({"provider": provider})
"""

_BYSTANDER = """
import sys
from shiori_sdk.tools import Tool

probe = sys.modules["reload_probe"]


class Busy(Tool):
    name = "bystander_busy"
    description = "waits for the test"
    parameters = {"type": "object", "properties": {}}

    async def execute(self, **kwargs):
        await probe.bystander_release.wait()
        return "bystander"


async def setup(ctx):
    probe.events.append(("setup", "bystander"))
    ctx.tools.register(Busy())
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
    module.bystander_release = asyncio.Event()
    module.setup_gate = asyncio.Event()
    module.relay_gate = asyncio.Event()
    module.Resource = _Resource
    monkeypatch.setitem(sys.modules, "reload_probe", module)
    return module


async def _kernel(
    tmp_path: Path,
    *,
    consumer_capabilities: str = "",
    consumer_manifest: str = "",
    configs: dict[str, dict] | None = None,
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
        f"capabilities: [dependencies, runtime, tools, {consumer_capabilities}]\n"
        f"dependencies: [provider]\n{consumer_manifest}",
        _CONSUMER,
    )
    _write(tmp_path, "bystander", "capabilities: [tools]\n", _BYSTANDER)
    tools = ToolRegistry()
    configs = configs or {"provider": {"label": "v1"}}
    services = HostServices(
        event_bus=EventBus(),
        tool_registry=tools,
        workspace=tmp_path / "workspace",
        plugin_configs=configs,
        raw_plugin_configs={key: dict(value) for key, value in configs.items()},
        process_resources=ProcessResourceOwner(),
    )
    kernel = PluginKernel([tmp_path], services=services)
    await kernel.load_all()
    kernel.publish_process_resources()
    return kernel, services, tools


def _reload(kernel: PluginKernel, label: str, timeout: float = 5):
    return kernel.reload(
        "provider",
        values={"label": label},
        raw_values={"label": label},
        drain_timeout=timeout,
    )


async def _until(probe: ModuleType, event: tuple) -> None:
    async with asyncio.timeout(1):
        while event not in probe.events:
            await asyncio.sleep(0)


async def _echo(kernel: PluginKernel) -> dict[str, object] | None:
    resolved = kernel.rpc.resolve("plugin.provider.echo")
    assert resolved is not None
    return await resolved[1]({})


@pytest.mark.asyncio
async def test_reload_reruns_only_the_closure_with_new_config(probe, tmp_path):
    kernel, services, _ = await _kernel(tmp_path)
    probe.events.clear()

    result = await _reload(kernel, "v2")

    assert result.plugin_ids == ("provider", "consumer")
    assert result.cleanup_errors == ()
    # Dependents drain and retire first and come back after the new provider;
    # the reloaded instances see the reload, and the bystander is untouched.
    assert probe.events == [
        ("drain", "consumer"),
        ("drain", "provider", "v1"),
        ("dispose", "consumer"),
        ("dispose", "provider", "v1"),
        ("setup", "provider", "v2", True, True),
        ("setup", "consumer", "v2", True, True),
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
async def test_reload_waits_for_closure_calls_only_and_rejects_new_ones(
    probe, tmp_path
):
    kernel, _, tools = await _kernel(tmp_path)
    old_tool = tools.get_tool("provider_slow")
    resolved = kernel.rpc.resolve("plugin.provider.echo")
    assert old_tool is not None and resolved is not None
    old_rpc = resolved[1]
    bystander = asyncio.create_task(tools.execute("bystander_busy", {}))
    in_flight = asyncio.create_task(tools.execute("provider_slow", {}))
    await _until(probe, ("call-start", "v1"))

    reload = asyncio.create_task(_reload(kernel, "v2"))
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
    await asyncio.wait_for(reload, 1)
    # The bystander call outside the closure was never waited for.
    assert not bystander.done()
    assert probe.events.index(("call-end", "v1")) < probe.events.index(
        ("drain", "provider", "v1")
    )
    assert await tools.execute("provider_slow", {}) == "v2"
    assert await kernel.rpc.services.call(
        "provider", "labels", "echo", {}, caller_active=lambda: True
    ) == {"label": "v2"}
    probe.bystander_release.set()
    assert await bystander == "bystander"
    await kernel.terminate_all(force=True)


@pytest.mark.asyncio
async def test_dependent_in_flight_work_can_still_call_its_provider_while_draining(
    probe, tmp_path
):
    kernel, _, tools = await _kernel(tmp_path)
    probe.release.set()
    relay = asyncio.create_task(tools.execute("consumer_relay", {}))
    await _until(probe, ("relay-start",))
    reload = asyncio.create_task(_reload(kernel, "v2"))
    for _ in range(20):
        await asyncio.sleep(0)
    assert not reload.done()

    # The dependent drains first; its provider still admits the dependent's call.
    probe.relay_gate.set()
    assert await relay == "v1"
    result = await asyncio.wait_for(reload, 1)
    assert result.plugin_ids == ("provider", "consumer")
    assert await tools.execute("consumer_relay", {}) == "v2"
    await kernel.terminate_all(force=True)


@pytest.mark.asyncio
async def test_drain_timeout_abandons_the_reload_unchanged(probe, tmp_path):
    kernel, services, tools = await _kernel(tmp_path)
    in_flight = asyncio.create_task(tools.execute("provider_slow", {}))
    await _until(probe, ("call-start", "v1"))

    with pytest.raises(PluginReloadTimeout) as caught:
        await _reload(kernel, "v2", timeout=0.05)

    assert caught.value.busy == ("provider",)
    # The dependent stage drained; the provider stage timed out; nothing left.
    assert ("drain", "provider", "v1") not in probe.events
    assert not any(event[0] == "dispose" for event in probe.events)
    # The sealed dependent was reopened and admits calls again.
    relay = asyncio.create_task(tools.execute("consumer_relay", {}))
    await _until(probe, ("relay-start",))
    probe.relay_gate.set()
    assert services.plugin_configs["provider"] == {"label": "v1"}
    assert await _echo(kernel) == {"label": "v1"}
    probe.release.set()
    assert await in_flight == "v1"
    assert await relay == "v1"
    await kernel.terminate_all(force=True)


@pytest.mark.asyncio
async def test_cancelling_the_caller_while_draining_reopens_the_old_instance(
    probe, tmp_path
):
    kernel, services, tools = await _kernel(tmp_path)
    in_flight = asyncio.create_task(tools.execute("provider_slow", {}))
    await _until(probe, ("call-start", "v1"))
    reload = asyncio.create_task(_reload(kernel, "v2"))
    for _ in range(20):
        await asyncio.sleep(0)

    reload.cancel()
    with pytest.raises(asyncio.CancelledError):
        await reload

    assert await _echo(kernel) == {"label": "v1"}
    assert services.plugin_configs["provider"] == {"label": "v1"}
    probe.release.set()
    assert await in_flight == "v1"
    assert not any(event[0] == "dispose" for event in probe.events)
    await kernel.terminate_all(force=True)


@pytest.mark.asyncio
async def test_cancelling_the_caller_during_setup_completes_the_reload(probe, tmp_path):
    kernel, services, _ = await _kernel(tmp_path)
    reload = asyncio.create_task(_reload(kernel, "slow-setup"))
    await _until(probe, ("setup-waiting",))

    reload.cancel()
    for _ in range(5):
        await asyncio.sleep(0)
    probe.setup_gate.set()
    with pytest.raises(asyncio.CancelledError):
        await reload

    states = {row["id"]: row["state"] for row in kernel.states()}
    assert states == {"provider": "ACTIVE", "consumer": "ACTIVE", "bystander": "ACTIVE"}
    assert services.plugin_configs["provider"] == {"label": "slow-setup"}
    assert await _echo(kernel) == {"label": "slow-setup"}
    assert probe.resources[0] is probe.resources[-1]
    assert probe.resources[0].closed == 0
    # The transition lock was released only after completion.
    assert (await _reload(kernel, "v3")).plugin_ids == ("provider", "consumer")
    await kernel.terminate_all(force=True)


@pytest.mark.asyncio
async def test_failed_reload_restores_the_old_config_instance(probe, tmp_path):
    kernel, services, tools = await _kernel(tmp_path)
    old_tables = services.plugin_configs["provider"]
    probe.events.clear()

    with pytest.raises(PluginReloadFailed) as caught:
        await _reload(kernel, "broken")

    assert list(caught.value.failed) == ["provider", "consumer"]
    assert caught.value.__cause__ is caught.value.failed["provider"]
    assert str(caught.value.__cause__) == "broken config"
    assert caught.value.restore_failed == {}
    assert caught.value.cleanup_errors == ()
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
        await _reload(kernel, "v2")

    assert caught.value.reason == reason
    assert caught.value.plugin_ids == ("consumer",)
    assert probe.events == []
    assert services.plugin_configs["provider"] == {"label": "v1"}
    assert all(row["state"] == PluginState.ACTIVE.name for row in kernel.states())
    await kernel.terminate_all(force=True)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("config", "reason"),
    [({"label": "v1", "enabled": False}, "disabled"), ({"label": "broken"}, "failed")],
)
async def test_reload_refuses_an_inactive_target_by_state(
    probe, tmp_path, config, reason
):
    kernel, services, _ = await _kernel(tmp_path, configs={"provider": config})

    with pytest.raises(PluginReloadUnsupported) as caught:
        await _reload(kernel, "v2")

    assert caught.value.reason == reason
    assert services.plugin_configs["provider"] == config
    await kernel.terminate_all(force=True)


@pytest.mark.asyncio
async def test_reload_values_cannot_disable_the_target(probe, tmp_path):
    kernel, services, _ = await _kernel(tmp_path)
    probe.events.clear()

    with pytest.raises(ValueError, match="停用"):
        await kernel.reload(
            "provider",
            values={"label": "v2", "enabled": False},
            raw_values={"label": "v2", "enabled": False},
            drain_timeout=5,
        )

    assert probe.events == []
    assert services.plugin_configs["provider"] == {"label": "v1"}
    await kernel.terminate_all(force=True)


@pytest.mark.asyncio
async def test_terminate_waits_for_a_reload_and_later_reloads_are_refused(
    probe, tmp_path
):
    kernel, _, tools = await _kernel(tmp_path)
    in_flight = asyncio.create_task(tools.execute("provider_slow", {}))
    await _until(probe, ("call-start", "v1"))
    reload = asyncio.create_task(_reload(kernel, "v2"))
    for _ in range(5):
        await asyncio.sleep(0)
    terminate = asyncio.create_task(kernel.terminate_all(force=True))
    for _ in range(20):
        await asyncio.sleep(0)
    assert ("dispose", "bystander") not in probe.events

    probe.release.set()
    await in_flight
    await reload
    await terminate
    # Retirement ran after the reload finished, never interleaved with it.
    assert probe.events.index(("setup", "consumer", "v2", True, True)) < (
        probe.events.index(("dispose", "bystander"))
    )
    with pytest.raises(PluginReloadUnsupported) as caught:
        await _reload(kernel, "v3")
    assert caught.value.reason == "retired"
