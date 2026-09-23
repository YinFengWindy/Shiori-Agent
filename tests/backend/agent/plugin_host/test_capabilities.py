"""capabilities.py 行为：贡献登记、卸载移除、后台任务取消与槽位校验。"""

from __future__ import annotations

import asyncio
import inspect

import pytest

from agent.plugin_host.capabilities import (
    BackgroundCapability,
    ChannelsCapability,
    LifecycleCapability,
    PHASE_SLOTS,
    PluginContributions,
    ProactiveGatesCapability,
    RpcCapability,
    ToolHooksCapability,
    ToolsCapability,
    contribute_to_list,
)
from agent.plugin_host.diagnostics import ChannelDeclarationError
from agent.plugin_host.effects import EffectScope
from agent.plugin_host.rpc import PluginRpcRegistry
from desktop_bridge.method_policy import Concurrency, Handler


class _FakeRegistry:
    """记录 register/unregister 调用的最小 ToolRegistry 替身。"""

    def __init__(self) -> None:
        self.registered: list[str] = []
        self.register_kwargs: dict[str, object] = {}

    def register(self, tool: object, **kwargs: object) -> None:
        self.registered.append(str(getattr(tool, "name")))
        self.register_kwargs = kwargs

    def unregister(self, name: str) -> None:
        if name in self.registered:
            self.registered.remove(name)


class _FakeTool:
    name = "demo_tool"


class _Named:
    def __init__(self, name: str) -> None:
        self.name = name


# ── 共享 helper ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_contribute_to_list_adds_then_removes_on_dispose():
    scope = EffectScope("demo")
    target: list[str] = ["pre-existing"]
    contribute_to_list(target, "added", effects=scope, label="x:added")

    assert target == ["pre-existing", "added"]
    _ = await scope.dispose_all()
    # 只移除自己贡献的项，既有内容保留
    assert target == ["pre-existing"]


@pytest.mark.asyncio
async def test_contribute_to_list_discard_is_idempotent():
    scope = EffectScope("demo")
    target: list[str] = []
    contribute_to_list(target, "once", effects=scope, label="x:once")
    target.remove("once")  # 外部已移除

    # 守卫使处置不抛 ValueError
    assert await scope.dispose_all() == []


# ── ToolsCapability ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tools_capability_registers_with_plugin_source_and_unregisters():
    registry = _FakeRegistry()
    contributions = PluginContributions()
    scope = EffectScope("demo")
    capability = ToolsCapability(registry, scope, contributions, "demo_plugin")

    capability.register(_FakeTool(), risk="destructive", always_on=True)

    assert registry.registered == ["demo_tool"]
    assert contributions.tool_names == ["demo_tool"]
    # 工具来源必须标为插件，否则 ToolRegistry 无法归因
    assert registry.register_kwargs["source_type"] == "plugin"
    assert registry.register_kwargs["source_name"] == "demo_plugin"
    assert registry.register_kwargs["risk"] == "destructive"
    assert registry.register_kwargs["always_on"] is True

    _ = await scope.dispose_all()
    assert registry.registered == []
    assert contributions.tool_names == []


def test_tools_capability_without_registry_raises():
    capability = ToolsCapability(
        None, EffectScope("demo"), PluginContributions(), "demo_plugin"
    )
    with pytest.raises(RuntimeError, match="未提供 ToolRegistry"):
        capability.register(_FakeTool())


# ── LifecycleCapability ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_lifecycle_contribution_removed_on_dispose():
    contributions = PluginContributions()
    scope = EffectScope("demo")
    capability = LifecycleCapability(contributions, scope)
    first, second = object(), object()

    capability.contribute("before_turn", [first, second])
    assert contributions.phase_modules["before_turn"] == [first, second]

    _ = await scope.dispose_all()
    assert contributions.phase_modules["before_turn"] == []


def test_lifecycle_unknown_slot_raises():
    capability = LifecycleCapability(PluginContributions(), EffectScope("demo"))
    with pytest.raises(ValueError, match="未知 phase 槽位"):
        capability.contribute("after_everything", [object()])


@pytest.mark.asyncio
async def test_lifecycle_dispose_only_removes_own_modules():
    contributions = PluginContributions()
    foreign = object()
    contributions.phase_modules["after_turn"].append(foreign)
    scope = EffectScope("demo")
    mine = object()

    LifecycleCapability(contributions, scope).contribute("after_turn", [mine])
    _ = await scope.dispose_all()

    # 其他插件贡献的模块不能被本插件卸载带走
    assert contributions.phase_modules["after_turn"] == [foreign]


def test_all_phase_slots_are_contributable():
    contributions = PluginContributions()
    capability = LifecycleCapability(contributions, EffectScope("demo"))
    for slot in PHASE_SLOTS:
        capability.contribute(slot, [object()])
    assert all(len(contributions.phase_modules[slot]) == 1 for slot in PHASE_SLOTS)


def test_phase_slots_matches_the_seven_documented_slot_names():
    """v2 PHASE_SLOTS 与 legacy 清单共用同一批槽位名，防止两处清单漂移。

    原先这条检查是 kernel.py 模块顶层的 assert（会在每次导入时执行）；
    迁移为普通测试，避免生产导入路径承担单元测试职责。
    """
    assert set(PHASE_SLOTS) == {
        "before_turn",
        "before_reasoning",
        "prompt_render",
        "before_step",
        "after_step",
        "after_reasoning",
        "after_turn",
    }


# ── 列表型 capability ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tool_hooks_capability_add_and_dispose():
    contributions = PluginContributions()
    scope = EffectScope("demo")
    hook = _Named("plugin:demo:guard")

    ToolHooksCapability(contributions, scope, "demo").add(hook)  # type: ignore[arg-type]
    assert contributions.tool_hooks == [hook]
    assert scope.labels == ["tool_hook:plugin:demo:guard"]

    _ = await scope.dispose_all()
    assert contributions.tool_hooks == []


@pytest.mark.asyncio
async def test_tool_hooks_capability_add_handler_builds_name_from_function():
    """add_handler 必须用 build_hook_name 统一拼 hook 名，不需要插件自己拼字符串。"""
    contributions = PluginContributions()
    scope = EffectScope("demo")

    async def rewrite_rm_to_mv(event: object) -> None:
        return None

    ToolHooksCapability(contributions, scope, "shell_restore").add_handler(
        rewrite_rm_to_mv, tool_name_filter="shell"
    )

    assert len(contributions.tool_hooks) == 1
    hook = contributions.tool_hooks[0]
    assert hook.name == "plugin:shell_restore:rewrite_rm_to_mv"


@pytest.mark.asyncio
async def test_tool_hooks_capability_add_handler_honors_explicit_handler_name():
    """legacy 适配器把 handler 包成 functools.partial 后没有 __name__，
    必须能显式传 handler_name 覆盖，而不是退化成 repr(partial(...))。"""
    import functools

    contributions = PluginContributions()
    scope = EffectScope("demo")

    async def guard(instance: object, event: object) -> None:
        return None

    bound = functools.partial(guard, object())

    ToolHooksCapability(contributions, scope, "legacy_hook").add_handler(
        bound, handler_name="guard"
    )

    assert contributions.tool_hooks[0].name == "plugin:legacy_hook:guard"


@pytest.mark.asyncio
async def test_proactive_gates_capability_add_and_dispose():
    contributions = PluginContributions()
    scope = EffectScope("demo")
    gate = _Named("relationship.loneliness")

    ProactiveGatesCapability(contributions, scope).add(gate)  # type: ignore[arg-type]
    assert contributions.proactive_gates == [gate]
    assert scope.labels == ["proactive_gate:relationship.loneliness"]

    _ = await scope.dispose_all()
    assert contributions.proactive_gates == []


@pytest.mark.asyncio
async def test_channels_capability_add_and_dispose():
    contributions = PluginContributions()
    scope = EffectScope("demo")
    channel = _Named("qq")

    capability = ChannelsCapability(
        contributions, scope, plugin_id="demo", declared=frozenset({"qq"})
    )
    capability.add(channel)  # type: ignore[arg-type]
    assert contributions.channels == [channel]
    assert scope.labels == ["channel:qq"]

    _ = await scope.dispose_all()
    assert contributions.channels == []


def test_channels_capability_rejects_undeclared_channel_without_registering():
    contributions = PluginContributions()
    scope = EffectScope("demo")
    capability = ChannelsCapability(
        contributions, scope, plugin_id="demo", declared=frozenset({"qq"})
    )

    with pytest.raises(ChannelDeclarationError) as caught:
        capability.add(_Named("telegram"))  # type: ignore[arg-type]

    assert caught.value.diagnostic.code == "undeclared_channel"
    assert caught.value.diagnostic.state == "FAILED"
    assert "telegram" in caught.value.diagnostic.reason
    assert contributions.channels == []
    assert scope.labels == []


# ── RpcCapability ─────────────────────────────────────────────────────────


async def _ping(payload):
    return {"pong": payload}


@pytest.mark.asyncio
async def test_rpc_capability_registers_under_plugin_namespace_and_disposes():
    registry = PluginRpcRegistry()
    scope = EffectScope("demo_plugin")
    capability = RpcCapability(registry, scope, "demo_plugin")

    capability.register(
        "ping", _ping, concurrency=Concurrency.READ_ONLY, admission_exempt=True
    )

    resolved = registry.resolve("plugin.demo_plugin.ping")
    assert resolved == ("demo_plugin", _ping)
    policy = registry.policy_for("plugin.demo_plugin.ping")
    assert policy is not None
    assert policy.concurrency is Concurrency.READ_ONLY
    assert policy.admission_exempt is True
    assert policy.handler is Handler.GENERATION
    assert await _ping({"x": 1}) == {"pong": {"x": 1}}


@pytest.mark.asyncio
async def test_rpc_capability_dispose_unregisters_the_method():
    registry = PluginRpcRegistry()
    scope = EffectScope("demo_plugin")
    capability = RpcCapability(registry, scope, "demo_plugin")
    capability.register("ping", _ping)

    _ = await scope.dispose_all()

    # 卸载后其 RPC 方法立即不可调用
    assert registry.resolve("plugin.demo_plugin.ping") is None


def test_rpc_capability_defaults_to_conservative_mutation_policy():
    registry = PluginRpcRegistry()
    capability = RpcCapability(registry, EffectScope("demo_plugin"), "demo_plugin")

    capability.register("write", _ping)

    policy = registry.policy_for("plugin.demo_plugin.write")
    assert policy is not None
    assert policy.concurrency is Concurrency.MUTATION
    assert policy.admission_exempt is False


@pytest.mark.asyncio
async def test_rpc_events_report_delivery_and_reject_disposed_producers():
    from agent.plugin_host.bridge_events import PluginBridgeEvent
    from bus.event_bus import EventBus

    bus = EventBus()
    scope = EffectScope("demo")
    capability = RpcCapability(PluginRpcRegistry(), scope, "demo", bus)
    assert await capability.emit("changed", {}) is False

    def delivered(event):
        event.dispatched = True

    bus.on(PluginBridgeEvent, delivered)
    assert await capability.emit("changed", {}) is True
    await scope.dispose_all()
    with pytest.raises(RuntimeError, match="已处置"):
        await capability.emit("changed", {})


# ── BackgroundCapability ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_background_task_cancelled_and_awaited_on_dispose():
    scope = EffectScope("demo")
    started = asyncio.Event()
    cleaned: list[str] = []

    async def worker() -> None:
        started.set()
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            cleaned.append("cancelled")
            raise

    task = BackgroundCapability(scope, "demo_plugin").spawn(worker(), name="worker")
    await started.wait()
    assert not task.done()
    assert task.get_name() == "plugin:demo_plugin:worker"

    _ = await scope.dispose_all()
    # dispose 必须等到任务真正退出，而不是只发出取消
    assert task.done()
    assert cleaned == ["cancelled"]


@pytest.mark.asyncio
async def test_background_dispose_of_finished_task_is_noop():
    scope = EffectScope("demo")

    async def quick() -> None:
        return None

    task = BackgroundCapability(scope, "demo_plugin").spawn(quick(), name="quick")
    await task

    assert await scope.dispose_all() == []
    assert not task.cancelled()


@pytest.mark.asyncio
async def test_background_task_failure_does_not_break_dispose():
    scope = EffectScope("demo")
    failed = asyncio.Event()

    async def boom() -> None:
        failed.set()
        raise RuntimeError("worker exploded")

    _ = BackgroundCapability(scope, "demo_plugin").spawn(boom(), name="boom")
    await failed.wait()
    await asyncio.sleep(0)

    # 后台任务自身异常不得让插件卸载失败
    assert await scope.dispose_all() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("during_cleanup", [True, False])
async def test_background_spawn_rejected_without_task_or_coroutine_leak(during_cleanup):
    scope = EffectScope("demo")
    capability = BackgroundCapability(scope, "demo")
    started = []

    async def worker():
        started.append("started")

    def spawn_late():
        coro = worker()
        before = asyncio.all_tasks()
        with pytest.raises(RuntimeError, match="已处置"):
            capability.spawn(coro, name="late")
        assert asyncio.all_tasks() == before
        assert inspect.getcoroutinestate(coro) == inspect.CORO_CLOSED

    if during_cleanup:
        scope.add("spawn-late", spawn_late)
    assert await scope.dispose_all() == []
    if not during_cleanup:
        spawn_late()
    await asyncio.sleep(0)
    assert started == []


@pytest.mark.asyncio
async def test_closed_scope_rejects_contributions_before_mutating_registries():
    scope = EffectScope("demo")
    contributions = PluginContributions()
    registry = _FakeRegistry()
    rpc = PluginRpcRegistry()
    target: list[str] = []

    def register_late():
        with pytest.raises(RuntimeError, match="已处置"):
            contribute_to_list(target, "late", effects=scope, label="late")
        with pytest.raises(RuntimeError, match="已处置"):
            ToolsCapability(registry, scope, contributions, "demo").register(
                _FakeTool()
            )
        with pytest.raises(RuntimeError, match="已处置"):
            LifecycleCapability(contributions, scope).contribute(
                "after_turn", [object()]
            )
        with pytest.raises(RuntimeError, match="已处置"):
            RpcCapability(rpc, scope, "demo").register("ping", _ping)

    scope.add("register-late", register_late)
    assert await scope.dispose_all() == []
    assert target == []
    assert registry.registered == []
    assert contributions.tool_names == []
    assert contributions.phase_modules["after_turn"] == []
    assert rpc.resolve("plugin.demo.ping") is None
