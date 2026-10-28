"""内核行为：发现、v2 装配、capability 门控、启停与聚合面。"""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

import pytest

from agent.plugin_host import PluginState
from agent.plugin_host import PluginGenerationSettings, PluginRpcRegistry
from shiori_sdk.core.services import LIGHT_PROVIDER
from agent.plugin_host.manifest import group_listening_channels
from agent.plugin_host.package_fingerprint import inspect_package_content
from agent.plugin_host.trust_store import PluginTrustStore
from agent.plugin_host.trusted_imports import TrustedPluginImports
from shiori_sdk.kernel import PluginFailed
from shiori_sdk.storage import plugin_data_dir
from core.roles.store import RoleStore
from agent.tools.registry import ToolRegistry
from conversation.commands import command_menu
from core.accounts.plugin_capability import (
    drop_plugin_accounts,
    publish_plugin_accounts,
)
from core.channels.plugin_capability import active_plugin_channels
from bus.event_bus import EventBus
import sys

from shiori_sdk.testing.external_turns import FakeExternalTurns
from shiori_sdk.testing.background_results import FakeBackgroundResults
from shiori_sdk.testing.packages import stage_plugin_package
from tests.support.plugin_kernel import (
    REPOSITORY_ROOT,
    before_turn_ctx,
    host_kernel,
    make_kernel,
    PLUGIN_FIXTURES,
)


@pytest.mark.asyncio
async def test_account_test_plugin_reports_and_withdraws_live_state(tmp_path):
    package = tmp_path / "account_demo"
    (package / "backend").mkdir(parents=True)
    (package / "manifest.yaml").write_text(
        "api: 4\nsdk: '>=4.0.0'\nid: account_demo\ninject: [accounts]\n",
        encoding="utf-8",
    )
    (package / "backend/plugin.py").write_text(
        "from shiori_sdk.core.services import ACCOUNTS\n"
        "async def setup(ctx):\n"
        "    accounts = ctx.require(ACCOUNTS)\n"
        "    first = accounts.register(platform='demo', "
        "platform_account_id='101', config_ref='one', role_id='mira', "
        "display_name='One')\n"
        "    second = accounts.register(platform='demo', "
        "platform_account_id='102', config_ref='two', role_id='other', "
        "display_name='Two')\n"
        "    accounts.report(first.record.id, connection='online', "
        "capabilities=frozenset({'contacts'}))\n"
        "    accounts.report(second.record.id, connection='login_required')\n"
        "    accounts.unregister(second.record.id)\n"
        "    second = accounts.register(platform='demo', "
        "platform_account_id='102', config_ref='two', role_id='other', "
        "display_name='Two')\n"
        "    accounts.report(second.record.id, connection='login_required')\n"
        "    ctx.expose((first.record.id, second.record.id))\n",
        encoding="utf-8",
    )
    workspace = tmp_path / "workspace"
    role_store = RoleStore(workspace)
    for role_id in ("mira", "other"):
        role_store.create_role(role_id=role_id, name=role_id, system_prompt=role_id)
    first_kernel = host_kernel(
        [tmp_path],
        settings=PluginGenerationSettings(workspace=workspace),
        role_store=role_store,
    )
    await first_kernel.load_all()
    publish_plugin_accounts(first_kernel.kernel)
    assert first_kernel.loaded_count == 1
    first, second = first_kernel._dependency_api("account_demo")
    assert role_store.accounts.get(first).connection == "online"
    assert role_store.accounts.get(first).capabilities == frozenset({"contacts"})
    assert role_store.accounts.get(second).connection == "login_required"

    discarded = host_kernel(
        [tmp_path],
        settings=PluginGenerationSettings(
            workspace=workspace,
            plugin_configs={"account_demo": {"enabled": False}},
            is_reload=True,
        ),
        role_store=role_store,
    )
    await discarded.load_all()
    assert role_store.accounts.get(first).connection == "online"
    await discarded.terminate_all(force=True)
    drop_plugin_accounts(discarded.kernel)
    assert role_store.accounts.get(first).connection == "online"

    replacement = host_kernel(
        [tmp_path],
        settings=PluginGenerationSettings(workspace=workspace, is_reload=True),
        role_store=role_store,
    )
    await replacement.load_all()
    assert replacement._dependency_api("account_demo") == (first, second)
    assert role_store.accounts.get(first).connection == "online"
    assert role_store.accounts.get(first).runtime_active
    publish_plugin_accounts(replacement.kernel)
    await first_kernel.terminate_all(force=True)
    drop_plugin_accounts(first_kernel.kernel)
    assert role_store.accounts.get(first).runtime_active
    # The unloaded plugin's accounts leave the index instead of lingering.
    await replacement.terminate_all(force=True)
    drop_plugin_accounts(replacement.kernel)
    assert role_store.accounts.list() == []

    disabled = host_kernel(
        [tmp_path],
        settings=PluginGenerationSettings(
            workspace=workspace, plugin_configs={"account_demo": {"enabled": False}}
        ),
        role_store=role_store,
    )
    await disabled.load_all()
    assert role_store.accounts.list() == []


@pytest.mark.asyncio
async def test_failed_account_plugin_setup_discards_unpublished_identity(tmp_path):
    package = tmp_path / "failed_account_demo"
    (package / "backend").mkdir(parents=True)
    (package / "manifest.yaml").write_text(
        "api: 4\nsdk: '>=4.0.0'\nid: failed_account_demo\ninject: [accounts]\n",
        encoding="utf-8",
    )
    (package / "backend/plugin.py").write_text(
        "from shiori_sdk.core.services import ACCOUNTS\n"
        "async def setup(ctx):\n"
        "    ctx.require(ACCOUNTS).register(platform='demo', "
        "platform_account_id='101', config_ref='one', role_id='mira')\n"
        "    raise RuntimeError('setup failed')\n",
        encoding="utf-8",
    )
    workspace = tmp_path / "workspace"
    role_store = RoleStore(workspace)
    role_store.create_role(role_id="mira", name="Mira", system_prompt="Mira")
    kernel = host_kernel(
        [tmp_path],
        settings=PluginGenerationSettings(workspace=workspace),
        role_store=role_store,
    )
    await kernel.load_all()
    assert kernel.loaded_count == 0
    assert role_store.accounts.list() == []
    assert RoleStore(workspace).accounts.list() == []


@pytest.mark.asyncio
async def test_external_source_import_boundary_is_reclaimed_with_plugin_effects(
    contract_package, tmp_path
):
    approved = inspect_package_content(contract_package)
    PluginTrustStore(tmp_path).approve(contract_package, approved.fingerprint)
    kernel = host_kernel(
        [tmp_path],
        external_plugin_dirs=[tmp_path],
        settings=PluginGenerationSettings(workspace=tmp_path),
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
@pytest.mark.parametrize("strict", [False, True])
async def test_setup_cancellation_rolls_back_before_force_cleanup(tmp_path, strict):
    # ``zlater`` is ordered after ``waiting``, so the cancelled start never
    # reaches it.
    for name in ("active", "waiting", "zlater"):
        package = tmp_path / name
        (package / "backend").mkdir(parents=True)
        (package / "manifest.yaml").write_text(
            f"api: 4\nsdk: '>=4.0.0'\nid: {name}\ninject: [events]\nsupports_hot_unload: false\n",
            encoding="utf-8",
        )
        (package / "backend/plugin.py").write_text(
            "import asyncio\n"
            "from shiori_sdk.core.services import EVENTS\n"
            "async def setup(ctx):\n"
            "    state = ['started']\n"
            "    ctx.expose(state)\n"
            "    ctx.effect('close', lambda: state.append('closed'))\n"
            "    async def on_event(event):\n"
            f"        event.append('{name}')\n"
            "        return event\n"
            "    ctx.require(EVENTS).on(list, on_event)\n"
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
    loading.cancel()
    with pytest.raises(asyncio.CancelledError):
        await loading
    try:
        assert state == ["started", "closed"]
        assert waiting.effects.labels == []
        assert waiting.state is PluginState.FAILED
        assert isinstance(waiting.error, asyncio.CancelledError)
        assert str((tmp_path / "zlater").absolute()) not in kernel._handles
        # Neither the cancelled plugin nor the unreached one is left runnable.
        await kernel.kernel.start([])
        assert kernel.kernel.status("zlater") is None
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
    (broken / "manifest.yaml").write_text(
        "api: 4\nsdk: '>=4.0.0'\ncapabilities: [\n", encoding="utf-8"
    )
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


@pytest.mark.parametrize(
    ("lines", "message"),
    [
        ("capabilities: []\n", "capabilities"),
        ("inject:\n  - host.tools\n", "inject 不能声明宿主内部 Key"),
        ("optional_inject:\n  - host.bridge\n", "optional_inject 不能声明宿主内部 Key"),
        ("provides:\n  - host.rpc\n", "provides 不能声明宿主内部 Key"),
    ],
)
def test_api_4_manifest_rejects_capabilities_and_host_keys(
    tmp_path: Path, lines: str, message: str
):
    """``host.*`` keys hold raw binders that could act as another plugin."""
    from agent.plugin_host.manifest import ManifestError, load_manifest

    (tmp_path / "manifest.yaml").write_text(
        "api: 4\nsdk: '>=4.0.0'\nid: demo\n" + lines, encoding="utf-8"
    )
    with pytest.raises(ManifestError, match=message):
        load_manifest(tmp_path)


@pytest.mark.asyncio
async def test_api_4_require_tools_registers_and_dispose_clears(tmp_path: Path):
    """ctx.require(TOOLS) reaches the host registry, and dispose unregisters it."""
    package = tmp_path / "demo"
    (package / "backend").mkdir(parents=True)
    (package / "manifest.yaml").write_text(
        "api: 4\nsdk: '>=4.0.0'\nid: demo\ninject:\n  - tools\n", encoding="utf-8"
    )
    (package / "backend/plugin.py").write_text(
        "from shiori_sdk.core.services import TOOLS\n"
        "from shiori_sdk.tools import Tool\n"
        "\n"
        "class DemoTool(Tool):\n"
        "    name = 'demo_tool'\n"
        "    description = 'demo'\n"
        "    parameters = {'type': 'object', 'properties': {}}\n"
        "\n"
        "    async def execute(self, **kwargs):\n"
        "        return 'ok'\n"
        "\n"
        "async def setup(ctx):\n"
        "    ctx.require(TOOLS).register(DemoTool())\n",
        encoding="utf-8",
    )
    tools = ToolRegistry()
    kernel = make_kernel([tmp_path], event_bus=EventBus(), tools=tools)
    await kernel.load_all()
    assert tools.get_tool("demo_tool") is not None
    await kernel.terminate_all(force=True)
    assert tools.get_tool("demo_tool") is None


@pytest.mark.asyncio
async def test_force_cleanup_recovers_effects_after_rollback_is_cancelled(tmp_path):
    package = tmp_path / "waiting"
    (package / "backend").mkdir(parents=True)
    (package / "manifest.yaml").write_text(
        "api: 4\nsdk: '>=4.0.0'\nsupports_hot_unload: false\n", encoding="utf-8"
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
    "browser_use",
    "computer_use",
    "context_pressure",
    "default_memory",
    "desktop_pet",
    "feishu",
    "gpt_sovits_tts",
    "grok_bot",
    "herdr",
    "meme",
    "novelai",
    "story",
    "observe",
    "plugin_undo",
    "qq",
    "qqbot",
    "screen_perception",
    "sensevoice_asr",
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
        == "0.1.1"
    )
    # discover() 只报出名字证明不了入口真的存在；record.entry_file 必须是磁盘上
    # 真实存在的文件，否则装配阶段 import 会直接失败（#178 复审 #11）。
    for record in records:
        assert (
            record.entry_file.is_file()
        ), f"{record.name} 的 entry_file 不存在: {record.entry_file}"


_EVENTS_KV_PLUGIN = """
from agent.lifecycle.types import BeforeTurnCtx
from shiori_sdk.core.services import EVENTS, KV

seen: list[str] = []


async def setup(ctx):
    ctx.require(EVENTS).on(BeforeTurnCtx, _on_turn)
    ctx.require(KV).set("booted", True)


async def _on_turn(event):
    seen.append(event.session_key)
    return event
""".strip()

_EVENTS_KV_MANIFEST = (
    "api: 4\nsdk: '>=4.0.0'\nid: kvdemo\nversion: '0.1'\ninject:\n  - events\n  - kv\n"
)


def _write_kv_plugin(root: Path) -> Path:
    plugin_dir = root / "kvdemo"
    (plugin_dir / "backend").mkdir(parents=True)
    (plugin_dir / "backend" / "plugin.py").write_text(
        _EVENTS_KV_PLUGIN, encoding="utf-8"
    )
    (plugin_dir / "manifest.yaml").write_text(_EVENTS_KV_MANIFEST, encoding="utf-8")
    return plugin_dir


@pytest.mark.asyncio
async def test_declared_dependency_loads_first_and_its_api_is_scoped(tmp_path):
    for name, dependencies, body in (
        (
            "a_consumer",
            "[z_provider]",
            "assert ctx.require(DEPENDENCIES).require('z_provider') == {'ready': True}",
        ),
        ("z_provider", "[]", "ctx.expose({'ready': True})"),
    ):
        package = tmp_path / name
        (package / "backend").mkdir(parents=True)
        (package / "manifest.yaml").write_text(
            f"api: 4\nsdk: '>=4.0.0'\nid: {name}\n"
            f"inject: [dependencies]\ndependencies: {dependencies}\n",
            encoding="utf-8",
        )
        (package / "backend/plugin.py").write_text(
            "from shiori_sdk.core.services import DEPENDENCIES\n"
            f"async def setup(ctx):\n    {body}\n",
            encoding="utf-8",
        )
    kernel = make_kernel([tmp_path], event_bus=EventBus())
    await kernel.load_all()
    assert [row["id"] for row in kernel.states()] == ["z_provider", "a_consumer"]
    assert all(row["state"] == "ACTIVE" for row in kernel.states())
    await kernel.unload("z_provider")
    assert kernel.loaded_count == 0


@pytest.mark.asyncio
async def test_enabled_plugin_cycled_with_a_disabled_one_is_not_a_dependency_cycle(
    tmp_path: Path,
):
    for name, dependencies in (("enabled", "[disabled]"), ("disabled", "[enabled]")):
        package = tmp_path / name
        (package / "backend").mkdir(parents=True)
        (package / "manifest.yaml").write_text(
            f"api: 4\nsdk: '>=4.0.0'\nid: {name}\ndependencies: {dependencies}\n",
            encoding="utf-8",
        )
        (package / "backend/plugin.py").write_text(
            "async def setup(ctx):\n    raise AssertionError('must not run')\n",
            encoding="utf-8",
        )
    kernel = make_kernel(
        [tmp_path],
        event_bus=EventBus(),
        plugin_configs={"disabled": {"enabled": False}},
    )
    await kernel.load_all()

    states = {item["id"]: item for item in kernel.states()}
    assert states["disabled"]["state"] == "DISABLED"
    assert states["enabled"]["state"] == "BLOCKED"
    assert (
        states["enabled"]["error"]
        == "插件 enabled 依赖的 plugin:disabled 未启用或加载失败"
    )
    assert kernel.kernel.status("disabled") is None
    enabled = kernel.kernel.status("enabled")
    assert enabled is not None and enabled.diagnostic is not None
    assert enabled.diagnostic.code == "dependency_unavailable"


@pytest.mark.asyncio
@pytest.mark.parametrize("dependencies", ["[missing]", "[blocked]"])
async def test_missing_or_cyclic_dependency_blocks_setup(tmp_path, dependencies):
    package = tmp_path / "blocked"
    (package / "backend").mkdir(parents=True)
    (package / "manifest.yaml").write_text(
        f"api: 4\nsdk: '>=4.0.0'\nid: blocked\ndependencies: {dependencies}\n",
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
async def test_uninstalled_external_source_is_never_a_kernel_candidate(
    contract_package, tmp_path
):
    dependent = tmp_path / "dependent"
    shutil.copytree(contract_package, dependent)
    path = dependent / "manifest.yaml"
    path.write_text(
        path.read_text(encoding="utf-8").replace("id: external_demo", "id: dependent")
        + "dependencies: [external_demo]\n",
        encoding="utf-8",
    )
    path = contract_package / "manifest.yaml"
    path.write_text(
        "api: 4\nsdk: '>=4.0.0'\nid: external_demo\nversion: 1.2.3\nentry: backend/plugin.py\n"
        "distribution: external\ninject: [channels]\n"
        "contributes:\n  channels:\n"
        "    - {name: listens, label: L, group_listening: true,"
        " chat_types: [{type: private, label: P, chat_id_label: ID}]}\n",
        encoding="utf-8",
    )
    (contract_package / "backend/plugin.py").write_text(
        "raise RuntimeError('source copy must not be imported')\n", encoding="utf-8"
    )
    kernel = make_kernel([tmp_path], event_bus=EventBus())
    try:
        await kernel.load_all()
        assert [record.manifest.id for record in kernel.discover()] == ["dependent"]
        [state] = kernel.states()
        assert state["id"] == "dependent" and state["state"] == "BLOCKED"
        # Same verdict as discovery-time checks: the source provides nothing.
        assert state["diagnostic"]["code"] == "missing_dependency"
        supports = group_listening_channels(
            record.manifest for record in kernel.discover()
        )
        assert not supports("listens")
        [source] = kernel.uninstalled_external_sources()
        assert source.plugin_dir == contract_package
        assert source.diagnostic.code == "external_not_installed"
    finally:
        await kernel.terminate_all(force=True)


@pytest.mark.asyncio
async def test_plugin_setup_and_unload(
    tmp_path: Path, tmp_path_factory: pytest.TempPathFactory
):
    plugin_dir = _write_kv_plugin(tmp_path)
    # workspace 必须独立于插件扫描根（tmp_path），否则"kv 不写插件目录"这条
    # 断言即使内核实现退化成从插件目录派生 workspace 也检测不出来（#178 复审 #9）。
    workspace = tmp_path_factory.mktemp("kvdemo-workspace")
    bus = EventBus()
    kernel = make_kernel([tmp_path], event_bus=bus, workspace=workspace)
    await kernel.load_all()

    assert kernel.loaded_count == 1
    # kv 落在 workspace 而不是插件目录（issue #209）
    assert (plugin_data_dir(workspace, "kvdemo") / "kv.json").exists()
    assert not (plugin_dir / ".kv.json").exists()

    import sys

    module = next(
        m
        for k, m in sys.modules.items()
        if k.startswith("akasic_plugin_") and k.endswith("_kvdemo")
    )
    _ = await bus.emit(before_turn_ctx(session_key="test:v2"))
    assert module.seen == ["test:v2"]

    _ = await kernel.unload("kvdemo")
    _ = await bus.emit(before_turn_ctx(session_key="test:gone"))
    assert module.seen == ["test:v2"]


@pytest.mark.asyncio
async def test_undeclared_keys_are_refused_at_setup(tmp_path: Path):
    """A ``host.`` name is never declarable, so providing one is refused too."""
    plugin_dir = tmp_path / "gated"
    (plugin_dir / "backend").mkdir(parents=True)
    (plugin_dir / "backend" / "plugin.py").write_text(
        """
from shiori_sdk.core.services import TOOLS
from shiori_sdk.kernel import Key

captured: dict = {}


async def setup(ctx):
    try:
        ctx.require(TOOLS)
    except Exception as e:
        captured["denied"] = str(e)
    try:
        ctx.provide(Key("host.bridge"), object())
    except Exception as e:
        captured["provide"] = e
""".strip(),
        encoding="utf-8",
    )
    (plugin_dir / "manifest.yaml").write_text(
        "api: 4\nsdk: '>=4.0.0'\nid: gated\ninject:\n  - events\n",
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
    assert "未在 manifest inject 中声明 tools" in module.captured["denied"]
    assert module.captured["provide"].diagnostic.code == "undeclared_key"
    assert kernel.kernel._providers["host.bridge"] == ("", kernel._rpc)
    await kernel.terminate_all(force=True)


@pytest.mark.asyncio
async def test_setup_failure_rolls_back_effects(tmp_path: Path):
    plugin_dir = tmp_path / "rollback_demo"
    (plugin_dir / "backend").mkdir(parents=True)
    (plugin_dir / "backend" / "plugin.py").write_text(
        """
from agent.lifecycle.types import BeforeTurnCtx
from shiori_sdk.core.services import EVENTS


async def setup(ctx):
    ctx.require(EVENTS).on(BeforeTurnCtx, _on_turn)
    raise RuntimeError("v2 boom")


async def _on_turn(event):
    event.extra_metadata["rollback_demo_touched"] = True
    return event
""".strip(),
        encoding="utf-8",
    )
    (plugin_dir / "manifest.yaml").write_text(
        "api: 4\nsdk: '>=4.0.0'\nid: rollback_demo\ninject:\n  - events\n",
        encoding="utf-8",
    )
    bus = EventBus()
    kernel = make_kernel([tmp_path], event_bus=bus)
    await kernel.load_all()

    assert kernel.loaded_count == 0
    result = await bus.emit(before_turn_ctx())
    assert "rollback_demo_touched" not in result.extra_metadata


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


_COMMANDS_PLUGIN = """
from shiori_sdk.core.conversation import COMMANDS


async def chatid(command):
    return command.session_key


async def setup(ctx):
    remove = ctx.require(COMMANDS).register(
        "chatid", chatid, description="查看我的 chat_id"
    )
    ctx.effect("command:chatid", remove)
""".strip()

_COMMANDS_MANIFEST = "api: 4\nsdk: '>=4.0.0'\nid: {id}\ninject:\n  - commands\n"


@pytest.mark.asyncio
async def test_injected_commands_reach_the_menu_until_unload(tmp_path: Path):
    # Both register /chatid: v2cmds sets up first (id order), the duplicate fails.
    for plugin_id in ("v2cmds", "v2cmds_dup"):
        package = tmp_path / plugin_id
        (package / "backend").mkdir(parents=True)
        (package / "backend/plugin.py").write_text(_COMMANDS_PLUGIN, encoding="utf-8")
        (package / "manifest.yaml").write_text(
            _COMMANDS_MANIFEST.format(id=plugin_id), encoding="utf-8"
        )
    kernel = make_kernel([tmp_path], event_bus=EventBus())
    await kernel.load_all()
    states = {row["id"]: row for row in kernel.states()}
    assert states["v2cmds"]["state"] == "ACTIVE"
    assert states["v2cmds_dup"]["state"] == "FAILED"
    assert "/chatid" in states["v2cmds_dup"]["error"]
    assert command_menu(kernel.kernel) == [("chatid", "查看我的 chat_id")]
    await kernel.unload("v2cmds")
    assert command_menu(kernel.kernel) == []


_RPC_PLUGIN = """
from shiori_sdk.core.services import RPC


async def _ping(payload):
    return {"pong": payload.get("value")}


async def setup(ctx):
    ctx.require(RPC).register("ping", _ping)
""".strip()

_RPC_MANIFEST = "api: 4\nsdk: '>=4.0.0'\nid: rpcdemo\ninject:\n  - rpc\n"


@pytest.mark.asyncio
async def test_plugin_rpc_method_callable_then_gone_after_unload(tmp_path: Path):
    plugin_dir = tmp_path / "rpcdemo"
    (plugin_dir / "backend").mkdir(parents=True)
    (plugin_dir / "backend" / "plugin.py").write_text(_RPC_PLUGIN, encoding="utf-8")
    (plugin_dir / "manifest.yaml").write_text(_RPC_MANIFEST, encoding="utf-8")
    bus = EventBus()
    rpc = PluginRpcRegistry(bus)
    kernel = make_kernel([tmp_path], event_bus=bus, rpc=rpc)
    await kernel.load_all()

    resolved = rpc.resolve("plugin.rpcdemo.ping")
    assert resolved is not None
    _, handler = resolved
    assert await handler({"value": 1}) == {"pong": 1}

    _ = await kernel.unload("rpcdemo")

    # 插件卸载后其 RPC 方法立即不可调用
    assert rpc.resolve("plugin.rpcdemo.ping") is None


_HOST_SERVICES_PLUGIN = """
from shiori_sdk.core.services import LIGHT_MODEL, LIGHT_PROVIDER, WORKSPACE

captured: dict = {}


async def setup(ctx):
    captured["workspace"] = ctx.require(WORKSPACE)
    captured["light_provider"] = ctx.require(LIGHT_PROVIDER)
    captured["light_model"] = ctx.require(LIGHT_MODEL)
""".strip()

_HOST_SERVICES_MANIFEST = (
    "api: 4\nsdk: '>=4.0.0'\nid: hostrefs\n"
    "inject:\n  - workspace\n  - light_provider\n  - light_model\n"
)


@pytest.mark.asyncio
async def test_plugin_reads_host_service_references(tmp_path: Path):
    """直传型 capability（#183）必须原样透出核心提供的同一个对象。"""
    plugin_dir = tmp_path / "hostrefs"
    (plugin_dir / "backend").mkdir(parents=True)
    (plugin_dir / "backend" / "plugin.py").write_text(
        _HOST_SERVICES_PLUGIN, encoding="utf-8"
    )
    (plugin_dir / "manifest.yaml").write_text(_HOST_SERVICES_MANIFEST, encoding="utf-8")
    workspace = tmp_path / "workspace-for-hostrefs"
    workspace.mkdir()
    light_provider = object()
    kernel = make_kernel(
        [tmp_path],
        event_bus=EventBus(),
        workspace=workspace,
        light_provider=light_provider,
        light_model="light-model-x",
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
        "light_provider": light_provider,
        "light_model": "light-model-x",
    }
    # 核心根本没 provide 声明过的 capability 时，仍在 setup 前失败。
    withheld_root = tmp_path / "withheld"
    light_plugin = withheld_root / "needs_light"
    (light_plugin / "backend").mkdir(parents=True)
    (light_plugin / "backend" / "plugin.py").write_text(
        "async def setup(ctx):\n    raise AssertionError('setup must not run')\n",
        encoding="utf-8",
    )
    (light_plugin / "manifest.yaml").write_text(
        "api: 4\nsdk: '>=4.0.0'\nid: needs_light\ninject:\n  - light_provider\n",
        encoding="utf-8",
    )
    withheld = host_kernel([withheld_root], withheld=frozenset({LIGHT_PROVIDER}))
    await withheld.load_all()
    [state] = withheld.states()
    assert state["state"] == "BLOCKED"
    assert "不存在" in state["error"]


@pytest.mark.asyncio
@pytest.mark.parametrize("capability", ["external_turns", "background_results"])
async def test_turn_services_reach_only_a_plugin_that_declares_them(
    tmp_path: Path, capability: str
):
    for plugin_id, declared in (("submits", f"[{capability}]"), ("other", "[]")):
        plugin_dir = tmp_path / plugin_id
        (plugin_dir / "backend").mkdir(parents=True)
        (plugin_dir / "backend" / "plugin.py").write_text(
            """
from shiori_sdk.core.services import KEY

captured = {}


async def setup(ctx):
    try:
        captured["turns"] = ctx.require(KEY)
    except Exception as error:
        captured["denied"] = str(error)
""".replace(
                "KEY",
                (
                    "EXTERNAL_TURNS"
                    if capability == "external_turns"
                    else "BACKGROUND_RESULTS"
                ),
            ),
            encoding="utf-8",
        )
        (plugin_dir / "manifest.yaml").write_text(
            f"""
api: 4
sdk: ">=4.0.0"
id: {plugin_id}
inject: {declared}
""",
            encoding="utf-8",
        )
    turns = (
        FakeExternalTurns()
        if capability == "external_turns"
        else FakeBackgroundResults()
    )
    kernel = host_kernel([tmp_path], **{capability: turns})
    await kernel.load_all()

    captured = {
        name.rsplit("_", 1)[-1]: module.captured
        for name, module in sys.modules.items()
        if name.startswith("akasic_plugin_") and name.endswith(("_submits", "_other"))
    }
    assert captured["submits"] == {"turns": turns}
    assert capability in captured["other"]["denied"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("name", "state", "fragment", "with_workspace"),
    [
        ("roles", "BLOCKED", "不存在", True),
        ("kv", "FAILED", "宿主未提供服务 workspace", False),
    ],
)
async def test_injected_service_without_a_provider_fails_before_setup(
    tmp_path: Path, name: str, state: str, fragment: str, with_workspace: bool
):
    """缺提供方时计划阶段 BLOCKED；kv 没有 workspace 时在构造上下文时失败。"""
    root = tmp_path / "plugins"
    plugin_dir = root / "needs_service"
    (plugin_dir / "backend").mkdir(parents=True)
    (plugin_dir / "backend" / "plugin.py").write_text(
        "async def setup(ctx):\n    raise AssertionError('setup must not run')\n",
        encoding="utf-8",
    )
    (plugin_dir / "manifest.yaml").write_text(
        f"api: 4\nsdk: '>=4.0.0'\nid: needs_service\ninject:\n  - {name}\n",
        encoding="utf-8",
    )
    kernel = host_kernel(
        [root],
        settings=PluginGenerationSettings(
            workspace=tmp_path / "workspace" if with_workspace else None
        ),
    )
    await kernel.load_all()

    row = next(item for item in kernel.states() if item["id"] == "needs_service")
    assert row["state"] == state
    assert name in row["error"]
    assert fragment in row["error"]
    # 缺 workspace 时不能退回写插件目录（#209）
    assert not (plugin_dir / ".kv.json").exists()


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
        ("consumer", "[provider]", "ctx.expose(ctx.require(DEPENDENCIES))"),
        ("provider", "[]", "ctx.expose({'version': 'first'})"),
    ):
        package = tmp_path / name
        (package / "backend").mkdir(parents=True)
        _ = (package / "manifest.yaml").write_text(
            f"api: 4\nsdk: '>=4.0.0'\nid: {name}\n"
            f"inject: [dependencies]\n"
            f"optional_dependencies: {optional}\n",
            encoding="utf-8",
        )
        _ = (package / "backend/plugin.py").write_text(
            "from shiori_sdk.core.services import DEPENDENCIES\n"
            f"async def setup(ctx):\n    {body}\n",
            encoding="utf-8",
        )
    # Disposal runs while the provider is UNLOADING, before its export is cleared.
    # Optional reads must already report it unavailable at this boundary.
    _ = (tmp_path / "provider/manifest.yaml").write_text(
        "api: 4\nsdk: '>=4.0.0'\nid: provider\n"
        "inject: [dependencies]\n"
        "optional_dependencies: [consumer]\n",
        encoding="utf-8",
    )
    _ = (tmp_path / "provider/backend/plugin.py").write_text(
        "from shiori_sdk.core.services import DEPENDENCIES\n"
        "async def setup(ctx):\n"
        "    dependencies = ctx.require(DEPENDENCIES)\n"
        "    ctx.expose({'version': 'first'})\n"
        "    def on_unload():\n"
        "        consumer = dependencies.get_optional('consumer')\n"
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
        "api: 4\nsdk: '>=4.0.0'\nid: provider\n",
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
            f"api: 4\nsdk: '>=4.0.0'\nid: {name}\ndependencies: {dependencies}\nsupports_hot_unload: {str(safe).lower()}\n",
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
            f"api: 4\nsdk: '>=4.0.0'\nid: {name}\nsupports_hot_unload: false\n",
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
        "api: 4\nsdk: '>=4.0.0'\nid: broken\ninject: [events]\nsupports_hot_unload: false\n",
        encoding="utf-8",
    )
    (package / "backend/plugin.py").write_text(
        "from shiori_sdk.core.services import EVENTS\n"
        'async def setup(ctx):\n    async def on_event(event):\n        event.append("leaked")\n        return event\n    ctx.require(EVENTS).on(list, on_event)\n    raise RuntimeError("setup failed")\n',
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
        "api: 4\nsdk: '>=4.0.0'\nid: needs_config\ninject: [config]\n"
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
        "from shiori_sdk.core.services import CONFIG\n"
        "from .config import Config\n\n\n"
        "async def setup(ctx):\n"
        "    Config.model_validate(ctx.require(CONFIG).as_dict())\n",
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
async def test_only_manifested_entries_are_loaded(tmp_path):
    for name, manifest in [
        ("missing", None),
        ("old", "api: 1\ncapabilities: []\n"),
        ("missing_setup", "api: 4\nsdk: '>=4.0.0'\n"),
    ]:
        package = tmp_path / name
        (package / "backend").mkdir(parents=True)
        (package / "backend/plugin.py").write_text("value = 1\n", encoding="utf-8")
        if manifest is not None:
            (package / "manifest.yaml").write_text(manifest, encoding="utf-8")
    kernel = make_kernel([tmp_path], event_bus=EventBus())
    assert {record.name for record in kernel.discover()} == {"old", "missing_setup"}
    await kernel.load_all()
    assert kernel.loaded_count == 0
    states = {row["id"]: row for row in kernel.states()}
    assert states["old"]["state"] == "BLOCKED"
    assert states["old"]["diagnostic"]["code"] == "unsupported_api"
    assert states["missing_setup"]["state"] == "FAILED"
    assert "setup(ctx)" in states["missing_setup"]["error"]


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
            f"api: 4\nsdk: '>=4.0.0'\nid: {name}\n" + body, encoding="utf-8"
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
        "runtime_api: '>=2.0.0 <3.0.0'",
        "renderer: {surface: {entry: missing.mjs, css: []}}",
        "host_dependencies: {python: [not-installed]}",
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
    kernel = host_kernel(
        [contract_package.parent],
        external_plugin_dirs=[contract_package.parent],
        event_bus=EventBus(),
    )
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
@pytest.mark.parametrize("provider", ["missing", "disabled", "unadmitted"])
async def test_plugin_dependency_rejection_keeps_contract_diagnostic(
    contract_package, provider
):
    import yaml

    path = contract_package / "manifest.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    raw["dependencies"] = ["provider"]
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    if provider != "missing":
        package = contract_package.parent / "provider"
        package.mkdir()
        # An old package is on the roster but not runnable, so the dependent
        # is "unavailable", not "missing".
        api = 2 if provider == "unadmitted" else 4
        sdk = "sdk: '>=4.0.0'\n" if api == 4 else ""
        (package / "manifest.yaml").write_text(
            f"api: {api}\n{sdk}id: provider\n",
            encoding="utf-8",
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
    assert state["diagnostic"]["code"] == (
        "missing_dependency" if provider == "missing" else "dependency_unavailable"
    )
    assert state["diagnostic"]["stage"] == "dependency"
    assert state["diagnostic"]["field"] == "dependencies[0]"
    assert state["diagnostic"]["state"] == "BLOCKED"
    assert state["diagnostic"]["reason"] == state["error"]


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled", [True, False])
async def test_external_package_never_executes_even_with_config_enablement(
    contract_package, enabled
):
    from agent.plugin_host import PluginGenerationSettings

    marker = contract_package / "executed.txt"
    (contract_package / "backend/plugin.py").write_text(
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('imported', encoding='utf-8')\n"
        "async def setup(ctx): raise AssertionError('must not execute')\n",
        encoding="utf-8",
    )
    kernel = host_kernel(
        [contract_package.parent],
        external_plugin_dirs=[contract_package.parent],
        strict=True,
        settings=PluginGenerationSettings(
            plugin_configs={"external_demo": {"enabled": enabled}}
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
async def test_package_changed_after_discovery_is_not_started_by_the_kernel(
    contract_package, tmp_path
):
    approved = inspect_package_content(contract_package)
    PluginTrustStore(tmp_path).approve(contract_package, approved.fingerprint)
    kernel = host_kernel(
        [tmp_path],
        external_plugin_dirs=[tmp_path],
        settings=PluginGenerationSettings(workspace=tmp_path),
    )
    _ = kernel.discover()
    marker = tmp_path / "executed.txt"
    (contract_package / "backend/plugin.py").write_text(
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('imported', encoding='utf-8')\n"
        "async def setup(ctx): pass\n",
        encoding="utf-8",
    )
    failed: list[PluginFailed] = []

    async def record_failure(event: PluginFailed) -> PluginFailed:
        failed.append(event)
        return event

    kernel.kernel.check(PluginFailed, record_failure)

    # Admitted at discovery, then refused at load when the bytes no longer
    # match: the refusal is the host's, never a kernel setup failure.
    await kernel.load_all()
    [state] = kernel.states()
    assert state["state"] == "UNTRUSTED"
    assert state["diagnostic"]["code"] == "trust_changed"
    assert kernel.kernel.status("external_demo") is None
    assert failed == []

    await kernel.kernel.start([])

    assert not marker.exists()
    assert kernel.kernel.status("external_demo") is None
    assert failed == []
    await kernel.terminate_all(force=True)


@pytest.mark.asyncio
async def test_refused_duplicate_provider_leaves_the_key_to_the_other(tmp_path):
    workspace = tmp_path / "workspace"
    trust = PluginTrustStore(tmp_path)
    for plugin_id in ("alpha", "beta"):
        package = workspace / plugin_id
        (package / "backend").mkdir(parents=True)
        (package / "manifest.yaml").write_text(
            f"api: 4\nsdk: '>=4.0.0'\nid: {plugin_id}\n"
            "version: 1.0.0\n"
            "entry: backend/plugin.py\nprovides: [shared.engine]\n",
            encoding="utf-8",
        )
        (package / "backend/plugin.py").write_text(
            "async def setup(ctx): pass\n", encoding="utf-8"
        )
        trust.approve(package, inspect_package_content(package).fingerprint)
    kernel = host_kernel(
        [workspace],
        external_plugin_dirs=[workspace],
        settings=PluginGenerationSettings(workspace=tmp_path),
    )
    _ = kernel.discover()
    (workspace / "beta/backend/plugin.py").write_text(
        "async def setup(ctx): raise RuntimeError('changed')\n", encoding="utf-8"
    )

    await kernel.load_all()

    # beta is refused before the plan, so it is no duplicate of alpha.
    assert {row["id"]: row["state"] for row in kernel.states()} == {
        "alpha": "ACTIVE",
        "beta": "UNTRUSTED",
    }
    await kernel.terminate_all(force=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("conflict", [True, False])
async def test_rejected_provider_and_dependents_never_execute(tmp_path, conflict):

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
            f"api: 4\nsdk: '>=4.0.0'\nid: {plugin_id}\n"
            "version: 1.0.0\n"
            "entry: backend/plugin.py\n" + extra,
            encoding="utf-8",
        )
        (package / "backend/plugin.py").write_text(
            "from pathlib import Path\n"
            f"Path({str(marker)!r}).write_text('imported', encoding='utf-8')\n"
            "async def setup(ctx): pass\n",
            encoding="utf-8",
        )
    kernel = host_kernel(
        [builtin, external],
        external_plugin_dirs=[external],
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
    from agent.plugin_host.manifest import ManifestError

    roots = [tmp_path / "a", tmp_path / "b"]
    for index, root in enumerate(roots):
        package = root / "same"
        (package / "backend").mkdir(parents=True)
        (package / "manifest.yaml").write_text(
            f"api: 4\nsdk: '>=4.0.0'\nid: plugin_{index}\n", encoding="utf-8"
        )
        (package / "backend/plugin.py").write_text(
            "async def setup(ctx): pass\n", encoding="utf-8"
        )
    kernel = host_kernel(
        roots,
    )
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

    stage_plugin_package(PLUGIN_FIXTURES / "hello", tmp_path / "hello")
    first_bus, next_bus = EventBus(), EventBus()
    first = make_kernel([tmp_path], event_bus=first_bus)
    await first.load_all()
    successor = host_kernel(
        [tmp_path],
        event_bus=next_bus,
        discovery_snapshot=first.discover(),
    )
    first_record, next_record = first.discover()[0], successor.discover()[0]
    assert first_record is not next_record
    assert first_record.manifest is not next_record.manifest
    assert first_record.import_path != next_record.import_path
    # The manifest metadata contains nested lists; shallow descriptor copying
    # would let one generation silently modify another generation's snapshot.
    next_record.manifest.metadata["inject"].append("kv")
    assert first_record.manifest.metadata["inject"] == ["events"]
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

    first = make_kernel([tmp_path], event_bus=EventBus())
    assert first.discover() == []
    stage_plugin_package(PLUGIN_FIXTURES / "hello", tmp_path / "hello")
    successor = host_kernel(
        [tmp_path],
        discovery_snapshot=first.discover(),
    )
    await successor.load_all()
    assert successor.discover() == []
    assert successor.loaded_count == 0


# ── 跨进程激活事务汇总（issue #262） ────────────────────────────────────────


def _write_renderer_gated_plugin(
    directory: Path, plugin_id: str, *, renderer: str
) -> None:
    """Writes an api: 4 builtin manifest whose ``renderer`` block gates display.

    The loader keeps ``renderer`` in metadata. A builtin source does not go
    through package validation, so the activation gate can be exercised
    without trust.
    """
    (directory / "backend").mkdir(parents=True)
    (directory / "manifest.yaml").write_text(
        f"api: 4\nsdk: '>=4.0.0'\nid: {plugin_id}\ninject: [tools]\n{renderer}",
        encoding="utf-8",
    )
    (directory / "backend/plugin.py").write_text(
        "from shiori_sdk.core.services import TOOLS\n"
        "from shiori_sdk.tools import Tool\n\n\n"
        "class DemoTool(Tool):\n"
        f"    name = {plugin_id + '_tool'!r}\n"
        "    description = 'demo'\n"
        "    parameters = {'type': 'object', 'properties': {}}\n\n"
        "    async def execute(self, **kwargs):\n"
        "        return 'ok'\n\n\n"
        "async def setup(ctx):\n"
        "    ctx.require(TOOLS).register(DemoTool())\n",
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
        "api: 4\nsdk: '>=4.0.0'\nid: unclean\n", encoding="utf-8"
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
from shiori_sdk.core.services import CHANNELS

class _Channel:
    def __init__(self, name):
        self.name = name

async def setup(ctx):
    channels = ctx.require(CHANNELS)
    channels.add(_Channel("declared"))
    channels.add(_Channel({second!r}))
""".strip()


def _write_channel_plugin(root: Path, plugin_id: str, second: str) -> None:
    package = root / plugin_id
    (package / "backend").mkdir(parents=True)
    (package / "backend/plugin.py").write_text(
        _CHANNEL_PLUGIN.format(second=second), encoding="utf-8"
    )
    (package / "manifest.yaml").write_text(
        f"api: 4\nsdk: '>=4.0.0'\nid: {plugin_id}\ninject: [channels]\n"
        "contributes:\n  channels:\n"
        "    - {name: declared, label: Declared, chat_types:"
        " [{type: private, label: 私聊, chat_id_label: ID}]}\n"
        "    - {name: also_declared, label: Also, chat_types:"
        " [{type: private, label: 私聊, chat_id_label: ID}]}\n",
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_declared_channels_are_contributed(tmp_path: Path):
    _write_channel_plugin(tmp_path, "chan", "also_declared")
    kernel = make_kernel([tmp_path], event_bus=EventBus())
    await kernel.load_all()
    try:
        assert [channel.name for channel in active_plugin_channels(kernel)] == [
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
        assert active_plugin_channels(kernel) == []
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
        assert active_plugin_channels(kernel) == []
        assert {state["state"] for state in kernel.states()} == {"CONFLICT"}
        assert {state["diagnostic"]["code"] for state in kernel.states()} == {
            "duplicate_channel"
        }
    finally:
        await kernel.terminate_all(force=True)


@pytest.mark.asyncio
async def test_installed_api2_package_is_blocked_without_losing_data(tmp_path: Path):
    """An old package that provides a core key does not abort startup.

    Its files and config stay, and a current sibling still loads.
    """
    builtin, installed = tmp_path / "builtin", tmp_path / "plugins"
    legacy = installed / "legacy"
    (legacy / "backend").mkdir(parents=True)
    (legacy / "manifest.yaml").write_text(
        "api: 2\nid: legacy\nprovides:\n  - tools\n",
        encoding="utf-8",
    )
    marker = tmp_path / "executed.txt"
    (legacy / "backend/plugin.py").write_text(
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('executed', encoding='utf-8')\n"
        "from shiori_sdk.kernel import Key\n"
        "async def setup(ctx):\n"
        "    ctx.provide(Key('host.bridge'), object())\n"
        "    ctx.provide(Key('tools'), object())\n",
        encoding="utf-8",
    )
    data = tmp_path / "plugin-data" / "legacy" / "kv.json"
    data.parent.mkdir(parents=True)
    data.write_text('{"saved": "keep"}', encoding="utf-8")
    fresh = builtin / "fresh"
    (fresh / "backend").mkdir(parents=True)
    (fresh / "manifest.yaml").write_text(
        "api: 4\nsdk: '>=4.0.0'\nid: fresh\ninject: [tools]\n", encoding="utf-8"
    )
    (fresh / "backend/plugin.py").write_text(
        "from shiori_sdk.core.services import TOOLS\n"
        "from shiori_sdk.tools import Tool\n"
        "class Fresh(Tool):\n"
        "    name = 'fresh_tool'\n"
        "    description = 'fresh'\n"
        "    parameters = {'type': 'object', 'properties': {}}\n"
        "    async def execute(self, **kwargs):\n"
        "        return 'ok'\n"
        "async def setup(ctx):\n"
        "    ctx.require(TOOLS).register(Fresh(), risk='read-only')\n",
        encoding="utf-8",
    )
    settings = PluginGenerationSettings(
        workspace=tmp_path,
        plugin_configs={"legacy": {"enabled": True, "note": "keep"}},
    )
    tools = ToolRegistry()
    kernel = host_kernel(
        [builtin, installed],
        external_plugin_dirs=[installed],
        settings=settings,
        tools=tools,
        strict=True,
    )
    await kernel.load_all()
    try:
        states = {row["id"]: row for row in kernel.states()}
        assert states["legacy"]["state"] == "BLOCKED"
        assert states["legacy"]["diagnostic"]["code"] == "unsupported_api"
        assert states["fresh"]["state"] == "ACTIVE"
        assert tools.get_tool("fresh_tool") is not None
        assert not marker.exists()
        assert data.read_text(encoding="utf-8") == '{"saved": "keep"}'
        assert settings.plugin_configs["legacy"]["note"] == "keep"
        assert (legacy / "manifest.yaml").is_file()
        assert (legacy / "backend/plugin.py").is_file()
    finally:
        await kernel.terminate_all(force=True)


@pytest.mark.asyncio
async def test_api2_host_key_does_not_abort_startup(tmp_path: Path):
    """A strict host still starts when an old manifest names ``host.bridge``."""
    package = tmp_path / "legacy"
    (package / "backend").mkdir(parents=True)
    (package / "manifest.yaml").write_text(
        "api: 2\nid: legacy\ninject:\n  - host.bridge\n",
        encoding="utf-8",
    )
    (package / "backend/plugin.py").write_text(
        "raise AssertionError('old package must not be imported')\n",
        encoding="utf-8",
    )
    kernel = host_kernel([tmp_path], strict=True)
    await kernel.load_all()
    try:
        [state] = kernel.states()
        assert state["state"] == "BLOCKED"
        assert state["diagnostic"]["code"] == "unsupported_api"
        owner, impl = kernel.kernel._providers["host.bridge"]
        assert owner == ""
        assert impl is kernel._rpc
    finally:
        await kernel.terminate_all(force=True)
