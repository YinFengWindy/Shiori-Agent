"""内核行为：发现、v2 装配、capability 门控、启停与聚合面。"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from agent.plugin_host import PluginState
from agent.plugin_host import HostServices, PluginKernel
from agent.plugin_host.package_fingerprint import inspect_package_content
from agent.plugin_host.trust_store import PluginTrustStore
from agent.plugin_host.trusted_imports import TrustedPluginImports
from agent.plugin_host.plugin_data import plugin_data_dir
from agent.tools.registry import ToolRegistry
from bus.event_bus import EventBus
import sys

from tests.backend.agent.plugin_host.conftest import (
    REPOSITORY_ROOT,
    before_turn_ctx,
    make_kernel,
    stage_plugin_package,
    PLUGIN_FIXTURES,
)


@pytest.mark.asyncio
async def test_external_source_import_boundary_is_reclaimed_with_plugin_effects(
    contract_package, tmp_path
):
    approved = inspect_package_content(contract_package)
    PluginTrustStore(tmp_path).approve(contract_package, approved.fingerprint)
    kernel = PluginKernel(
        [tmp_path],
        external_plugin_dirs=[tmp_path],
        services=HostServices(event_bus=EventBus(), workspace=tmp_path),
    )
    before = set(sys.meta_path)
    try:
        await kernel.load_all()
        assert kernel.loaded_count == 1
        assert any(
            isinstance(finder, TrustedPluginImports) and finder not in before
            for finder in sys.meta_path
        )
    finally:
        await kernel.terminate_all(force=True)
    assert set(sys.meta_path) == before


@pytest.mark.asyncio
async def test_replaced_plugin_consumes_migrated_config_and_kv(tmp_path, monkeypatch):
    """A replacement code package receives preserved data through real host services."""
    import shutil
    from agent.config import load_config
    from agent.plugin_host import HostServices, PluginKernel

    packages = tmp_path / "packages"
    package = packages / "folder"
    workspace = tmp_path / "workspace"
    config_path = tmp_path / "config.toml"
    config_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(
        "agent.plugin_config_migration.plugin_roots", lambda: [packages]
    )
    monkeypatch.setattr("agent.plugin_config_migration.REPOSITORY_ROOT", tmp_path)
    old = workspace / "plugins/stable-id"
    old.mkdir(parents=True)
    (old / "plugin_config.json").write_text('{"secret":"preserved"}', encoding="utf-8")
    (old / "kv.json").write_text('{"count":42}', encoding="utf-8")

    for version in (1, 2):
        if package.exists():
            shutil.rmtree(package)
        (package / "backend").mkdir(parents=True)
        (package / "manifest.yaml").write_text(
            "api: 2\nid: stable-id\ncapabilities: [config, kv]\n", encoding="utf-8"
        )
        (package / "backend/plugin.py").write_text(
            "async def setup(ctx):\n"
            f"    ctx.expose(({version}, ctx.config.get('secret'), ctx.kv.get('count')))\n",
            encoding="utf-8",
        )
        config = load_config(config_path, workspace=workspace)
        kernel = PluginKernel(
            [packages],
            services=HostServices(
                event_bus=EventBus(), workspace=workspace, plugin_configs=config.plugins
            ),
        )
        try:
            await kernel.load_all()
            assert kernel.loaded_count == 1
            assert kernel._dependency_api("stable-id") == (version, "preserved", 42)
        finally:
            await kernel.terminate_all(force=True)


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
    waiting = kernel._handles[str((tmp_path / "waiting").absolute())]
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
    handle = kernel._handles[str((tmp_path / "waiting").absolute())]
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
    "browser_use",
    "computer_use",
    "citation",
    "context_pressure",
    "default_memory",
    "desktop_pet",
    "feishu",
    "meme",
    "novelai",
    "story",
    "observe",
    "plugin_undo",
    "qq",
    "qqbot",
    "screen_perception",
    "setup_helper",
    "shell_restore",
    "shell_safety",
    "status_commands",
    "telegram",
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


def _stage_default_disabled_hello(root: Path) -> None:
    stage_plugin_package(PLUGIN_FIXTURES / "hello", root / "hello")
    manifest = root / "hello" / "manifest.yaml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8") + "default_enabled: false\n",
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_manifest_default_disabled_applies_when_config_has_no_flag(
    tmp_path: Path,
):
    _stage_default_disabled_hello(tmp_path)
    kernel = make_kernel([tmp_path], event_bus=EventBus())
    await kernel.load_all()

    assert kernel.loaded_count == 0
    assert [item["state"] for item in kernel.states()] == [PluginState.DISABLED.name]


@pytest.mark.asyncio
async def test_explicit_enabled_overrides_manifest_default_disabled(tmp_path: Path):
    _stage_default_disabled_hello(tmp_path)
    kernel = make_kernel(
        [tmp_path],
        event_bus=EventBus(),
        plugin_configs={"hello": {"enabled": True}},
    )
    await kernel.load_all()

    assert kernel.loaded_count == 1
    await kernel.terminate_all()


@pytest.mark.asyncio
async def test_repeated_discovery_root_is_scanned_once(tmp_path: Path):
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
    assert kernel.bot_commands == [("chatid", "查看我的 chat_id")]
    await kernel.unload("v2cmds")
    assert kernel.bot_commands == []


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


def _write_needs_config_plugin(package: Path) -> None:
    """A minimal v2 plugin whose ``setup()`` validates its own config model
    and raises when the stored value fails it — the shape every plugin that
    validates ``ctx.config`` in ``setup()`` shares (novelai, qqbot,
    tool_loop_guard)."""
    (package / "backend").mkdir(parents=True)
    (package / "manifest.yaml").write_text(
        "api: 2\nid: needs_config\ncapabilities: [config]\n"
        'config_model: "config:Config"\n',
        encoding="utf-8",
    )
    (package / "backend/config.py").write_text(
        "from pydantic import BaseModel, Field\n\n\n"
        "class Config(BaseModel):\n"
        "    limit: int = Field(default=3, ge=2)\n",
        encoding="utf-8",
    )
    (package / "backend/plugin.py").write_text(
        "from .config import Config\n\n\n"
        "async def setup(ctx):\n"
        "    Config.model_validate(ctx.config.as_dict())\n",
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_config_schema_survives_a_setup_failure_caused_by_its_own_config(
    tmp_path,
):
    """#239 修复：插件因为自己存量的配置非法而 setup() 失败时，config schema
    必须继续留在 config_schemas 里。

    修复前 schema 是作为 setup 回滚 effect 注册的：setup 一失败，
    ``_rollback_failed_load`` 调 ``handle.effects.dispose_all()`` 就把它跟着
    其它 effect 一起注销了，``plugin.config.get/set`` 立刻变回
    plugin_config_unsupported——用户唯一的出路是手改配置文件。这个洞不是
    tool_loop_guard 独有的：任何在 setup() 里校验自己 config_model 的插件
    （novelai、qqbot）都有同样的问题，所以这里用一个最小化的通用插件复现，
    不依赖任何具体插件的业务逻辑。
    """
    _write_needs_config_plugin(tmp_path / "needs_config")
    kernel = make_kernel(
        [tmp_path],
        event_bus=EventBus(),
        plugin_configs={"needs_config": {"limit": 1}},
    )
    await kernel.load_all()

    assert kernel.states()[0]["state"] == "FAILED"
    assert "limit" in kernel.states()[0]["error"]
    assert kernel.config_schemas.schema_for("needs_config") is not None

    await kernel.terminate_all(force=True)


@pytest.mark.asyncio
async def test_config_schema_is_unregistered_once_the_plugin_is_actually_disposed(
    tmp_path,
):
    """schema 的生命周期绑定的是 handle 本身被处置的那一刻（unload /
    terminate_all），而不是 setup 是否成功——这条测试覆盖 FAILED handle 被
    真正处置后 schema 也必须清理，跟前一条"设置失败但暂不处置"互补，合起来
    才是完整的生命周期证明。"""
    _write_needs_config_plugin(tmp_path / "needs_config")
    kernel = make_kernel(
        [tmp_path],
        event_bus=EventBus(),
        plugin_configs={"needs_config": {"limit": 1}},
    )
    await kernel.load_all()
    assert kernel.config_schemas.schema_for("needs_config") is not None

    await kernel.terminate_all(force=True)

    assert kernel.config_schemas.schema_for("needs_config") is None


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
    assert kernel._handles[str(contract_package.absolute())].effects.labels == []
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


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_present", [False, True])
@pytest.mark.parametrize("contract", [False, True])
async def test_plugin_dependency_rejection_keeps_contract_diagnostic(
    contract_package, provider_present, contract
):
    import yaml

    path = contract_package / "manifest.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    raw["dependencies"] = ["provider"]
    if not contract:
        del raw["package_contract"]
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    if provider_present:
        provider = contract_package.parent / "provider"
        provider.mkdir()
        (provider / "manifest.yaml").write_text(
            "api: 2\nid: provider\ncapabilities: []\n", encoding="utf-8"
        )
    marker = contract_package / "executed.txt"
    (contract_package / "backend/plugin.py").write_text(
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('executed', encoding='utf-8')\n"
        "async def setup(ctx): pass\n",
        encoding="utf-8",
    )
    kernel = make_kernel(
        [contract_package.parent],
        event_bus=EventBus(),
        plugin_configs={"provider": {"enabled": False}},
    )
    await kernel.load_all()
    assert not marker.exists()
    state = next(state for state in kernel.states() if state["id"] == "external_demo")
    assert state["state"] == "BLOCKED"
    if contract:
        assert state["diagnostic"]["code"] == (
            "dependency_unavailable" if provider_present else "missing_dependency"
        )
        assert state["diagnostic"]["stage"] == "dependency"
        assert state["diagnostic"]["field"] == "dependencies[0]"
        assert state["diagnostic"]["state"] == "BLOCKED"
        assert state["diagnostic"]["reason"] == state["error"]
    else:
        assert state["diagnostic"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled", [True, False])
async def test_external_package_never_executes_even_with_config_enablement(
    contract_package, enabled
):
    from agent.plugin_host import HostServices, PluginKernel

    marker = contract_package / "executed.txt"
    (contract_package / "backend/plugin.py").write_text(
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('imported', encoding='utf-8')\n"
        "async def setup(ctx): raise AssertionError('must not execute')\n",
        encoding="utf-8",
    )
    kernel = PluginKernel(
        [contract_package.parent],
        external_plugin_dirs=[contract_package.parent],
        strict=True,
        services=HostServices(
            event_bus=EventBus(), plugin_configs={"external_demo": {"enabled": enabled}}
        ),
    )
    await kernel.load_all()
    first = kernel.states()
    await kernel.load_all()
    assert not await kernel.load("external_demo")
    assert kernel.states() == first
    assert first[0]["state"] == "UNTRUSTED"
    assert first[0]["diagnostic"]["code"] == "trust_required"
    assert kernel.loaded_count == 0
    assert not marker.exists()
    await kernel.terminate_all(force=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("conflict", [True, False])
async def test_rejected_provider_and_dependents_never_execute(tmp_path, conflict):
    from agent.plugin_host import HostServices, PluginKernel

    builtin, external = tmp_path / "builtin", tmp_path / "workspace"
    packages = [
        (builtin / "consumer", "consumer", "dependencies: [provider]\n"),
        (external / "external-copy", "provider", ""),
    ]
    if conflict:
        packages.append((builtin / "provider", "provider", ""))
    marker = tmp_path / "executed.txt"
    for package, plugin_id, extra in packages:
        (package / "backend").mkdir(parents=True)
        (package / "manifest.yaml").write_text(
            f"api: 2\nid: {plugin_id}\ncapabilities: []\npackage_contract: 1\n"
            "version: 1.0.0\nruntime_api: '>=2.0.0 <3.0.0'\n"
            "entry: backend/plugin.py\n" + extra,
            encoding="utf-8",
        )
        (package / "backend/plugin.py").write_text(
            "from pathlib import Path\n"
            f"Path({str(marker)!r}).write_text('imported', encoding='utf-8')\n"
            "async def setup(ctx): pass\n",
            encoding="utf-8",
        )
    kernel = PluginKernel(
        [builtin, external],
        external_plugin_dirs=[external],
        services=HostServices(event_bus=EventBus()),
        strict=True,
    )
    await kernel.load_all()
    await kernel.load_all()
    states = kernel.states()
    providers = [row for row in states if row["id"] == "provider"]
    assert len(providers) == (2 if conflict else 1)
    assert {row["state"] for row in providers} == {
        "CONFLICT" if conflict else "UNTRUSTED"
    }
    assert next(row for row in states if row["id"] == "consumer")["state"] == "BLOCKED"
    assert not marker.exists()
    assert kernel.loaded_count == 0
    await kernel.terminate_all(force=True)


@pytest.mark.asyncio
async def test_identical_directory_names_keep_independent_runtime_handles(tmp_path):
    from agent.plugin_host import HostServices, PluginKernel
    from agent.plugin_host.manifest import ManifestError

    roots = [tmp_path / "a", tmp_path / "b"]
    for index, root in enumerate(roots):
        package = root / "same"
        (package / "backend").mkdir(parents=True)
        (package / "manifest.yaml").write_text(
            f"api: 2\nid: plugin_{index}\ncapabilities: []\n", encoding="utf-8"
        )
        (package / "backend/plugin.py").write_text(
            "async def setup(ctx): pass\n", encoding="utf-8"
        )
    kernel = PluginKernel(roots, services=HostServices(event_bus=EventBus()))
    await kernel.load_all()
    assert kernel.loaded_count == 2
    with pytest.raises(ManifestError, match="不唯一"):
        await kernel.unload("same")
    await kernel.unload("plugin_0")
    assert kernel.loaded_count == 1
    assert kernel.states()[0]["id"] == "plugin_1"
    await kernel.terminate_all(force=True)


@pytest.mark.asyncio
async def test_discovery_snapshot_preserves_admission_without_sharing_runtime_state(
    tmp_path,
):
    import sys

    from agent.plugin_host import HostServices, PluginKernel

    stage_plugin_package(PLUGIN_FIXTURES / "hello", tmp_path / "hello")
    first_bus, next_bus = EventBus(), EventBus()
    first = make_kernel([tmp_path], event_bus=first_bus)
    await first.load_all()
    successor = PluginKernel(
        [tmp_path],
        services=HostServices(event_bus=next_bus),
        discovery_snapshot=first.discover(),
    )
    first_record, next_record = first.discover()[0], successor.discover()[0]
    assert first_record is not next_record
    assert first_record.manifest is not next_record.manifest
    assert first_record.import_path != next_record.import_path
    # The manifest metadata contains nested lists; shallow descriptor copying
    # would let one generation silently modify another generation's snapshot.
    next_record.manifest.metadata["capabilities"].append("kv")
    assert first_record.manifest.metadata["capabilities"] == ["events"]
    await successor.load_all()
    assert first_record.import_path in sys.modules
    assert next_record.import_path in sys.modules
    try:
        await first.terminate_all(force=True)
        assert first_record.import_path not in sys.modules
        assert next_record.import_path in sys.modules
        result = await next_bus.emit(before_turn_ctx())
        assert result.extra_metadata["hello_touched"] is True
        assert successor.loaded_count == 1
    finally:
        await successor.terminate_all(force=True)


@pytest.mark.asyncio
async def test_empty_startup_snapshot_does_not_rescan_new_packages(tmp_path):
    from agent.plugin_host import HostServices, PluginKernel

    first = make_kernel([tmp_path], event_bus=EventBus())
    assert first.discover() == []
    stage_plugin_package(PLUGIN_FIXTURES / "hello", tmp_path / "hello")
    successor = PluginKernel(
        [tmp_path],
        services=HostServices(event_bus=EventBus()),
        discovery_snapshot=first.discover(),
    )
    await successor.load_all()
    assert successor.discover() == []
    assert successor.loaded_count == 0


# ── 跨进程激活事务汇总（issue #262） ────────────────────────────────────────


def _write_renderer_gated_plugin(
    directory: Path, plugin_id: str, *, renderer: str, capabilities: str = "[tools]"
) -> None:
    """Writes a plain (non package_contract) manifest declaring a renderer block.

    The generic v2 manifest loader captures every top-level key into
    ``PluginManifest.metadata`` (see ``manifest.py``'s ``_parse_manifest``)
    without validating unknown keys, so a builtin-source test plugin can
    declare ``renderer:`` and exercise ``PluginKernel``'s gating/rollback
    without any of the package-contract trust/UNTRUSTED machinery a real
    external package would need.
    """
    (directory / "backend").mkdir(parents=True)
    (directory / "manifest.yaml").write_text(
        f"api: 2\nid: {plugin_id}\ncapabilities: {capabilities}\n{renderer}",
        encoding="utf-8",
    )
    (directory / "backend/plugin.py").write_text(
        "from agent.tools.base import Tool\n\n\n"
        "class DemoTool(Tool):\n"
        f"    name = {plugin_id + '_tool'!r}\n"
        "    description = 'demo'\n"
        "    parameters = {'type': 'object', 'properties': {}}\n\n"
        "    async def execute(self, **kwargs):\n"
        "        return 'ok'\n\n\n"
        "async def setup(ctx):\n"
        "    ctx.tools.register(DemoTool())\n",
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_activation_gate_clears_only_once_every_declared_kind_confirms(tmp_path):
    tools = ToolRegistry()
    _write_renderer_gated_plugin(
        tmp_path / "gated",
        "gated",
        renderer="renderer:\n  ui: {entry: x}\n  background: {entry: y}\n",
    )
    kernel = make_kernel([tmp_path], event_bus=EventBus(), tools=tools)
    await kernel.load_all()
    handle = kernel._handles[str((tmp_path / "gated").absolute())]
    # Backend contributions are already live — AC1 only gates display.
    assert handle.state is PluginState.ACTIVE
    assert tools.get_tool("gated_tool") is not None
    assert kernel.states()[0]["pending_renderer_kinds"] == ["background", "ui"]

    token = handle.activation_token
    # An unrequired/unknown kind or plugin id is a no-op, not an error.
    assert await kernel.confirm_renderer_entry("gated", "surface", token) is False
    assert await kernel.confirm_renderer_entry("no-such-plugin", "ui", token) is False
    # A mismatched token is treated exactly like "plugin not found".
    assert await kernel.confirm_renderer_entry("gated", "ui", "wrong-token") is False

    assert await kernel.confirm_renderer_entry("gated", "ui", token) is True
    assert kernel.states()[0]["pending_renderer_kinds"] == ["background"]
    # A duplicate confirmation changes nothing and reports so.
    assert await kernel.confirm_renderer_entry("gated", "ui", token) is False

    assert await kernel.confirm_renderer_entry("gated", "background", token) is True
    assert kernel.states()[0]["pending_renderer_kinds"] == []
    assert handle.state is PluginState.ACTIVE
    await kernel.terminate_all(force=True)


@pytest.mark.asyncio
async def test_failed_renderer_entry_rolls_back_only_that_plugin(tmp_path):
    tools = ToolRegistry()
    _write_renderer_gated_plugin(
        tmp_path / "flaky", "flaky", renderer="renderer:\n  ui: {entry: x}\n"
    )
    _write_renderer_gated_plugin(
        tmp_path / "healthy", "healthy", renderer="renderer:\n  ui: {entry: x}\n"
    )
    kernel = make_kernel([tmp_path], event_bus=EventBus(), tools=tools)
    await kernel.load_all()
    flaky = kernel._handles[str((tmp_path / "flaky").absolute())]
    healthy = kernel._handles[str((tmp_path / "healthy").absolute())]
    assert flaky.state is PluginState.ACTIVE
    assert healthy.state is PluginState.ACTIVE

    flaky_candidate_id = str((tmp_path / "flaky").absolute())
    healthy_candidate_id = str((tmp_path / "healthy").absolute())
    changed = await kernel.fail_renderer_entry(
        "flaky", "ui", "module threw on import", flaky.activation_token
    )
    assert changed is True

    # The failing plugin is rolled back completely: no tool, no leftover
    # effect, no longer in the active-order aggregation (AC2/AC6).
    assert flaky.state is PluginState.FAILED
    assert flaky.effects.labels == []
    assert tools.get_tool("flaky_tool") is None
    assert flaky_candidate_id not in kernel._active_order
    states_by_id = {row["id"]: row for row in kernel.states()}
    assert states_by_id["flaky"]["diagnostic"] == {
        "code": "renderer_ui_failed",
        "stage": "ui",
        "field": "renderer.ui.entry",
        "reason": "module threw on import",
        "path": "",
        "state": "FAILED",
    }

    # The other, unrelated plugin is completely unaffected (AC3).
    assert healthy.state is PluginState.ACTIVE
    assert tools.get_tool("healthy_tool") is not None
    assert healthy_candidate_id in kernel._active_order
    await kernel.terminate_all(force=True)


@pytest.mark.asyncio
async def test_failed_renderer_entry_accepts_surface_although_not_gated(tmp_path):
    # `surface` never appears in `pending_renderer_kinds` (it loads on demand),
    # but a surface failure must still roll the whole plugin back (AC2).
    tools = ToolRegistry()
    _write_renderer_gated_plugin(
        tmp_path / "demo", "demo", renderer="renderer:\n  ui: {entry: x}\n"
    )
    kernel = make_kernel([tmp_path], event_bus=EventBus(), tools=tools)
    await kernel.load_all()
    assert kernel.states()[0]["pending_renderer_kinds"] == ["ui"]
    handle = kernel._handles[str((tmp_path / "demo").absolute())]

    assert (
        await kernel.fail_renderer_entry(
            "demo", "surface", "window crashed", handle.activation_token
        )
        is True
    )

    assert handle.state is PluginState.FAILED
    assert tools.get_tool("demo_tool") is None
    await kernel.terminate_all(force=True)


@pytest.mark.asyncio
async def test_stale_or_unknown_activation_reports_are_ignored(tmp_path):
    _write_renderer_gated_plugin(
        tmp_path / "demo",
        "demo",
        renderer="renderer:\n  ui: {entry: x}\n",
        capabilities="[]",
    )
    kernel = make_kernel(
        [tmp_path],
        event_bus=EventBus(),
        plugin_configs={"demo": {"enabled": False}},
    )
    await kernel.load_all()
    handle = kernel._handles[str((tmp_path / "demo").absolute())]
    assert handle.state is PluginState.DISABLED

    # A report naming a plugin the kernel does not consider ACTIVE (disabled,
    # never loaded, or belonging to a superseded generation) is stale and
    # must not raise or mutate anything. The token is irrelevant here — the
    # plugin isn't ACTIVE regardless of what token accompanies the report.
    assert await kernel.confirm_renderer_entry("demo", "ui", "") is False
    assert await kernel.fail_renderer_entry("demo", "ui", "irrelevant", "") is False
    assert await kernel.fail_renderer_entry("never-existed", "ui", "n/a", "") is False
    assert handle.state is PluginState.DISABLED
    await kernel.terminate_all(force=True)


@pytest.mark.asyncio
async def test_stale_report_from_a_superseded_generation_is_ignored(tmp_path):
    """Reproduces the disable/re-enable race a plugin-id-only check misses:

    enable P (G1, ui import in flight) -> disable P (G1 disposed) -> re-enable
    P (G3, fresh handle, same plugin id, `pending_renderer_kinds={"ui"}`).
    G1's abandoned load then resolves late and reports against the *new*
    handle. Without a per-load token this would let a stale success silently
    mark G3 fully ACTIVE without G3's UI ever loading (AC1), or a stale
    failure roll back a healthy, just-re-enabled G3 plugin with a reason
    string that belongs to the discarded G1 attempt (AC2). Every real
    disable/re-enable constructs a brand new `PluginKernel` (a new
    generation, see `bootstrap/tools.py`); two separate kernels here stand in
    for G1 and G3 sharing the same plugin id and host services.
    """
    _write_renderer_gated_plugin(
        tmp_path / "demo", "demo", renderer="renderer:\n  ui: {entry: x}\n"
    )
    tools = ToolRegistry()

    # G1: loads, but nothing ever confirms its ui entry before it is disposed
    # (the disable that discards this generation).
    kernel_g1 = make_kernel([tmp_path], event_bus=EventBus(), tools=tools)
    await kernel_g1.load_all()
    stale_token = kernel_g1._handles[
        str((tmp_path / "demo").absolute())
    ].activation_token
    await kernel_g1.terminate_all(force=True)

    # G3: the re-enable — a fresh kernel, fresh handle, fresh token.
    kernel_g3 = make_kernel([tmp_path], event_bus=EventBus(), tools=tools)
    await kernel_g3.load_all()
    fresh_handle = kernel_g3._handles[str((tmp_path / "demo").absolute())]
    assert fresh_handle.activation_token != stale_token
    assert fresh_handle.pending_renderer_kinds == {"ui"}

    # G1's abandoned "ui ready" resolves late, echoing G1's token: ignored,
    # G3 keeps waiting for its own confirmation (AC1).
    changed = await kernel_g3.confirm_renderer_entry("demo", "ui", stale_token)
    assert changed is False
    assert fresh_handle.pending_renderer_kinds == {"ui"}
    assert fresh_handle.state is PluginState.ACTIVE

    # G1's abandoned failure also resolves late: ignored, G3 stays healthy
    # rather than flipping FAILED over G1's stale reason (AC2).
    changed = await kernel_g3.fail_renderer_entry(
        "demo", "ui", "stale failure from a discarded attempt", stale_token
    )
    assert changed is False
    assert fresh_handle.state is PluginState.ACTIVE
    assert tools.get_tool("demo_tool") is not None

    # G3's own, current-generation report still works normally.
    changed = await kernel_g3.confirm_renderer_entry(
        "demo", "ui", fresh_handle.activation_token
    )
    assert changed is True
    assert fresh_handle.pending_renderer_kinds == frozenset()
    await kernel_g3.terminate_all(force=True)


@pytest.mark.asyncio
async def test_concurrent_failure_reports_for_the_same_plugin_clean_up_exactly_once(
    tmp_path,
):
    """Two renderer processes (e.g. ui and background) can both fail near-
    simultaneously; the resulting rollback must still be clean and single
    (AC7 — "并发事件到达时的清理")."""
    tools = ToolRegistry()
    _write_renderer_gated_plugin(
        tmp_path / "demo",
        "demo",
        renderer="renderer:\n  ui: {entry: x}\n  background: {entry: y}\n",
    )
    kernel = make_kernel([tmp_path], event_bus=EventBus(), tools=tools)
    await kernel.load_all()
    handle = kernel._handles[str((tmp_path / "demo").absolute())]
    assert handle.state is PluginState.ACTIVE

    token = handle.activation_token
    results = await asyncio.gather(
        kernel.fail_renderer_entry("demo", "ui", "ui failed", token),
        kernel.fail_renderer_entry("demo", "background", "background failed", token),
    )
    assert sorted(results) == [False, True]
    assert handle.state is PluginState.FAILED
    assert handle.effects.labels == []
    assert tools.get_tool("demo_tool") is None
    assert kernel._active_order == []
    await kernel.terminate_all(force=True)


@pytest.mark.asyncio
async def test_rollback_that_cannot_dispose_every_effect_requires_a_restart(tmp_path):
    """A setup-time failure whose own rollback cannot fully dispose its
    effects must not offer an unsafe immediate retry (RESTART_REQUIRED,
    distinct from FAILED) — exercised through the same `_rollback_failed_load`
    core `fail_renderer_entry` reuses."""
    package = tmp_path / "unclean"
    (package / "backend").mkdir(parents=True)
    (package / "manifest.yaml").write_text(
        "api: 2\nid: unclean\ncapabilities: []\n", encoding="utf-8"
    )
    (package / "backend/plugin.py").write_text(
        "async def setup(ctx):\n"
        "    ctx.effect('poison', lambda: (_ for _ in ()).throw(RuntimeError('stuck')))\n"
        "    raise RuntimeError('setup failed after registering a bad effect')\n",
        encoding="utf-8",
    )
    kernel = make_kernel([tmp_path], event_bus=EventBus())
    await kernel.load_all()
    handle = kernel._handles[str(package.absolute())]
    assert handle.state is PluginState.RESTART_REQUIRED
    await kernel.terminate_all(force=True)


_CHANNEL_PLUGIN = """
class _Channel:
    def __init__(self, name):
        self.name = name

async def setup(ctx):
    ctx.channels.add(_Channel("declared"))
    ctx.channels.add(_Channel({second!r}))
""".strip()


def _write_channel_plugin(root: Path, plugin_id: str, second: str) -> None:
    package = root / plugin_id
    (package / "backend").mkdir(parents=True)
    (package / "backend/plugin.py").write_text(
        _CHANNEL_PLUGIN.format(second=second), encoding="utf-8"
    )
    (package / "manifest.yaml").write_text(
        f"api: 2\nid: {plugin_id}\ncapabilities: [channels]\nchannels:\n"
        "  - {name: declared, label: Declared}\n"
        "  - {name: also_declared, label: Also}\n",
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_declared_channels_are_contributed(tmp_path: Path):
    _write_channel_plugin(tmp_path, "chan", "also_declared")
    kernel = make_kernel([tmp_path], event_bus=EventBus())
    await kernel.load_all()
    try:
        assert [channel.name for channel in kernel.channels] == [
            "declared",
            "also_declared",
        ]
    finally:
        await kernel.terminate_all(force=True)


@pytest.mark.asyncio
async def test_undeclared_channel_fails_activation_with_diagnostic(tmp_path: Path):
    _write_channel_plugin(tmp_path, "chan", "sneaky")
    kernel = make_kernel([tmp_path], event_bus=EventBus())
    await kernel.load_all()
    try:
        assert kernel.channels == []
        [state] = kernel.states()
        assert state["state"] == "FAILED"
        assert state["diagnostic"]["code"] == "undeclared_channel"
        assert state["diagnostic"]["state"] == "FAILED"
        assert "sneaky" in state["diagnostic"]["reason"]
    finally:
        await kernel.terminate_all(force=True)


@pytest.mark.asyncio
async def test_plugins_declaring_one_channel_both_stay_inactive(tmp_path: Path):
    _write_channel_plugin(tmp_path, "first", "also_declared")
    _write_channel_plugin(tmp_path, "second", "also_declared")
    kernel = make_kernel([tmp_path], event_bus=EventBus())
    await kernel.load_all()
    try:
        assert kernel.loaded_count == 0
        assert kernel.channels == []
        assert {state["state"] for state in kernel.states()} == {"CONFLICT"}
        assert {state["diagnostic"]["code"] for state in kernel.states()} == {
            "duplicate_channel"
        }
    finally:
        await kernel.terminate_all(force=True)
