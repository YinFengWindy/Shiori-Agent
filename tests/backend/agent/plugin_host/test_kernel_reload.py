"""In-generation reload: closure, call draining, cancellation and rollback."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from shiori_sdk.core.conversation import StepStarting
from shiori_sdk.kernel import KernelState, PluginFailed
from shiori_sdk.rpc import PluginRpcError

from agent.plugin_host import (
    PluginGenerationSettings,
    PluginKernel,
    PluginRpcRegistry,
    PluginReloadFailed,
    PluginReloadTimeout,
    PluginReloadUnsupported,
    PluginState,
)
from tests.support.plugin_kernel import host_kernel
from infra.process.resources import ProcessResourceOwner
from agent.tools.registry import ToolRegistry
from bus.event_bus import EventBus

_PROVIDER = """
import sys
from shiori_sdk.core.services import (
    CONFIG,
    PROCESS_RESOURCES,
    RPC,
    RUNTIME,
    SERVICES,
    TOOLS,
)
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
    runtime = ctx.require(RUNTIME)
    label = ctx.require(CONFIG).get("label")
    if label == "broken":
        raise RuntimeError("broken config")
    if label == "slow-setup":
        probe.events.append(("setup-waiting",))
        await probe.setup_gate.wait()
    probe.events.append(
        ("setup", "provider", label, runtime.was_active, runtime.is_reload)
    )
    probe.resources.append(
        ctx.require(PROCESS_RESOURCES).acquire("shared-v1", probe.Resource)
    )
    tool = Slow(label)
    ctx.require(TOOLS).register(tool)

    async def echo(payload):
        return {"label": label}

    ctx.require(RPC).register("echo", echo)
    ctx.require(SERVICES).register(
        "labels", contract="labels-v1", label="Labels", methods={"echo": echo}
    )

    async def drain():
        probe.events.append(("drain", "provider", label))

    runtime.on_drain(drain)
    ctx.effect("dispose", lambda: probe.events.append(("dispose", "provider", label)))
    ctx.expose(tool)
"""

_CONSUMER = """
import asyncio
import sys
from shiori_sdk.core.services import DEPENDENCIES, RUNTIME, TOOLS
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
    runtime = ctx.require(RUNTIME)
    provider = ctx.require(DEPENDENCIES).require("provider")
    if provider.label == "consumer-fails":
        # A call into the new provider is under way when this setup fails.
        probe.pending.append(asyncio.ensure_future(provider.execute()))
        await asyncio.sleep(0)
        raise RuntimeError("consumer rejects the new provider")
    ctx.require(TOOLS).register(Relay(provider))
    probe.events.append(
        (
            "setup",
            "consumer",
            provider.label,
            runtime.was_active,
            runtime.is_reload,
        )
    )

    async def drain():
        probe.events.append(("drain", "consumer"))

    runtime.on_drain(drain)
    ctx.effect("dispose", lambda: probe.events.append(("dispose", "consumer")))
    ctx.expose({"provider": provider})
"""

_BYSTANDER = """
import sys
from shiori_sdk.core.services import TOOLS
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
    ctx.require(TOOLS).register(Busy())
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
        f"api: 4\nsdk: '>=4.0.0'\nid: {plugin_id}\n{manifest}", encoding="utf-8"
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
    module.pending = []
    module.shared = []
    module.Resource = _Resource
    monkeypatch.setitem(sys.modules, "reload_probe", module)
    return module


_CONSUMER_INJECT = "dependencies, runtime, tools"
_RELAY_CHANNEL = (
    "contributes:\n  channels:\n    - {name: relay, label: Relay, chat_types:"
    " [{type: private, label: Private, chat_id_label: ID}]}\n"
)


async def _kernel(
    tmp_path: Path,
    *,
    consumer_inject: str = _CONSUMER_INJECT,
    consumer_manifest: str = "",
    configs: dict[str, dict] | None = None,
) -> tuple[
    PluginKernel, PluginGenerationSettings, ToolRegistry, PluginRpcRegistry[Any]
]:
    _write(
        tmp_path,
        "provider",
        "inject: [tools, rpc, services, process_resources, config, runtime]\n",
        _PROVIDER,
    )
    _write(
        tmp_path,
        "consumer",
        f"inject: [{consumer_inject}]\ndependencies: [provider]\n{consumer_manifest}",
        _CONSUMER,
    )
    _write(
        tmp_path,
        "bystander",
        "inject: [tools]\n",
        _BYSTANDER,
    )
    tools = ToolRegistry()
    configs = configs or {"provider": {"label": "v1"}}
    settings = PluginGenerationSettings(
        workspace=tmp_path / "workspace",
        plugin_configs=configs,
        raw_plugin_configs={key: dict(value) for key, value in configs.items()},
        process_resources=ProcessResourceOwner(),
    )
    rpc = PluginRpcRegistry(EventBus())
    kernel = host_kernel([tmp_path], settings=settings, tools=tools, rpc=rpc)
    await kernel.load_all()
    assert settings.process_resources is not None
    settings.process_resources.publish(kernel.namespace)
    return kernel, settings, tools, rpc


def _failures(kernel: PluginKernel) -> list[str]:
    """Ids of the ``PluginFailed`` events the kernel emits from now on."""
    failed: list[str] = []

    async def record(event: PluginFailed) -> PluginFailed:
        failed.append(event.plugin_id)
        return event

    kernel.kernel.check(PluginFailed, record)
    return failed


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


async def _echo(rpc: PluginRpcRegistry[Any]) -> dict[str, object] | None:
    resolved = rpc.resolve("plugin.provider.echo")
    assert resolved is not None
    return await resolved[1]({})


@pytest.mark.asyncio
async def test_reload_reruns_only_the_closure_with_new_config(probe, tmp_path):
    kernel, settings, _, _ = await _kernel(tmp_path)
    probe.events.clear()
    failed = _failures(kernel)

    result = await _reload(kernel, "v2")

    assert result.plugin_ids == ("provider", "consumer")
    assert result.cleanup_errors == ()
    # The disposed consumer is not started by the new provider's start.
    assert failed == []
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
    assert settings.plugin_configs["provider"] == {"label": "v2"}
    assert settings.raw_plugin_configs["provider"] == {"label": "v2"}
    # The shared process resource is the same object and was never closed.
    assert probe.resources[0] is probe.resources[1]
    assert probe.resources[0].closed == 0
    await kernel.terminate_all(force=True)


@pytest.mark.asyncio
async def test_reload_waits_for_closure_calls_only_and_rejects_new_ones(
    probe, tmp_path
):
    kernel, _, tools, rpc = await _kernel(tmp_path)
    old_tool = tools.get_tool("provider_slow")
    resolved = rpc.resolve("plugin.provider.echo")
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
        await rpc.services.call(
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
    assert await rpc.services.call(
        "provider", "labels", "echo", {}, caller_active=lambda: True
    ) == {"label": "v2"}
    probe.bystander_release.set()
    assert await bystander == "bystander"
    await kernel.terminate_all(force=True)


@pytest.mark.asyncio
async def test_dependent_in_flight_work_can_still_call_its_provider_while_draining(
    probe, tmp_path
):
    kernel, _, tools, _ = await _kernel(tmp_path)
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
    kernel, settings, tools, rpc = await _kernel(tmp_path)
    in_flight = asyncio.create_task(tools.execute("provider_slow", {}))
    await _until(probe, ("call-start", "v1"))

    with pytest.raises(PluginReloadTimeout) as caught:
        await _reload(kernel, "v2", timeout=0.05)

    assert caught.value.busy == ("provider",)
    # The dependent stage already ran its wait-only on_drain; the provider
    # stage timed out; nothing was disposed and both stay ACTIVE.
    assert ("drain", "consumer") in probe.events
    assert ("drain", "provider", "v1") not in probe.events
    assert not any(event[0] == "dispose" for event in probe.events)
    assert all(row["state"] == "ACTIVE" for row in kernel.states())
    # The sealed dependent was reopened and admits calls again.
    relay = asyncio.create_task(tools.execute("consumer_relay", {}))
    await _until(probe, ("relay-start",))
    probe.relay_gate.set()
    assert settings.plugin_configs["provider"] == {"label": "v1"}
    assert await _echo(rpc) == {"label": "v1"}
    probe.release.set()
    assert await in_flight == "v1"
    assert await relay == "v1"
    await kernel.terminate_all(force=True)


@pytest.mark.asyncio
async def test_rollback_waits_for_calls_admitted_by_a_discarded_new_instance(
    probe, tmp_path
):
    kernel, settings, _, _ = await _kernel(tmp_path)
    reload = asyncio.create_task(_reload(kernel, "consumer-fails"))
    await _until(probe, ("call-start", "consumer-fails"))
    for _ in range(20):
        await asyncio.sleep(0)
    assert ("dispose", "provider", "consumer-fails") not in probe.events

    probe.release.set()
    with pytest.raises(PluginReloadFailed) as caught:
        await asyncio.wait_for(reload, 1)

    assert list(caught.value.failed) == ["consumer"]
    assert caught.value.cleanup_errors == ()
    assert probe.events.index(("call-end", "consumer-fails")) < probe.events.index(
        ("dispose", "provider", "consumer-fails")
    )
    assert await probe.pending[0] == "consumer-fails"
    assert settings.plugin_configs["provider"] == {"label": "v1"}
    await kernel.terminate_all(force=True)


@pytest.mark.asyncio
async def test_rollback_drain_timeout_is_reported_and_disposal_proceeds(
    probe, tmp_path
):
    kernel, _, _, _ = await _kernel(tmp_path)

    with pytest.raises(PluginReloadFailed) as caught:
        await _reload(kernel, "consumer-fails", timeout=0.05)

    [timeout] = caught.value.cleanup_errors
    assert isinstance(timeout, PluginReloadTimeout)
    assert timeout.busy == ("provider",)
    assert ("dispose", "provider", "consumer-fails") in probe.events
    assert all(row["state"] == "ACTIVE" for row in kernel.states())
    probe.release.set()
    assert await probe.pending[0] == "consumer-fails"
    await kernel.terminate_all(force=True)


_SHARER = """
import sys
from shiori_sdk.core.services import PROCESS_RESOURCES, TOOLS
from shiori_sdk.tools import Tool

probe = sys.modules["reload_probe"]


class Shared(Tool):
    name = "shared_tool"
    description = "one object kept across generations"
    parameters = {"type": "object", "properties": {}}

    async def execute(self, **kwargs):
        probe.events.append(("shared-call",))
        await probe.release.wait()
        return "shared"


class Holder:
    def __init__(self):
        self.tool = Shared()

    async def close(self):
        pass


async def setup(ctx):
    holder = ctx.require(PROCESS_RESOURCES).acquire("holder-v1", Holder)
    probe.shared.append(holder.tool)
    ctx.require(TOOLS).register(holder.tool)
"""


@pytest.mark.asyncio
async def test_retired_generation_gate_never_admits_a_shared_tool_call(probe, tmp_path):
    _write(
        tmp_path,
        "sharer",
        "inject: [tools, process_resources]\n",
        _SHARER,
    )
    owner = ProcessResourceOwner()

    async def generation() -> tuple[PluginKernel, ToolRegistry]:
        tools = ToolRegistry()
        kernel = host_kernel(
            [tmp_path],
            settings=PluginGenerationSettings(
                workspace=tmp_path / "workspace", process_resources=owner
            ),
            tools=tools,
        )
        await kernel.load_all()
        owner.publish(kernel.namespace)
        return kernel, tools

    first, _ = await generation()
    second, tools = await generation()
    await first.terminate_all(force=True)
    tool = probe.shared[0]
    assert probe.shared[1] is tool
    in_flight = asyncio.create_task(tools.execute("shared_tool", {}))
    await _until(probe, ("shared-call",))
    reload = asyncio.create_task(
        second.reload("sharer", values={}, raw_values={}, drain_timeout=5)
    )
    for _ in range(20):
        await asyncio.sleep(0)

    # Neither the terminated generation nor the draining one admits it.
    with pytest.raises(PluginRpcError):
        await asyncio.wait_for(tool.execute(), 1)
    probe.release.set()
    assert await in_flight == "shared"
    await asyncio.wait_for(reload, 1)
    # Dead gates were pruned: only the reloaded instance gates the object.
    assert len(tool.__dict__["__plugin_call_gates__"]) == 1
    assert await tool.execute() == "shared"
    await second.terminate_all(force=True)
    await owner.close()


@pytest.mark.asyncio
async def test_cancelling_the_caller_while_draining_reopens_the_old_instance(
    probe, tmp_path
):
    kernel, settings, tools, rpc = await _kernel(tmp_path)
    in_flight = asyncio.create_task(tools.execute("provider_slow", {}))
    await _until(probe, ("call-start", "v1"))
    reload = asyncio.create_task(_reload(kernel, "v2"))
    for _ in range(20):
        await asyncio.sleep(0)

    reload.cancel()
    with pytest.raises(asyncio.CancelledError):
        await reload

    assert await _echo(rpc) == {"label": "v1"}
    assert settings.plugin_configs["provider"] == {"label": "v1"}
    probe.release.set()
    assert await in_flight == "v1"
    assert not any(event[0] == "dispose" for event in probe.events)
    await kernel.terminate_all(force=True)


@pytest.mark.asyncio
async def test_cancelling_the_caller_during_setup_completes_the_reload(probe, tmp_path):
    kernel, settings, _, rpc = await _kernel(tmp_path)
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
    assert settings.plugin_configs["provider"] == {"label": "slow-setup"}
    assert await _echo(rpc) == {"label": "slow-setup"}
    assert probe.resources[0] is probe.resources[-1]
    assert probe.resources[0].closed == 0
    # The transition lock was released only after completion.
    assert (await _reload(kernel, "v3")).plugin_ids == ("provider", "consumer")
    await kernel.terminate_all(force=True)


@pytest.mark.asyncio
async def test_failed_reload_restores_the_old_config_instance(probe, tmp_path):
    kernel, settings, tools, _ = await _kernel(tmp_path)
    old_tables = settings.plugin_configs["provider"]
    probe.events.clear()

    with pytest.raises(PluginReloadFailed) as caught:
        await _reload(kernel, "broken")

    assert list(caught.value.failed) == ["provider", "consumer"]
    assert caught.value.__cause__ is caught.value.failed["provider"]
    assert str(caught.value.__cause__) == "broken config"
    assert caught.value.restore_failed == {}
    assert caught.value.cleanup_errors == ()
    assert settings.plugin_configs["provider"] is old_tables
    assert settings.raw_plugin_configs["provider"] == {"label": "v1"}
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
        (_RELAY_CHANNEL, "channels"),
        ("supports_hot_unload: false\n", "hot_unload"),
    ],
)
async def test_reload_refuses_generation_only_closures_before_any_change(
    probe, tmp_path, consumer_manifest, reason
):
    kernel, settings, _, _ = await _kernel(
        tmp_path,
        consumer_inject=(
            f"{_CONSUMER_INJECT}, channels"
            if reason == "channels"
            else _CONSUMER_INJECT
        ),
        consumer_manifest=consumer_manifest,
    )
    probe.events.clear()

    with pytest.raises(PluginReloadUnsupported) as caught:
        await _reload(kernel, "v2")

    assert caught.value.reason == reason
    assert caught.value.plugin_ids == ("consumer",)
    assert probe.events == []
    assert settings.plugin_configs["provider"] == {"label": "v1"}
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
    kernel, settings, _, _ = await _kernel(tmp_path, configs={"provider": config})

    with pytest.raises(PluginReloadUnsupported) as caught:
        await _reload(kernel, "v2")

    assert caught.value.reason == reason
    assert settings.plugin_configs["provider"] == config
    await kernel.terminate_all(force=True)


@pytest.mark.asyncio
async def test_reload_values_cannot_disable_the_target(probe, tmp_path):
    kernel, settings, _, _ = await _kernel(tmp_path)
    probe.events.clear()

    with pytest.raises(ValueError, match="停用"):
        await kernel.reload(
            "provider",
            values={"label": "v2", "enabled": False},
            raw_values={"label": "v2", "enabled": False},
            drain_timeout=5,
        )

    assert probe.events == []
    assert settings.plugin_configs["provider"] == {"label": "v1"}
    await kernel.terminate_all(force=True)


@pytest.mark.asyncio
async def test_terminate_waits_for_a_reload_and_later_reloads_are_refused(
    probe, tmp_path
):
    kernel, _, tools, _ = await _kernel(tmp_path)
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


_HOOKED = """
import sys
from dataclasses import replace

from shiori_sdk.core.conversation import StepStarting
from shiori_sdk.core.services import CONFIG

probe = sys.modules["reload_probe"]


async def setup(ctx):
    label = ctx.require(CONFIG).get("label")

    async def stamp(event):
        probe.events.append(("handler-start", label))
        await probe.release.wait()
        return replace(event, extra_hints=(*event.extra_hints, label))

    ctx.on(StepStarting, stamp)
"""


async def _hooked_kernel(tmp_path: Path) -> PluginKernel:
    _write(tmp_path, "hooked", "inject: [config]\n", _HOOKED)
    configs = {"hooked": {"label": "v1"}}
    kernel = host_kernel(
        [tmp_path],
        settings=PluginGenerationSettings(
            plugin_configs=configs, raw_plugin_configs={"hooked": {"label": "v1"}}
        ),
    )
    await kernel.load_all()
    return kernel


def _reload_hooked(kernel: PluginKernel):
    return kernel.reload(
        "hooked",
        values={"label": "v2"},
        raw_values={"label": "v2"},
        drain_timeout=5,
    )


def _step() -> StepStarting:
    return StepStarting(
        session_key="s",
        channel="c",
        chat_id="1",
        iteration=1,
        input_tokens_estimate=0,
        visible_tool_names=None,
    )


async def _hints(kernel: PluginKernel) -> tuple[str, ...]:
    event = await kernel.kernel.emit(_step())
    assert isinstance(event, StepStarting)
    return event.extra_hints


@pytest.mark.asyncio
async def test_reload_waits_for_a_running_turn_handler_and_then_runs_the_new_one(
    probe, tmp_path
):
    kernel = await _hooked_kernel(tmp_path)
    # A turn is inside the old instance's handler when the reload starts.
    running = asyncio.create_task(_hints(kernel))
    await _until(probe, ("handler-start", "v1"))

    reload = asyncio.create_task(_reload_hooked(kernel))
    for _ in range(20):
        await asyncio.sleep(0)
    assert not reload.done()

    probe.release.set()
    assert await running == ("v1",)
    await asyncio.wait_for(reload, 1)
    assert await _hints(kernel) == ("v2",)
    await kernel.terminate_all(force=True)


# ── 代内启停（#858） ──────────────────────────────────────────────────────


def _toggle(kernel: PluginKernel, enabled: bool, commit=None, label: str = "v1"):
    table = {"label": label, "enabled": enabled}
    return kernel.set_enabled(
        "provider",
        values=table,
        raw_values=dict(table),
        drain_timeout=5,
        commit=commit,
    )


def _states(kernel: PluginKernel) -> dict[str, str]:
    return {row["id"]: row["state"] for row in kernel.states()}


@pytest.mark.asyncio
async def test_disable_and_enable_only_touch_the_closure_within_the_generation(
    probe, tmp_path
):
    kernel, settings, tools, rpc = await _kernel(tmp_path)
    in_flight = asyncio.create_task(tools.execute("provider_slow", {}))
    await _until(probe, ("call-start", "v1"))
    probe.events.clear()
    committed = []

    # Disabling does not wait for the provider's in-flight call.
    disabled = await asyncio.wait_for(_toggle(kernel, False, committed.append), 1)

    assert disabled.plugin_ids == ("provider", "consumer")
    assert committed == [("provider", "consumer")]
    assert probe.events == [("dispose", "consumer"), ("dispose", "provider", "v1")]
    assert _states(kernel) == {
        "provider": "DISABLED",
        "consumer": "BLOCKED",
        "bystander": "ACTIVE",
    }
    assert settings.plugin_configs["provider"] == {"label": "v1", "enabled": False}
    assert tools.get_tool("provider_slow") is None
    assert rpc.resolve("plugin.provider.echo") is None
    # Nothing re-acquires the provider's process resource, so it is closed.
    assert probe.resources[0].closed == 1
    probe.release.set()
    assert await in_flight == "v1"

    probe.events.clear()
    enabled = await _toggle(kernel, True, committed.append)

    assert enabled.plugin_ids == ("provider", "consumer")
    assert committed[-1] == ("provider", "consumer")
    # A plugin turned on again within the generation starts fresh.
    assert probe.events == [
        ("setup", "provider", "v1", False, False),
        ("setup", "consumer", "v1", False, False),
    ]
    assert all(state == "ACTIVE" for state in _states(kernel).values())
    new_provider = kernel._dependency_api("provider")
    assert kernel._dependency_api("consumer")["provider"] is new_provider
    assert await _echo(rpc) == {"label": "v1"}
    assert probe.resources[-1] is not probe.resources[0]
    await kernel.terminate_all(force=True)


@pytest.mark.asyncio
async def test_failed_toggle_commit_restores_the_previous_states(probe, tmp_path):
    kernel, settings, _, _ = await _kernel(tmp_path)
    probe.events.clear()

    def fail(_plugin_ids):
        raise OSError("disk full")

    with pytest.raises(PluginReloadFailed) as caught:
        await _toggle(kernel, False, fail)

    assert isinstance(caught.value.__cause__, OSError)
    assert caught.value.restore_failed == {}
    assert all(state == "ACTIVE" for state in _states(kernel).values())
    assert settings.plugin_configs["provider"] == {"label": "v1"}
    # The restored instances were active before, and kept their resource.
    assert ("setup", "provider", "v1", True, True) in probe.events
    assert probe.resources[0] is probe.resources[-1]
    assert probe.resources[0].closed == 0

    await _toggle(kernel, False)
    probe.events.clear()
    with pytest.raises(PluginReloadFailed):
        await _toggle(kernel, True, fail)

    assert ("setup", "provider", "v1", False, False) in probe.events
    assert _states(kernel) == {
        "provider": "DISABLED",
        "consumer": "BLOCKED",
        "bystander": "ACTIVE",
    }
    assert settings.plugin_configs["provider"] == {"label": "v1", "enabled": False}
    await kernel.terminate_all(force=True)


@pytest.mark.asyncio
async def test_enabling_a_plugin_whose_setup_fails_keeps_it_failed(probe, tmp_path):
    kernel, settings, _, _ = await _kernel(
        tmp_path, configs={"provider": {"label": "broken", "enabled": False}}
    )
    committed = []

    result = await _toggle(kernel, True, committed.append, label="broken")

    # Like a generation swap: the change is kept, the plugin reports its error.
    assert committed == [("provider", "consumer")]
    assert result.plugin_ids == ("provider", "consumer")
    assert _states(kernel) == {
        "provider": "FAILED",
        "consumer": "BLOCKED",
        "bystander": "ACTIVE",
    }
    assert settings.plugin_configs["provider"]["enabled"] is True
    await kernel.terminate_all(force=True)


_WATCHER = """
import sys
from shiori_sdk.core.services import DEPENDENCIES, RUNTIME

probe = sys.modules["reload_probe"]


async def setup(ctx):
    runtime = ctx.require(RUNTIME)
    # Read once at setup, as an optional consumer that registers with its
    # provider only when there is one.
    provider = ctx.require(DEPENDENCIES).get_optional("provider")
    label = None if provider is None else provider.label
    probe.events.append(
        ("setup", "watcher", label, runtime.was_active, runtime.is_reload)
    )

    async def drain():
        probe.events.append(("drain", "watcher"))

    runtime.on_drain(drain)
    ctx.effect("dispose", lambda: probe.events.append(("dispose", "watcher")))
"""


@pytest.mark.asyncio
async def test_toggling_a_provider_sets_up_its_running_optional_consumers_again(
    probe, tmp_path
):
    _write(
        tmp_path,
        "watcher",
        "inject: [dependencies, runtime]\noptional_dependencies: [provider]\n",
        _WATCHER,
    )
    kernel, _, _, _ = await _kernel(tmp_path)
    probe.events.clear()

    disabled = await _toggle(kernel, False)

    # The optional consumer stays up: drained like on a reload, then set up
    # again without the provider, as the running instance it was.
    assert disabled.plugin_ids == ("provider", "consumer", "watcher")
    assert probe.events == [
        ("drain", "watcher"),
        ("dispose", "watcher"),
        ("dispose", "consumer"),
        ("dispose", "provider", "v1"),
        ("setup", "watcher", None, True, True),
    ]
    assert _states(kernel) == {
        "provider": "DISABLED",
        "consumer": "BLOCKED",
        "bystander": "ACTIVE",
        "watcher": "ACTIVE",
    }

    probe.events.clear()
    enabled = await _toggle(kernel, True)

    # Set up again after the provider it now gets.
    assert enabled.plugin_ids == ("provider", "consumer", "watcher")
    assert probe.events == [
        ("drain", "watcher"),
        ("dispose", "watcher"),
        ("setup", "provider", "v1", False, False),
        ("setup", "consumer", "v1", False, False),
        ("setup", "watcher", "v1", True, True),
    ]
    assert all(state == "ACTIVE" for state in _states(kernel).values())
    await kernel.terminate_all(force=True)


_MUTUAL = """
import sys
from shiori_sdk.core.services import CONFIG, DEPENDENCIES

probe = sys.modules["reload_probe"]


async def setup(ctx):
    other = ctx.require(DEPENDENCIES).get_optional("{other}")
    label = ctx.require(CONFIG).get("label")
    probe.events.append(("setup", "{me}", label, other is not None))
    ctx.effect("dispose", lambda: probe.events.append(("dispose", "{me}")))
    ctx.expose({{"id": "{me}"}})
"""


@pytest.mark.asyncio
async def test_mutually_optional_plugins_reload_and_toggle_the_named_target(
    probe, tmp_path
):
    for me, other in (("aaa", "zzz"), ("zzz", "aaa")):
        _write(
            tmp_path,
            me,
            f"inject: [dependencies, config]\noptional_dependencies: [{other}]\n",
            _MUTUAL.format(me=me, other=other),
        )
    configs = {"aaa": {"label": "a1"}, "zzz": {"label": "z1"}}
    kernel = host_kernel(
        [tmp_path],
        settings=PluginGenerationSettings(
            workspace=tmp_path / "workspace",
            plugin_configs=configs,
            raw_plugin_configs={key: dict(value) for key, value in configs.items()},
        ),
    )
    await kernel.load_all()
    probe.events.clear()

    # Mutual optional injection does not rank the target last in the closure;
    # the named target still takes the table and is set up before its consumer.
    reloaded = await kernel.reload(
        "aaa", values={"label": "a2"}, raw_values={"label": "a2"}, drain_timeout=5
    )

    assert reloaded.plugin_ids == ("aaa", "zzz")
    assert configs == {"aaa": {"label": "a2"}, "zzz": {"label": "z1"}}
    assert probe.events == [
        ("dispose", "zzz"),
        ("dispose", "aaa"),
        ("setup", "aaa", "a2", False),
        ("setup", "zzz", "z1", True),
    ]

    probe.events.clear()
    table = {"label": "a2", "enabled": False}
    disabled = await kernel.set_enabled(
        "aaa", values=table, raw_values=dict(table), drain_timeout=5
    )

    assert disabled.plugin_ids == ("aaa", "zzz")
    assert _states(kernel) == {"aaa": "DISABLED", "zzz": "ACTIVE"}
    assert configs == {"aaa": table, "zzz": {"label": "z1"}}
    assert probe.events == [
        ("dispose", "zzz"),
        ("dispose", "aaa"),
        ("setup", "zzz", "z1", False),
    ]
    await kernel.terminate_all(force=True)


@pytest.mark.asyncio
async def test_toggle_refuses_closures_only_a_generation_swap_can_change(
    probe, tmp_path
):
    kernel, settings, _, _ = await _kernel(
        tmp_path,
        consumer_inject=f"{_CONSUMER_INJECT}, channels",
        consumer_manifest=_RELAY_CHANNEL,
    )
    probe.events.clear()

    with pytest.raises(PluginReloadUnsupported) as caught:
        await _toggle(kernel, False)

    assert caught.value.reason == "channels"
    assert caught.value.plugin_ids == ("consumer",)
    assert probe.events == []
    assert settings.plugin_configs["provider"] == {"label": "v1"}
    assert all(state == "ACTIVE" for state in _states(kernel).values())
    await kernel.terminate_all(force=True)


@pytest.mark.asyncio
async def test_enable_refuses_a_dependency_only_a_swap_can_retry(probe, tmp_path):
    kernel, _, _, _ = await _kernel(
        tmp_path,
        configs={"provider": {"label": "broken"}, "consumer": {"enabled": False}},
    )

    with pytest.raises(PluginReloadUnsupported) as caught:
        await kernel.set_enabled(
            "consumer",
            values={"enabled": True},
            raw_values={"enabled": True},
            drain_timeout=5,
        )

    assert caught.value.reason == "failed"
    assert caught.value.plugin_ids == ("provider",)
    assert _states(kernel)["consumer"] == "DISABLED"
    await kernel.terminate_all(force=True)


@pytest.mark.asyncio
async def test_disabled_plugin_is_not_started_again_by_the_kernel(probe, tmp_path):
    kernel, _, _, _ = await _kernel(tmp_path)
    await _toggle(kernel, False)
    probe.events.clear()

    # ``Kernel.start`` sets up every runnable plugin that is not running, so the
    # disabled provider must be register-only in the kernel by now.
    await kernel.kernel.start([])

    assert probe.events == []
    status = kernel.kernel.status("provider")
    assert status is not None and status.state is not KernelState.ACTIVE
    assert _states(kernel)["provider"] == "DISABLED"
    await kernel.terminate_all(force=True)


@pytest.mark.asyncio
async def test_failed_plugin_is_retried_only_when_a_load_selects_it(probe, tmp_path):
    _write(
        tmp_path,
        "boom",
        "",
        "import sys\n\nasync def setup(ctx):\n"
        "    probe = sys.modules['reload_probe']\n"
        "    probe.events.append(('setup', 'boom'))\n"
        "    if not probe.setup_gate.is_set():\n"
        "        raise RuntimeError('boom')\n",
    )
    _write(
        tmp_path,
        "later",
        "",
        "import sys\n\nasync def setup(ctx):\n"
        "    sys.modules['reload_probe'].events.append(('setup', 'later'))\n",
    )
    configs = {"later": {"enabled": False}}
    kernel = host_kernel(
        [tmp_path],
        settings=PluginGenerationSettings(
            workspace=tmp_path / "workspace",
            plugin_configs=configs,
            raw_plugin_configs={key: dict(value) for key, value in configs.items()},
        ),
    )
    failed = _failures(kernel)
    await kernel.load_all()
    table = {"enabled": True}

    # Another plugin's start within the generation does not run the failed one.
    _ = await kernel.set_enabled(
        "later", values=table, raw_values=dict(table), drain_timeout=5
    )

    assert _states(kernel) == {"boom": "FAILED", "later": "ACTIVE"}
    assert probe.events == [("setup", "boom"), ("setup", "later")]
    assert failed == ["boom"]

    # Selected by a load, it is tried again.
    probe.setup_gate.set()
    assert await kernel.load("boom")
    assert probe.events[-1] == ("setup", "boom")
    assert failed == ["boom"]
    await kernel.terminate_all(force=True)


@pytest.mark.asyncio
async def test_providers_of_one_key_take_over_from_each_other_within_the_generation(
    probe, tmp_path
):
    for plugin_id in ("first", "second"):
        _write(
            tmp_path,
            plugin_id,
            "provides: [shared.engine]\n",
            "import sys\n\nasync def setup(ctx):\n"
            f"    sys.modules['reload_probe'].events.append(('setup', {plugin_id!r}))\n",
        )
    configs = {"second": {"enabled": False}}
    kernel = host_kernel(
        [tmp_path],
        settings=PluginGenerationSettings(
            workspace=tmp_path / "workspace",
            plugin_configs=configs,
            raw_plugin_configs={key: dict(value) for key, value in configs.items()},
        ),
    )
    await kernel.load_all()

    async def toggle(plugin_id: str, enabled: bool) -> None:
        table = {"enabled": enabled}
        _ = await kernel.set_enabled(
            plugin_id, values=table, raw_values=dict(table), drain_timeout=5
        )

    # A disabled provider no longer counts as a duplicate of the one enabled.
    await toggle("first", False)
    await toggle("second", True)
    assert _states(kernel) == {"first": "DISABLED", "second": "ACTIVE"}
    first = kernel.kernel.status("first")
    assert first is not None and first.diagnostic is None

    # Enabled while the other runs, it is refused; once the other is disabled
    # it starts within the generation instead of staying BLOCKED.
    await toggle("first", True)
    assert _states(kernel)["first"] == "BLOCKED"
    await toggle("second", False)
    assert _states(kernel) == {"first": "ACTIVE", "second": "DISABLED"}
    assert probe.events == [("setup", "first"), ("setup", "second"), ("setup", "first")]
    await kernel.terminate_all(force=True)
