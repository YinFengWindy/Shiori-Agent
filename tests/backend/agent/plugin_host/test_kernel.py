"""内核行为：发现、v2 装配、capability 门控、启停与聚合面。"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from agent.plugin_host import PluginState
from agent.plugin_host.plugin_data import plugin_data_dir
from agent.tools.registry import ToolRegistry
from bus.event_bus import EventBus

from tests.backend.agent.plugin_host.conftest import (
    REPOSITORY_ROOT,
    before_turn_ctx,
    make_kernel,
    stage_plugin_package,
    PLUGIN_FIXTURES,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("strict", [False, True])
async def test_setup_cancellation_rolls_back_before_force_cleanup(tmp_path, strict):
    for name in ("active", "waiting"):
        package = tmp_path / name
        (package / "backend").mkdir(parents=True)
        (package / "manifest.yaml").write_text(
            f"api: 2\nid: {name}\ncapabilities: [events, lifecycle]\n"
            "supports_hot_unload: false\n",
            encoding="utf-8",
        )
        (package / "backend/plugin.py").write_text(
            "import asyncio\n"
            "async def setup(ctx):\n"
            "    state = ['started']\n"
            "    ctx.expose(state)\n"
            "    ctx.effect('close', lambda: state.append('closed'))\n"
            "    async def on_event(event):\n"
            f"        event.append('{name}')\n"
            "        return event\n"
            "    ctx.events.on(list, on_event)\n"
            "    ctx.lifecycle.contribute('before_turn', [object()])\n"
            + ("    await asyncio.Event().wait()\n" if name == "waiting" else ""),
            encoding="utf-8",
        )
    bus = EventBus()
    kernel = make_kernel([tmp_path], event_bus=bus, strict=strict)
    loading = asyncio.create_task(kernel.load_all())
    await asyncio.sleep(0)
    waiting = kernel._handles["waiting"]
    state = waiting.instance
    active_state = kernel._dependency_api("active")
    assert waiting.state is PluginState.LOADING
    assert state == ["started"]
    assert waiting.effects.labels
    assert len(waiting.contributions.phase_modules["before_turn"]) == 1
    loading.cancel()
    with pytest.raises(asyncio.CancelledError):
        await loading
    try:
        assert state == ["started", "closed"]
        assert waiting.effects.labels == []
        assert waiting.contributions.phase_modules["before_turn"] == []
        assert waiting.state is PluginState.FAILED
        assert isinstance(waiting.error, asyncio.CancelledError)
        assert await bus.emit([]) == ["active"]
        assert active_state == ["started"]
    finally:
        await kernel.terminate_all(force=True)
    assert active_state == ["started", "closed"]
    assert state == ["started", "closed"]
    assert await bus.emit([]) == []
    assert kernel.states() == []


@pytest.mark.asyncio
async def test_invalid_yaml_is_diagnosed_without_blocking_valid_sibling(
    tmp_path, caplog
):
    from agent.plugin_host.manifest import ManifestError

    broken = tmp_path / "broken"
    broken.mkdir()
    (broken / "manifest.yaml").write_text("api: 2\ncapabilities: [\n", encoding="utf-8")
    stage_plugin_package(PLUGIN_FIXTURES / "hello", tmp_path / "hello")
    kernel = make_kernel([tmp_path], event_bus=EventBus())
    try:
        await kernel.load_all()
        assert kernel.loaded_count == 1
        assert kernel.states()[0]["id"] == "hello"
        assert "broken" in caplog.text
        assert "manifest" in caplog.text
    finally:
        await kernel.terminate_all(force=True)
    strict_kernel = make_kernel([tmp_path], event_bus=EventBus(), strict=True)
    with pytest.raises(ManifestError, match="manifest.yaml"):
        await strict_kernel.load_all()


@pytest.mark.asyncio
async def test_force_cleanup_recovers_effects_after_rollback_is_cancelled(tmp_path):
    package = tmp_path / "waiting"
    (package / "backend").mkdir(parents=True)
    (package / "manifest.yaml").write_text(
        "api: 2\ncapabilities: []\nsupports_hot_unload: false\n", encoding="utf-8"
    )
    (package / "backend/plugin.py").write_text(
        "import asyncio\n"
        "async def setup(ctx):\n"
        "    state = {'closed': False, 'closing': asyncio.Event()}\n"
        "    ctx.expose(state)\n"
        "    ctx.effect('close', lambda: state.update(closed=True))\n"
        "    async def interrupted_close():\n"
        "        state['closing'].set()\n"
        "        await asyncio.Event().wait()\n"
        "    ctx.effect('interrupted', interrupted_close)\n"
        "    await asyncio.Event().wait()\n",
        encoding="utf-8",
    )
    kernel = make_kernel([tmp_path], event_bus=EventBus())
    loading = asyncio.create_task(kernel.load_all())
    await asyncio.sleep(0)
    handle = kernel._handles["waiting"]
    state = handle.instance
    loading.cancel()
    try:
        await asyncio.wait_for(state["closing"].wait(), timeout=1)
    finally:
        loading.cancel()
        with pytest.raises(asyncio.CancelledError):
            await loading
    assert handle.effects.labels == ["custom:close"]
    assert not state["closed"]
    await kernel.terminate_all(force=True)
    assert state["closed"]
    assert handle.effects.labels == []
    assert kernel.states() == []


_EXPECTED_TOP_LEVEL_PLUGINS = {
    "akasha",
    "citation",
    "context_pressure",
    "default_memory",
    "desktop_pet",
    "meme",
    "novelai",
    "story",
    "observe",
    "plugin_undo",
    "qqbot",
    "setup_helper",
    "shell_restore",
    "shell_safety",
    "status_commands",
    "tool_loop_guard",
}


def test_discover_finds_all_top_level_plugins():
    """插件目录迁至仓库顶层 `plugins/` 后，内核发现路径必须能找到当前插件，且两项核心能力不再被发现。"""
    plugins_dir = REPOSITORY_ROOT / "plugins"
    kernel = make_kernel([plugins_dir], event_bus=EventBus())

    records = kernel.discover()
    names = {record.name for record in records}

    assert names == _EXPECTED_TOP_LEVEL_PLUGINS
    assert (
        next(
            record for record in records if record.name == "desktop_pet"
        ).manifest.version
        == "0.1.0"
    )
    # discover() 只报出名字证明不了入口真的存在；record.entry_file 必须是磁盘上
    # 真实存在的文件，否则装配阶段 import 会直接失败（#178 复审 #11）。
    for record in records:
        assert (
            record.entry_file.is_file()
        ), f"{record.name} 的 entry_file 不存在: {record.entry_file}"


_V2_PLUGIN = """
from agent.lifecycle.types import BeforeTurnCtx

seen: list[str] = []


class StampModule:
    async def run(self, frame):
        return frame


async def setup(ctx):
    ctx.events.on(BeforeTurnCtx, _on_turn)
    ctx.lifecycle.contribute("before_turn", [StampModule()])
    ctx.kv.set("booted", True)


async def _on_turn(event):
    seen.append(event.session_key)
    return event
""".strip()

_V2_MANIFEST = (
    "api: 2\nid: v2demo\nversion: '0.1'\n"
    "capabilities:\n  - events\n  - lifecycle\n  - kv\n"
)


def _write_v2_plugin(root: Path) -> Path:
    plugin_dir = root / "v2demo"
    (plugin_dir / "backend").mkdir(parents=True)
    (plugin_dir / "backend" / "plugin.py").write_text(_V2_PLUGIN, encoding="utf-8")
    (plugin_dir / "manifest.yaml").write_text(_V2_MANIFEST, encoding="utf-8")
    return plugin_dir


@pytest.mark.asyncio
async def test_declared_dependency_loads_first_and_its_api_is_scoped(tmp_path):
    for name, dependencies, body in (
        (
            "a_consumer",
            "[z_provider]",
            "assert ctx.dependencies.require('z_provider') == {'ready': True}",
        ),
        ("z_provider", "[]", "ctx.expose({'ready': True})"),
    ):
        package = tmp_path / name
        (package / "backend").mkdir(parents=True)
        (package / "manifest.yaml").write_text(
            f"api: 2\nid: {name}\ncapabilities: [dependencies]\ndependencies: {dependencies}\n",
            encoding="utf-8",
        )
        (package / "backend/plugin.py").write_text(
            f"async def setup(ctx):\n    {body}\n", encoding="utf-8"
        )
    kernel = make_kernel([tmp_path], event_bus=EventBus())
    await kernel.load_all()
    assert [row["id"] for row in kernel.states()] == ["z_provider", "a_consumer"]
    assert all(row["state"] == "ACTIVE" for row in kernel.states())
    await kernel.unload("z_provider")
    assert kernel.loaded_count == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("dependencies", ["[missing]", "[blocked]"])
async def test_missing_or_cyclic_dependency_blocks_setup(tmp_path, dependencies):
    package = tmp_path / "blocked"
    (package / "backend").mkdir(parents=True)
    (package / "manifest.yaml").write_text(
        f"api: 2\nid: blocked\ncapabilities: []\ndependencies: {dependencies}\n",
        encoding="utf-8",
    )
    (package / "backend/plugin.py").write_text(
        "async def setup(ctx):\n    raise AssertionError('must not run')\n",
        encoding="utf-8",
    )
    kernel = make_kernel([tmp_path], event_bus=EventBus())
    await kernel.load_all()
    assert kernel.states()[0]["state"] == "BLOCKED"
    assert kernel.states()[0]["error"]


@pytest.mark.asyncio
async def test_v2_plugin_setup_and_unload(
    tmp_path: Path, tmp_path_factory: pytest.TempPathFactory
):
    plugin_dir = _write_v2_plugin(tmp_path)
    # workspace 必须独立于插件扫描根（tmp_path），否则"kv 不写插件目录"这条
    # 断言即使内核实现退化成从插件目录派生 workspace 也检测不出来（#178 复审 #9）。
    workspace = tmp_path_factory.mktemp("v2demo-workspace")
    bus = EventBus()
    kernel = make_kernel([tmp_path], event_bus=bus, workspace=workspace)
    await kernel.load_all()

    assert kernel.loaded_count == 1
    assert [m.__class__.__name__ for m in kernel.before_turn_modules] == ["StampModule"]
    # kv 落在 workspace 而不是插件目录（issue #209）
    assert (plugin_data_dir(workspace, "v2demo") / "kv.json").exists()
    assert not (plugin_dir / ".kv.json").exists()

    import sys

    module = next(
        m
        for k, m in sys.modules.items()
        if k.startswith("akasic_plugin_") and k.endswith("_v2demo")
    )
    _ = await bus.emit(before_turn_ctx(session_key="test:v2"))
    assert module.seen == ["test:v2"]

    _ = await kernel.unload("v2demo")
    assert kernel.before_turn_modules == []
    _ = await bus.emit(before_turn_ctx(session_key="test:gone"))
    assert module.seen == ["test:v2"]


@pytest.mark.asyncio
async def test_v2_capability_gating(tmp_path: Path):
    plugin_dir = tmp_path / "gated"
    (plugin_dir / "backend").mkdir(parents=True)
    (plugin_dir / "backend" / "plugin.py").write_text(
        """
captured: dict = {}


async def setup(ctx):
    captured["granted"] = ctx.granted
    try:
        _ = ctx.tools
    except AttributeError as e:
        captured["denied"] = str(e)
""".strip(),
        encoding="utf-8",
    )
    (plugin_dir / "manifest.yaml").write_text(
        "api: 2\nid: gated\ncapabilities:\n  - events\n",
        encoding="utf-8",
    )
    kernel = make_kernel([tmp_path], event_bus=EventBus())
    await kernel.load_all()

    import sys

    module = next(
        m
        for k, m in sys.modules.items()
        if k.startswith("akasic_plugin_") and k.endswith("_gated")
    )
    assert module.captured["granted"] == ("events",)
    assert "未声明 capability" in module.captured["denied"]


@pytest.mark.asyncio
async def test_v2_setup_failure_rolls_back_effects(tmp_path: Path):
    plugin_dir = tmp_path / "v2broken"
    (plugin_dir / "backend").mkdir(parents=True)
    (plugin_dir / "backend" / "plugin.py").write_text(
        """
from agent.lifecycle.types import BeforeTurnCtx


async def setup(ctx):
    ctx.events.on(BeforeTurnCtx, _on_turn)
    raise RuntimeError("v2 boom")


async def _on_turn(event):
    event.extra_metadata["v2broken_touched"] = True
    return event
""".strip(),
        encoding="utf-8",
    )
    (plugin_dir / "manifest.yaml").write_text(
        "api: 2\nid: v2broken\ncapabilities:\n  - events\n",
        encoding="utf-8",
    )
    bus = EventBus()
    kernel = make_kernel([tmp_path], event_bus=bus)
    await kernel.load_all()

    assert kernel.loaded_count == 0
    result = await bus.emit(before_turn_ctx())
    assert "v2broken_touched" not in result.extra_metadata


@pytest.mark.asyncio
async def test_obsolete_marker_cannot_override_authoritative_config(tmp_path: Path):
    stage_plugin_package(PLUGIN_FIXTURES / "hello", tmp_path / "hello")
    (tmp_path / "hello" / "plugin.disabled").write_text("", encoding="utf-8")
    kernel = make_kernel(
        [tmp_path], event_bus=EventBus(), plugin_configs={"hello": {"enabled": True}}
    )
    await kernel.load_all()
    assert kernel.loaded_count == 1
    await kernel.terminate_all()


@pytest.mark.asyncio
async def test_config_enabled_false_skips_plugin(tmp_path: Path):
    """启停(issue #174)的来源是配置状态，不是 plugin.disabled 文件。"""
    stage_plugin_package(PLUGIN_FIXTURES / "hello", tmp_path / "hello")
    kernel = make_kernel(
        [tmp_path],
        event_bus=EventBus(),
        plugin_configs={"hello": {"enabled": False}},
    )
    await kernel.load_all()

    assert kernel.loaded_count == 0
    assert any(item["state"] == PluginState.DISABLED.name for item in kernel.states())


@pytest.mark.asyncio
async def test_config_enabled_defaults_to_true_when_absent(tmp_path: Path):
    stage_plugin_package(PLUGIN_FIXTURES / "hello", tmp_path / "hello")
    kernel = make_kernel([tmp_path], event_bus=EventBus())
    await kernel.load_all()

    assert kernel.loaded_count == 1


@pytest.mark.asyncio
async def test_duplicate_plugin_name_first_wins(tmp_path: Path):
    _ = stage_plugin_package(PLUGIN_FIXTURES / "hello", tmp_path / "hello")
    _ = stage_plugin_package(PLUGIN_FIXTURES / "weather", tmp_path / "weather")
    kernel = make_kernel([tmp_path, tmp_path], event_bus=EventBus())

    records = kernel.discover()

    # 同一目录被列两次，同名插件只应出现一次
    assert {r.name for r in records} == {"hello", "weather"}
    assert len(records) == 2


@pytest.mark.asyncio
async def test_runtime_disable_then_enable(tmp_path: Path):
    stage_plugin_package(PLUGIN_FIXTURES / "hello", tmp_path / "hello")
    bus = EventBus()
    kernel = make_kernel([tmp_path], event_bus=bus)
    await kernel.load_all()
    assert kernel.loaded_count == 1

    _ = await kernel.unload("hello")
    assert kernel.loaded_count == 0
    result = await bus.emit(before_turn_ctx())
    assert "hello_touched" not in result.extra_metadata

    # 重新启用后行为恢复
    assert await kernel.load("hello") is True
    assert kernel.loaded_count == 1
    result = await bus.emit(before_turn_ctx())
    assert result.extra_metadata.get("hello_touched") is True


@pytest.mark.asyncio
async def test_load_all_is_idempotent(tmp_path: Path):
    stage_plugin_package(PLUGIN_FIXTURES / "hello", tmp_path / "hello")
    bus = EventBus()
    kernel = make_kernel([tmp_path], event_bus=bus)
    await kernel.load_all()
    await kernel.load_all()

    assert kernel.loaded_count == 1
    result = await bus.emit(before_turn_ctx())
    # 重复 load_all 不得重复绑定 handler（否则 metadata 被写两次也看不出，改用计数）
    assert result.extra_metadata.get("hello_touched") is True


_V2_BOT_COMMANDS_PLUGIN = """
async def setup(ctx):
    ctx.bot_commands.add("chatid", "查看我的 chat_id")
""".strip()

_V2_BOT_COMMANDS_MANIFEST = "api: 2\nid: v2cmds\ncapabilities:\n  - bot_commands\n"


@pytest.mark.asyncio
async def test_bot_commands_are_scoped_contributions_only(tmp_path: Path):
    package = tmp_path / "v2cmds"
    (package / "backend").mkdir(parents=True)
    (package / "backend/plugin.py").write_text(
        _V2_BOT_COMMANDS_PLUGIN, encoding="utf-8"
    )
    (package / "manifest.yaml").write_text(_V2_BOT_COMMANDS_MANIFEST, encoding="utf-8")
    kernel = make_kernel([tmp_path], event_bus=EventBus())
    await kernel.load_all()
    assert kernel.telegram_bot_commands == [("chatid", "查看我的 chat_id")]
    await kernel.unload("v2cmds")
    assert kernel.telegram_bot_commands == []


_RPC_PLUGIN = """
async def _ping(payload):
    return {"pong": payload.get("value")}


async def setup(ctx):
    ctx.rpc.register("ping", _ping)
""".strip()

_RPC_MANIFEST = "api: 2\nid: rpcdemo\ncapabilities:\n  - rpc\n"


@pytest.mark.asyncio
async def test_v2_plugin_rpc_method_callable_then_gone_after_unload(tmp_path: Path):
    plugin_dir = tmp_path / "rpcdemo"
    (plugin_dir / "backend").mkdir(parents=True)
    (plugin_dir / "backend" / "plugin.py").write_text(_RPC_PLUGIN, encoding="utf-8")
    (plugin_dir / "manifest.yaml").write_text(_RPC_MANIFEST, encoding="utf-8")
    kernel = make_kernel([tmp_path], event_bus=EventBus())
    await kernel.load_all()

    resolved = kernel.rpc.resolve("plugin.rpcdemo.ping")
    assert resolved is not None
    _, handler = resolved
    assert await handler({"value": 1}) == {"pong": 1}

    _ = await kernel.unload("rpcdemo")

    # 插件卸载后其 RPC 方法立即不可调用
    assert kernel.rpc.resolve("plugin.rpcdemo.ping") is None


_HOST_SERVICES_PLUGIN = """
captured: dict = {}


async def setup(ctx):
    captured["workspace"] = ctx.workspace
    captured["memory_engine"] = ctx.memory_engine
    captured["session_manager"] = ctx.session_manager
    captured["light_provider"] = ctx.light_provider
    captured["light_model"] = ctx.light_model
    captured["relationship_runtime"] = ctx.relationship_runtime
""".strip()

_HOST_SERVICES_MANIFEST = (
    "api: 2\nid: hostrefs\ncapabilities:\n"
    "  - workspace\n  - memory_engine\n  - session_manager\n"
    "  - light_provider\n  - light_model\n  - relationship_runtime\n"
)


@pytest.mark.asyncio
async def test_v2_plugin_reads_host_service_references(tmp_path: Path):
    """新增 6 个直传型 capability（#183）必须原样透出 HostServices 的同名字段。"""
    plugin_dir = tmp_path / "hostrefs"
    (plugin_dir / "backend").mkdir(parents=True)
    (plugin_dir / "backend" / "plugin.py").write_text(
        _HOST_SERVICES_PLUGIN, encoding="utf-8"
    )
    (plugin_dir / "manifest.yaml").write_text(_HOST_SERVICES_MANIFEST, encoding="utf-8")
    workspace = tmp_path / "workspace-for-hostrefs"
    workspace.mkdir()
    memory_engine = object()
    session_manager = object()
    light_provider = object()
    relationship_runtime = object()
    kernel = make_kernel(
        [tmp_path],
        event_bus=EventBus(),
        workspace=workspace,
        memory_engine=memory_engine,
        session_manager=session_manager,
        light_provider=light_provider,
        light_model="light-model-x",
        relationship_runtime=relationship_runtime,
    )
    await kernel.load_all()

    import sys

    module = next(
        m
        for k, m in sys.modules.items()
        if k.startswith("akasic_plugin_") and k.endswith("_hostrefs")
    )
    assert module.captured == {
        "workspace": workspace,
        "memory_engine": memory_engine,
        "session_manager": session_manager,
        "light_provider": light_provider,
        "light_model": "light-model-x",
        "relationship_runtime": relationship_runtime,
    }


@pytest.mark.asyncio
async def test_v2_plugin_host_service_capabilities_are_gated(tmp_path: Path):
    """未在 manifest 声明的直传型 capability 访问时必须抛 CapabilityNotGranted。"""
    plugin_dir = tmp_path / "hostrefs_gated"
    (plugin_dir / "backend").mkdir(parents=True)
    (plugin_dir / "backend" / "plugin.py").write_text(
        """
captured: dict = {}


async def setup(ctx):
    try:
        _ = ctx.memory_engine
    except AttributeError as e:
        captured["denied"] = str(e)
""".strip(),
        encoding="utf-8",
    )
    (plugin_dir / "manifest.yaml").write_text(
        "api: 2\nid: hostrefs_gated\ncapabilities:\n  - workspace\n",
        encoding="utf-8",
    )
    kernel = make_kernel([tmp_path], event_bus=EventBus())
    await kernel.load_all()

    import sys

    module = next(
        m
        for k, m in sys.modules.items()
        if k.startswith("akasic_plugin_") and k.endswith("_hostrefs_gated")
    )
    assert "未声明 capability" in module.captured["denied"]


@pytest.mark.asyncio
async def test_weather_tool_via_facade(tmp_path: Path):
    stage_plugin_package(PLUGIN_FIXTURES / "weather", tmp_path / "weather")
    tools = ToolRegistry()
    kernel = make_kernel([tmp_path], event_bus=EventBus(), tools=tools)
    await kernel.load_all()
    assert tools.get_tool("get_weather") is not None
    await kernel.terminate_all()
    assert tools.get_tool("get_weather") is None


@pytest.mark.asyncio
async def test_optional_provider_lifecycle_does_not_activate_or_unload_consumer(
    tmp_path,
):
    from agent.plugin_host.dependencies import PluginDependencyError

    for name, optional, body in (
        ("consumer", "[provider]", "ctx.expose(ctx.dependencies)"),
        ("provider", "[]", "ctx.expose({'version': 'first'})"),
    ):
        package = tmp_path / name
        (package / "backend").mkdir(parents=True)
        _ = (package / "manifest.yaml").write_text(
            f"api: 2\nid: {name}\ncapabilities: [dependencies]\n"
            f"optional_dependencies: {optional}\n",
            encoding="utf-8",
        )
        _ = (package / "backend/plugin.py").write_text(
            f"async def setup(ctx):\n    {body}\n",
            encoding="utf-8",
        )
    # Disposal runs while the provider is UNLOADING, before its export is cleared.
    # Optional reads must already report it unavailable at this boundary.
    _ = (tmp_path / "provider/manifest.yaml").write_text(
        "api: 2\nid: provider\ncapabilities: [dependencies]\n"
        "optional_dependencies: [consumer]\n",
        encoding="utf-8",
    )
    _ = (tmp_path / "provider/backend/plugin.py").write_text(
        "async def setup(ctx):\n"
        "    ctx.expose({'version': 'first'})\n"
        "    def on_unload():\n"
        "        consumer = ctx.dependencies.get_optional('consumer')\n"
        "        if consumer is not None:\n"
        "            assert consumer.get_optional('provider') is None\n"
        "    ctx.effect('check-unloading', on_unload)\n",
        encoding="utf-8",
    )
    kernel = make_kernel([tmp_path], event_bus=EventBus(), namespace="optional")
    try:
        assert await kernel.load("consumer")
        consumer = kernel._dependency_api("consumer")
        assert consumer.get_optional("provider") is None
        assert [row["id"] for row in kernel.states()] == ["consumer"]
        assert await kernel.load("provider")
        first = consumer.get_optional("provider")
        assert first == {"version": "first"}
        assert await kernel.unload("provider") == []
        assert kernel.loaded_count == 1
        assert consumer.get_optional("provider") is None
        _ = (tmp_path / "provider/backend/plugin.py").write_text(
            "async def setup(ctx):\n    ctx.expose({'version': 'second-generation'})\n",
            encoding="utf-8",
        )
        assert await kernel.load("provider")
        assert consumer.get_optional("provider") == {"version": "second-generation"}
        assert consumer.get_optional("provider") is not first
        with pytest.raises(PluginDependencyError, match="未声明"):
            consumer.get_optional("undeclared")
    finally:
        await kernel.terminate_all()
    # A handle from the retired kernel cannot read any future generation's API.
    next_kernel = make_kernel(
        [tmp_path], event_bus=EventBus(), namespace="next_optional"
    )
    try:
        assert await next_kernel.load("provider")
        assert next_kernel._dependency_api("provider") == {
            "version": "second-generation"
        }
        assert consumer.get_optional("provider") is None
    finally:
        await next_kernel.terminate_all()


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["missing", "disabled", "failed", "unexported"])
async def test_optional_unavailable_exports_return_none_but_require_stays_strict(
    tmp_path, provider
):
    from agent.plugin_host.dependencies import PluginDependencyError

    package = tmp_path / "provider"
    (package / "backend").mkdir(parents=True)
    _ = (package / "manifest.yaml").write_text(
        "api: 2\nid: provider\ncapabilities: []\n",
        encoding="utf-8",
    )
    body = "raise RuntimeError('setup failure')" if provider == "failed" else "pass"
    _ = (package / "backend/plugin.py").write_text(
        f"async def setup(ctx):\n    {body}\n",
        encoding="utf-8",
    )
    kernel = make_kernel(
        [tmp_path],
        event_bus=EventBus(),
        namespace="unavailable",
        plugin_configs={"provider": {"enabled": provider != "disabled"}},
    )
    try:
        if provider != "missing":
            await kernel.load_all()
        assert kernel._dependency_api("provider", True) is None
        expected = "未导出接口" if provider == "unexported" else "不可用"
        with pytest.raises(PluginDependencyError, match=expected):
            kernel._dependency_api("provider")
    finally:
        await kernel.terminate_all()


@pytest.mark.asyncio
async def test_unsafe_strong_dependency_closure_is_rejected_before_any_effect(tmp_path):
    from agent.plugin_host import PluginRestartRequired

    for name, dependencies, safe in [
        ("provider", [], True),
        ("safe", ["provider"], True),
        ("unsafe", ["provider"], False),
    ]:
        package = tmp_path / name
        (package / "backend").mkdir(parents=True)
        (package / "manifest.yaml").write_text(
            f"api: 2\nid: {name}\ncapabilities: []\ndependencies: {dependencies}\nsupports_hot_unload: {str(safe).lower()}\n",
            encoding="utf-8",
        )
        (package / "backend/plugin.py").write_text(
            'async def setup(ctx):\n    state = []\n    ctx.expose(state)\n    ctx.effect("close", lambda: state.append("closed"))\n',
            encoding="utf-8",
        )
    kernel = make_kernel([tmp_path], event_bus=EventBus())
    await kernel.load_all()
    states = {
        name: kernel._dependency_api(name) for name in ("provider", "safe", "unsafe")
    }
    try:
        for operation in (lambda: kernel.unload("provider"), kernel.terminate_all):
            with pytest.raises(PluginRestartRequired) as caught:
                await operation()
            assert caught.value.plugin_ids == ("unsafe",)
            assert kernel.loaded_count == 3
            assert all(value == [] for value in states.values())
        await kernel.unload("safe")
        assert states["safe"] == ["closed"]
        assert states["unsafe"] == []
    finally:
        await kernel.terminate_all(force=True)
    assert all(value == ["closed"] for value in states.values())


@pytest.mark.asyncio
async def test_force_cleanup_continues_after_an_unsafe_plugin_effect_fails(tmp_path):
    for name, fail in [("one", True), ("two", False)]:
        package = tmp_path / name
        (package / "backend").mkdir(parents=True)
        (package / "manifest.yaml").write_text(
            f"api: 2\nid: {name}\ncapabilities: []\nsupports_hot_unload: false\n",
            encoding="utf-8",
        )
        body = "raise OSError('close failed')" if fail else "pass"
        (package / "backend/plugin.py").write_text(
            f'async def setup(ctx):\n    state = []\n    ctx.expose(state)\n    def close():\n        state.append("closed")\n        {body}\n    ctx.effect("close", close)\n',
            encoding="utf-8",
        )
    kernel = make_kernel([tmp_path], event_bus=EventBus())
    await kernel.load_all()
    state = {name: kernel._dependency_api(name) for name in ("one", "two")}
    with pytest.raises(ExceptionGroup, match="Plugin cleanup failed"):
        await kernel.terminate_all(force=True)
    assert state == {"one": ["closed"], "two": ["closed"]}
    assert kernel.states() == []


@pytest.mark.asyncio
async def test_unsafe_declaration_never_blocks_setup_failure_rollback(tmp_path):
    package = tmp_path / "broken"
    (package / "backend").mkdir(parents=True)
    (package / "manifest.yaml").write_text(
        "api: 2\nid: broken\ncapabilities: [events]\nsupports_hot_unload: false\n",
        encoding="utf-8",
    )
    (package / "backend/plugin.py").write_text(
        'async def setup(ctx):\n    async def on_event(event):\n        event.append("leaked")\n        return event\n    ctx.events.on(list, on_event)\n    raise RuntimeError("setup failed")\n',
        encoding="utf-8",
    )
    bus = EventBus()
    kernel = make_kernel([tmp_path], event_bus=bus)
    await kernel.load_all()
    assert kernel.states()[0]["state"] == "FAILED"
    assert await bus.emit([]) == []
    await kernel.terminate_all()


@pytest.mark.asyncio
async def test_only_manifested_v2_entries_are_loaded(tmp_path):
    for name, manifest in [
        ("missing", None),
        ("old", "api: 1\ncapabilities: []\n"),
        ("missing_setup", "api: 2\ncapabilities: []\n"),
    ]:
        package = tmp_path / name
        (package / "backend").mkdir(parents=True)
        (package / "backend/plugin.py").write_text("value = 1\n", encoding="utf-8")
        if manifest is not None:
            (package / "manifest.yaml").write_text(manifest, encoding="utf-8")
    kernel = make_kernel([tmp_path], event_bus=EventBus())
    assert [record.name for record in kernel.discover()] == ["missing_setup"]
    await kernel.load_all()
    assert kernel.loaded_count == 0
    assert kernel.states()[0]["state"] == "FAILED"
    assert "setup(ctx)" in kernel.states()[0]["error"]


@pytest.mark.asyncio
async def test_optional_unsafe_consumer_does_not_block_provider_unload(tmp_path):
    for name, body in [
        ("consumer", "supports_hot_unload: false\noptional_dependencies: [provider]\n"),
        ("provider", ""),
    ]:
        package = tmp_path / name
        (package / "backend").mkdir(parents=True)
        (package / "backend/plugin.py").write_text(
            "async def setup(ctx):\n    pass\n", encoding="utf-8"
        )
        (package / "manifest.yaml").write_text(
            f"api: 2\nid: {name}\ncapabilities: []\n" + body, encoding="utf-8"
        )
    kernel = make_kernel([tmp_path], event_bus=EventBus())
    await kernel.load_all()
    try:
        assert await kernel.unload("provider") == []
        assert kernel.loaded_count == 1
        assert kernel.states()[0]["id"] == "consumer"
    finally:
        await kernel.terminate_all(force=True)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "replacement",
    [
        "runtime_api: '>=3.0.0 <4.0.0'",
        "renderer: {surface: {entry: missing.mjs, css: []}}",
        "host_dependencies: {python: [not-installed]}",
        "capabilities: [unknown]",
    ],
)
async def test_contract_rejection_precedes_backend_execution(
    contract_package, replacement
):
    import yaml

    path = contract_package / "manifest.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    raw.update(yaml.safe_load(replacement))
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    marker = contract_package / "executed.txt"
    (contract_package / "backend/plugin.py").write_text(
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('executed', encoding='utf-8')\n"
        "async def setup(ctx): pass\n",
        encoding="utf-8",
    )
    kernel = make_kernel([contract_package.parent], event_bus=EventBus())
    await kernel.load_all()
    assert not marker.exists()
    assert kernel.states()[0]["state"] == "BLOCKED"
    assert kernel.states()[0]["diagnostic"]["stage"] == "validation"
    assert kernel.discover()[0].manifest.id == "external_demo"


@pytest.mark.asyncio
async def test_contract_package_activates_after_preflight(contract_package):
    kernel = make_kernel([contract_package.parent], event_bus=EventBus())
    await kernel.load_all()
    assert kernel.states()[0]["state"] == "ACTIVE"
    await kernel.terminate_all(force=True)


@pytest.mark.asyncio
async def test_runtime_contract_error_still_rolls_back_failed_setup(contract_package):
    (contract_package / "backend/plugin.py").write_text(
        "from agent.plugin_host.diagnostics import PackageContractError\n"
        "async def setup(ctx):\n"
        "    values = []\n"
        "    ctx.expose(values)\n"
        "    ctx.effect('cleanup', lambda: values.append('disposed'))\n"
        "    raise PackageContractError('test', 'test', 'runtime failure')\n",
        encoding="utf-8",
    )
    kernel = make_kernel([contract_package.parent], event_bus=EventBus())
    await kernel.load_all()
    assert kernel.states()[0]["state"] == "FAILED"
    assert kernel._handles["external_demo"].effects.labels == []
    assert kernel.states()[0]["diagnostic"] is None


@pytest.mark.asyncio
async def test_contract_package_uses_explicit_host_build_inventory(contract_package):
    import yaml

    from agent.plugin_host import HostServices, PluginKernel
    from agent.plugin_host.host_contract import HostRuntimeContract

    path = contract_package / "manifest.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    raw["host_dependencies"] = {"python": ["host-build-library"]}
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    kernel = PluginKernel(
        [contract_package.parent],
        services=HostServices(
            event_bus=EventBus(),
            plugin_runtime_contract=HostRuntimeContract(
                python_dependencies=frozenset({"host-build-library"})
            ),
        ),
    )
    await kernel.load_all()
    assert kernel.states()[0]["state"] == "ACTIVE"
    await kernel.terminate_all(force=True)
