"""plugins.list/plugins.setEnabled：插件管理列表与热启停，覆盖验收标准 3。

沿用 test_plugin_config.py 的真实插件夹具（qqbot 有配置模型，hello 没有），
证明启停通道对存量插件立即可用，而不是只能造假插件验证。
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from agent.config import load_config_text
from agent.plugin_host.handle import PluginState
from bootstrap.app import AppRuntime, RuntimeFeatures
from shiori_plugin_testkit.packages import stage_plugin_package
from core.roles.store import RoleStore
from desktop_bridge.runtime.service import ReloadableDesktopService

_REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
_QQBOT_PLUGIN_DIR = _REPOSITORY_ROOT / "plugins" / "qqbot"
_HELLO_FIXTURE_DIR = _REPOSITORY_ROOT / "tests" / "fixtures" / "plugins" / "hello"

# A scoped RPC fixture exercises the public bridge registration.
_RPC_DEMO_PLUGIN_PY = """
async def _ping(payload):
    return {"pong": payload.get("value")}


async def setup(ctx):
    ctx.rpc.register("ping", _ping)
""".strip()

_RPC_DEMO_MANIFEST = "api: 2\nid: rpc_demo\ncapabilities:\n  - rpc\n"


def _config() -> str:
    return "[llm]\nregistrations = []\n\n[agent.maintenance]\nmemory_optimizer_enabled = false\n"


def _stage_plugin_dirs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    with_rpc_demo: bool = False,
) -> None:
    root = tmp_path / "plugin_dirs"
    shutil.copytree(_QQBOT_PLUGIN_DIR, root / "qqbot")
    _ = stage_plugin_package(_HELLO_FIXTURE_DIR, root / "hello")
    if with_rpc_demo:
        rpc_demo_dir = root / "rpc_demo"
        (rpc_demo_dir / "backend").mkdir(parents=True)
        (rpc_demo_dir / "backend" / "plugin.py").write_text(
            _RPC_DEMO_PLUGIN_PY, encoding="utf-8"
        )
        (rpc_demo_dir / "manifest.yaml").write_text(
            _RPC_DEMO_MANIFEST, encoding="utf-8"
        )
    monkeypatch.setattr(
        "bootstrap.tools._resolve_plugin_dirs", lambda workspace: [root]
    )


async def _start_service(
    tmp_path: Path,
) -> tuple[ReloadableDesktopService, Path, AppRuntime]:
    path = tmp_path / "config.toml"
    path.write_text(_config(), encoding="utf-8")
    app = AppRuntime(
        load_config_text(_config()),
        tmp_path,
        features=RuntimeFeatures(enable_message_channels=False, enable_proactive=False),
    )
    await app.start()
    service = ReloadableDesktopService(app, path, RoleStore(tmp_path))
    return service, path, app


async def _request(service: ReloadableDesktopService, method: str, payload=None):
    return await service.handle(
        {"id": method, "method": method, "payload": payload or {}},
        emit_event=lambda event: None,
    )


@pytest.mark.asyncio
async def test_plugin_events_are_forwarded_only_by_their_owning_generation(
    tmp_path, monkeypatch
):
    from agent.plugin_host.bridge_events import PluginBridgeEvent

    _stage_plugin_dirs(tmp_path, monkeypatch, with_rpc_demo=True)
    service, _, app = await _start_service(tmp_path)
    events = []
    service.add_event_listener(events.append)
    try:
        kernel = app.core.plugin_manager
        await app.core.event_bus.emit(
            PluginBridgeEvent("plugin.rpc_demo.changed", {"value": 1}, kernel.rpc)
        )
        await app.core.event_bus.emit(
            PluginBridgeEvent("plugin.rpc_demo.changed", {"value": 2}, object())
        )
        assert [event["payload"] for event in events] == [{"value": 1}]
    finally:
        await service.aclose()
        await app.shutdown()


@pytest.mark.asyncio
async def test_list_reports_every_discovered_plugin_enabled_by_default(
    tmp_path, monkeypatch
):
    _stage_plugin_dirs(tmp_path, monkeypatch)
    service, _, app = await _start_service(tmp_path)
    try:
        response = await _request(service, "plugins.list")

        assert response.error is None, response.error
        by_id = {item["id"]: item for item in response.payload["plugins"]}
        assert set(by_id) == {"qqbot", "hello"}
        assert by_id["qqbot"]["enabled"] is True
        assert by_id["qqbot"]["state"] == PluginState.ACTIVE.name
        assert by_id["qqbot"]["has_config_schema"] is True
        assert by_id["hello"]["has_config_schema"] is False
        assert by_id["hello"]["renderer"] == {}
    finally:
        await service.aclose()
        await app.shutdown()


@pytest.mark.asyncio
async def test_list_shows_manifest_title_without_changing_the_toggle_id(
    tmp_path, monkeypatch
):
    _stage_plugin_dirs(tmp_path, monkeypatch)
    manifest = tmp_path / "plugin_dirs" / "hello" / "manifest.yaml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8") + "\ndisplay_name: 24h视奸插件\n",
        encoding="utf-8",
    )
    service, _, app = await _start_service(tmp_path)
    try:
        response = await _request(service, "plugins.list")
        by_id = {item["id"]: item for item in response.payload["plugins"]}
        assert by_id["hello"]["name"] == "24h视奸插件"
        assert by_id["hello"]["id"] == "hello"
        # qqbot 的 manifest 自 #230 起声明了 display_name：真实插件同样只改展示名。
        assert by_id["qqbot"]["name"] == "QQBot"
        assert by_id["qqbot"]["id"] == "qqbot"
    finally:
        await service.aclose()
        await app.shutdown()


@pytest.mark.asyncio
async def test_list_falls_back_to_the_plugin_directory_name_without_display_name(
    tmp_path, monkeypatch
):
    """没有声明 display_name 的插件，展示名回退到插件目录名。

    这一半此前由 qqbot 承担；#230 给 qqbot 补了 display_name 之后需要一个仍然
    没有声明它的样本，否则回退链只剩下无人证明的一段。
    """
    _stage_plugin_dirs(tmp_path, monkeypatch)
    service, _, app = await _start_service(tmp_path)
    try:
        response = await _request(service, "plugins.list")
        by_id = {item["id"]: item for item in response.payload["plugins"]}
        assert by_id["hello"]["name"] == "hello"
    finally:
        await service.aclose()
        await app.shutdown()


@pytest.mark.asyncio
async def test_list_preserves_renderer_declarations_as_data(tmp_path, monkeypatch):
    _stage_plugin_dirs(tmp_path, monkeypatch)
    manifest = tmp_path / "plugin_dirs" / "hello" / "manifest.yaml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8")
        + "\nrenderer:\n  ui:\n    entry: ui/dist/index.mjs\n"
        + "    css: [ui/dist/style.css]\n",
        encoding="utf-8",
    )
    service, _, app = await _start_service(tmp_path)
    try:
        response = await _request(service, "plugins.list")
        assert response.error is None
        hello = next(row for row in response.payload["plugins"] if row["id"] == "hello")
        assert hello["renderer"] == {
            "ui": {"entry": "ui/dist/index.mjs", "css": ["ui/dist/style.css"]}
        }
    finally:
        await service.aclose()
        await app.shutdown()


def _declare_renderer_ui(tmp_path: Path, kinds: tuple[str, ...] = ("ui",)) -> None:
    """Appends a ``renderer:`` block declaring the given kinds to hello's manifest."""
    manifest = tmp_path / "plugin_dirs" / "hello" / "manifest.yaml"
    lines = "\n".join(
        f"  {kind}:\n    entry: {kind}/index.mjs\n    css: []" for kind in kinds
    )
    manifest.write_text(
        manifest.read_text(encoding="utf-8") + f"\nrenderer:\n{lines}\n",
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_activation_report_confirms_ready_and_clears_pending_kinds(
    tmp_path, monkeypatch
):
    """issue #262 AC1: hello stays displayed as ACTIVE with pending kinds until
    every declared renderer entry confirms, then the gate clears."""
    _stage_plugin_dirs(tmp_path, monkeypatch)
    _declare_renderer_ui(tmp_path, ("ui", "background"))
    service, _, app = await _start_service(tmp_path)
    try:
        before = await _request(service, "plugins.list")
        hello = next(row for row in before.payload["plugins"] if row["id"] == "hello")
        assert hello["state"] == PluginState.ACTIVE.name
        assert sorted(hello["pending_renderer_kinds"]) == ["background", "ui"]

        confirmed = await _request(
            service,
            "plugins.activation.report",
            {"plugin_id": "hello", "kind": "ui", "ok": True},
        )
        assert confirmed.error is None, confirmed.error
        assert confirmed.payload == {
            "plugin_id": "hello",
            "kind": "ui",
            "changed": True,
        }

        confirmed_again = await _request(
            service,
            "plugins.activation.report",
            {"plugin_id": "hello", "kind": "background", "ok": True},
        )
        assert confirmed_again.payload["changed"] is True

        after = await _request(service, "plugins.list")
        hello_after = next(
            row for row in after.payload["plugins"] if row["id"] == "hello"
        )
        assert hello_after["state"] == PluginState.ACTIVE.name
        assert hello_after["pending_renderer_kinds"] == []
    finally:
        await service.aclose()
        await app.shutdown()


@pytest.mark.asyncio
async def test_activation_report_failure_rolls_back_and_republishes_roster(
    tmp_path, monkeypatch
):
    """issue #262 AC2/AC3/AC4: a renderer-reported failure rolls the plugin
    back to FAILED with a `ui`-stage diagnostic, republishes the roster so
    every window's next `plugins.list()` sees it, and never touches qqbot."""
    _stage_plugin_dirs(tmp_path, monkeypatch)
    _declare_renderer_ui(tmp_path, ("ui",))
    service, _, app = await _start_service(tmp_path)
    events = []
    service.add_event_listener(events.append)
    try:
        failed = await _request(
            service,
            "plugins.activation.report",
            {"plugin_id": "hello", "kind": "ui", "ok": False, "reason": "module threw"},
        )
        assert failed.error is None, failed.error
        assert failed.payload == {"plugin_id": "hello", "kind": "ui", "changed": True}
        assert any(event["method"] == "runtime.applied" for event in events)

        after = await _request(service, "plugins.list")
        by_id = {row["id"]: row for row in after.payload["plugins"]}
        assert by_id["hello"]["state"] == PluginState.FAILED.name
        assert by_id["hello"]["diagnostic"] == {
            "code": "renderer_ui_failed",
            "stage": "ui",
            "field": "renderer.ui.entry",
            "reason": "module threw",
            "path": "",
            "state": "FAILED",
        }
        # Other plugins keep running untouched (AC3).
        assert by_id["qqbot"]["state"] == PluginState.ACTIVE.name
    finally:
        await service.aclose()
        await app.shutdown()


@pytest.mark.asyncio
async def test_activation_report_ignores_a_stale_or_unknown_plugin(
    tmp_path, monkeypatch
):
    """A report naming a plugin the current generation is not tracking as
    ACTIVE (never declared it, already disabled, or a superseded generation)
    is accepted and inert rather than raising (AC5 — no retry loop)."""
    _stage_plugin_dirs(tmp_path, monkeypatch)
    service, _, app = await _start_service(tmp_path)
    events = []
    service.add_event_listener(events.append)
    try:
        response = await _request(
            service,
            "plugins.activation.report",
            {"plugin_id": "does-not-exist", "kind": "ui", "ok": False, "reason": "n/a"},
        )
        assert response.error is None, response.error
        assert response.payload == {
            "plugin_id": "does-not-exist",
            "kind": "ui",
            "changed": False,
        }
        assert not any(event["method"] == "runtime.applied" for event in events)

        after = await _request(service, "plugins.list")
        hello = next(row for row in after.payload["plugins"] if row["id"] == "hello")
        assert hello["state"] == PluginState.ACTIVE.name
    finally:
        await service.aclose()
        await app.shutdown()


@pytest.mark.asyncio
async def test_set_enabled_false_disables_immediately_and_survives_a_restart(
    tmp_path, monkeypatch
):
    _stage_plugin_dirs(tmp_path, monkeypatch)
    service, path, app = await _start_service(tmp_path)
    try:
        response = await _request(
            service,
            "plugins.setEnabled",
            {
                "plugin_id": "hello",
                "enabled": False,
                "operation_id": "op-disable",
            },
        )
        assert response.error is None, response.error
        assert response.payload["enabled"] is False
        assert "generation" in response.payload

        # 立即消失：新一代内核里 hello 不再被加载，RPC/工具随之消失。
        after = await _request(service, "plugins.list")
        by_id = {item["id"]: item for item in after.payload["plugins"]}
        assert by_id["hello"]["enabled"] is False
        assert by_id["hello"]["state"] == PluginState.DISABLED.name
        assert by_id["qqbot"]["enabled"] is True

        on_disk = path.read_text(encoding="utf-8")
        assert "[plugins.hello]" in on_disk
    finally:
        await service.aclose()
        await app.shutdown()

    restarted = load_config_text(path.read_text(encoding="utf-8"))
    assert restarted.plugins["hello"]["enabled"] is False
    restarted_app = AppRuntime(
        restarted,
        tmp_path,
        features=RuntimeFeatures(enable_message_channels=False, enable_proactive=False),
    )
    await restarted_app.start()
    restarted_service = ReloadableDesktopService(
        restarted_app, path, RoleStore(tmp_path)
    )
    try:
        response_after_restart = await _request(restarted_service, "plugins.list")
        by_id = {item["id"]: item for item in response_after_restart.payload["plugins"]}
        assert by_id["hello"]["enabled"] is False
        assert by_id["hello"]["state"] == PluginState.DISABLED.name
    finally:
        await restarted_service.aclose()
        await restarted_app.shutdown()


@pytest.mark.asyncio
async def test_disabling_a_plugin_makes_its_rpc_method_immediately_uncallable(
    tmp_path, monkeypatch
):
    """端到端证明验收标准 3：不是只看 plugins.list 的 state，而是真的调不通了。

    此前只断言 ``plugins.list`` 里的 state 变成 DISABLED，注释里推断"RPC/工具
    随之消失"，但没有任何测试真的经 ``plugins.setEnabled`` 走一遍完整的
    停用流程后再调用该插件注册的 RPC 方法。这里用一个真正登记了
    ``plugin.rpc_demo.ping`` 的 v2 夹具插件，证明停用前能调通、停用后经桥接
    返回 unknown_method（而不是只在内核层面验证 unload，见
    test_kernel.py::test_v2_plugin_rpc_method_callable_then_gone_after_unload）。
    """
    _stage_plugin_dirs(tmp_path, monkeypatch, with_rpc_demo=True)
    service, _, app = await _start_service(tmp_path)
    try:
        before = await _request(service, "plugin.rpc_demo.ping", {"value": 1})
        assert before.error is None, before.error
        assert before.payload == {"pong": 1}

        disabled = await _request(
            service,
            "plugins.setEnabled",
            {
                "plugin_id": "rpc_demo",
                "enabled": False,
                "operation_id": "op-disable-rpc",
            },
        )
        assert disabled.error is None, disabled.error

        after = await _request(service, "plugin.rpc_demo.ping", {"value": 1})
        assert after.error is not None
        assert after.error.code == "unknown_method"
    finally:
        await service.aclose()
        await app.shutdown()


@pytest.mark.asyncio
async def test_set_enabled_publishes_runtime_applied(tmp_path, monkeypatch):
    """#226: the headless plugin-host window has no `pluginEnabledStateStore`
    of its own and learns its roster changed only through `runtime.applied`.

    Before this test existed, `plugins.setEnabled` was dispatched through the
    PLUGIN_MANAGEMENT branch of `ReloadableDesktopService.handle`, a
    different branch from the one that publishes `runtime.applied` (SETTINGS,
    gated on `method == "runtime.apply"`) — even though `set_enabled` performs
    the exact same kind of settings apply and returns the same
    `{generation, changed}` shape. The toggle succeeded and persisted, but no
    event ever told another window about it, so a disabled plugin's
    `app.background` contribution kept running until an unrelated settings
    save happened to fire `runtime.apply`, or the app restarted.
    """
    _stage_plugin_dirs(tmp_path, monkeypatch)
    service, _, app = await _start_service(tmp_path)
    published: list[dict] = []
    service.add_event_listener(lambda event: published.append(event))
    try:
        response = await _request(
            service,
            "plugins.setEnabled",
            {
                "plugin_id": "hello",
                "enabled": False,
                "operation_id": "op-disable",
            },
        )
        assert response.error is None, response.error

        applied = [
            event for event in published if event.get("method") == "runtime.applied"
        ]
        assert (
            len(applied) == 1
        ), f"expected exactly one runtime.applied, got {published}"
        # A real publication announces the resulting generation once.
        assert applied[0]["payload"] == response.payload
        retry = await _request(
            service,
            "plugins.setEnabled",
            {"plugin_id": "hello", "enabled": False, "operation_id": "op-disable"},
        )
        assert retry.error is None, retry.error
        assert retry.payload == response.payload
        assert published[-1]["payload"] == {**response.payload, "changed": False}
        reenabled = await _request(
            service,
            "plugins.setEnabled",
            {"plugin_id": "hello", "enabled": True, "operation_id": "op-enable"},
        )
        assert reenabled.error is None, reenabled.error
        assert published[-1]["payload"] == reenabled.payload
        count = len(published)
        stale = await _request(
            service,
            "plugins.setEnabled",
            {"plugin_id": "hello", "enabled": False, "operation_id": "op-disable"},
        )
        assert stale.error is None, stale.error
        assert stale.payload == response.payload
        assert len(published) == count
    finally:
        await service.aclose()
        await app.shutdown()


@pytest.mark.asyncio
async def test_list_does_not_publish_runtime_applied(tmp_path, monkeypatch):
    """`plugins.list` is a read; it must not fire the "something changed" event."""
    _stage_plugin_dirs(tmp_path, monkeypatch)
    service, _, app = await _start_service(tmp_path)
    published: list[dict] = []
    service.add_event_listener(lambda event: published.append(event))
    try:
        response = await _request(service, "plugins.list")
        assert response.error is None, response.error
        assert published == []
    finally:
        await service.aclose()
        await app.shutdown()


@pytest.mark.asyncio
async def test_set_enabled_re_enables_a_previously_disabled_plugin(
    tmp_path, monkeypatch
):
    _stage_plugin_dirs(tmp_path, monkeypatch)
    service, _, app = await _start_service(tmp_path)
    try:
        await _request(
            service,
            "plugins.setEnabled",
            {
                "plugin_id": "hello",
                "enabled": False,
                "operation_id": "op-1",
            },
        )
        response = await _request(
            service,
            "plugins.setEnabled",
            {
                "plugin_id": "hello",
                "enabled": True,
                "operation_id": "op-2",
            },
        )

        assert response.error is None, response.error
        after = await _request(service, "plugins.list")
        by_id = {item["id"]: item for item in after.payload["plugins"]}
        assert by_id["hello"]["enabled"] is True
        assert by_id["hello"]["state"] == PluginState.ACTIVE.name
    finally:
        await service.aclose()
        await app.shutdown()


@pytest.mark.asyncio
async def test_set_enabled_rejects_an_unknown_plugin_and_writes_nothing(
    tmp_path, monkeypatch
):
    _stage_plugin_dirs(tmp_path, monkeypatch)
    service, path, app = await _start_service(tmp_path)
    try:
        before = path.read_text(encoding="utf-8")

        response = await _request(
            service,
            "plugins.setEnabled",
            {
                "plugin_id": "does-not-exist",
                "enabled": False,
                "operation_id": "op-1",
            },
        )

        assert response.error is not None
        assert response.error.code == "plugin_not_found"
        assert path.read_text(encoding="utf-8") == before
    finally:
        await service.aclose()
        await app.shutdown()


@pytest.mark.asyncio
async def test_set_enabled_requires_plugin_id_operation_id_and_a_boolean(
    tmp_path, monkeypatch
):
    _stage_plugin_dirs(tmp_path, monkeypatch)
    service, path, app = await _start_service(tmp_path)
    try:
        before = path.read_text(encoding="utf-8")

        missing_plugin_id = await _request(
            service,
            "plugins.setEnabled",
            {
                "enabled": False,
                "operation_id": "op-1",
            },
        )
        missing_operation_id = await _request(
            service,
            "plugins.setEnabled",
            {
                "plugin_id": "hello",
                "enabled": False,
            },
        )
        non_boolean_enabled = await _request(
            service,
            "plugins.setEnabled",
            {
                "plugin_id": "hello",
                "enabled": "false",
                "operation_id": "op-2",
            },
        )

        assert missing_plugin_id.error.code == "runtime_invalid_request"
        assert missing_operation_id.error.code == "runtime_invalid_request"
        assert non_boolean_enabled.error.code == "runtime_invalid_request"
        assert path.read_text(encoding="utf-8") == before
    finally:
        await service.aclose()
        await app.shutdown()


@pytest.mark.asyncio
async def test_writing_plugin_config_preserves_the_enabled_flag(tmp_path, monkeypatch):
    """写插件配置不能把启停状态抹掉。

    启停状态与配置值住在同一张 ``[plugins.<id>]`` 表里，而 ``plugin.config.set``
    是整表替换、写入的是经模型校验后的值——``enabled`` 不是模型字段，pydantic
    默认会丢弃它。若不显式保留，用户改一次插件配置就会把这个标志冲掉。
    """
    _stage_plugin_dirs(tmp_path, monkeypatch)
    service, path, app = await _start_service(tmp_path)
    try:
        # 先停用再启用，让 enabled 以显式形式落进配置表
        for index, flag in enumerate((False, True)):
            toggled = await _request(
                service,
                "plugins.setEnabled",
                {
                    "plugin_id": "qqbot",
                    "enabled": flag,
                    "operation_id": f"op-toggle-{index}",
                },
            )
            assert toggled.error is None, toggled.error
        assert (
            load_config_text(path.read_text(encoding="utf-8")).plugins["qqbot"][
                "enabled"
            ]
            is True
        )

        written = await _request(
            service,
            "plugin.config.set",
            {
                "plugin_id": "qqbot",
                "operation_id": "op-config",
                "values": {"app_id": "app-123", "client_secret": "secret-xyz"},
            },
        )
        assert written.error is None, written.error
    finally:
        await service.aclose()
        await app.shutdown()

    restarted = load_config_text(path.read_text(encoding="utf-8"))
    assert restarted.plugins["qqbot"]["app_id"] == "app-123"
    assert restarted.plugins["qqbot"]["enabled"] is True, "写配置把启停状态抹掉了"


@pytest.mark.asyncio
async def test_a_disabled_plugin_cannot_have_its_config_written(tmp_path, monkeypatch):
    """已知限制：停用的插件不加载，配置模型未登记，因此写配置会被拒绝。

    这不是本 ticket 修复的目标，而是把当前边界钉住：管理列表会列出停用的插件，
    但它们的配置表单在重新启用之前不可写。要支持"停用状态下也能配置"，需要在
    发现阶段就导入插件模块只为读取配置模型，属于独立的设计变更。
    """
    _stage_plugin_dirs(tmp_path, monkeypatch)
    service, path, app = await _start_service(tmp_path)
    try:
        disabled = await _request(
            service,
            "plugins.setEnabled",
            {
                "plugin_id": "qqbot",
                "enabled": False,
                "operation_id": "op-disable",
            },
        )
        assert disabled.error is None, disabled.error
        before = path.read_text(encoding="utf-8")

        written = await _request(
            service,
            "plugin.config.set",
            {
                "plugin_id": "qqbot",
                "operation_id": "op-config",
                "values": {"app_id": "x"},
            },
        )

        assert written.error is not None
        assert written.error.code == "plugin_config_unsupported"
        assert path.read_text(encoding="utf-8") == before
    finally:
        await service.aclose()
        await app.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize("missing_provider", [False, True])
async def test_list_preserves_external_contract_rejection(
    tmp_path, monkeypatch, missing_provider
):
    import yaml

    _stage_plugin_dirs(tmp_path, monkeypatch)
    path = tmp_path / "plugin_dirs/hello/manifest.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    raw.update(
        package_contract=1,
        version="1.0.0",
        runtime_api=">=3.0.0 <4.0.0",
        entry="backend/plugin.py",
    )
    if missing_provider:
        raw.update(runtime_api=">=2.0.0 <3.0.0", dependencies=["missing-provider"])
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    service, _, app = await _start_service(tmp_path)
    try:
        response = await _request(service, "plugins.list")
        assert response.error is None
        item = next(
            item for item in response.payload["plugins"] if item["id"] == "hello"
        )
        assert item["state"] == "BLOCKED"
        assert item["diagnostic"]["code"] == (
            "missing_dependency" if missing_provider else "incompatible_runtime"
        )
        assert item["diagnostic"]["field"] == (
            "dependencies[0]" if missing_provider else "runtime_api"
        )
        assert item["diagnostic"]["stage"] == (
            "dependency" if missing_provider else "validation"
        )
        assert item["error"]
    finally:
        await service.aclose()
        await app.shutdown()


@pytest.mark.asyncio
async def test_workspace_candidates_are_visible_unsafe_and_reload_safe(
    tmp_path, monkeypatch
):
    _stage_plugin_dirs(tmp_path, monkeypatch)
    builtin = tmp_path / "plugin_dirs"
    external = tmp_path / "plugins"
    marker = tmp_path / "untrusted-imported"
    for name, plugin_id in [("hello-copy", "hello"), ("manual", "manual")]:
        package = external / name
        (package / "backend").mkdir(parents=True)
        (package / "manifest.yaml").write_text(
            f"api: 2\nid: {plugin_id}\ncapabilities: []\npackage_contract: 1\n"
            "version: 1.0.0\nruntime_api: '>=2.0.0 <3.0.0'\nentry: backend/plugin.py\n",
            encoding="utf-8",
        )
        (package / "backend/plugin.py").write_text(
            "from pathlib import Path\n"
            f"Path({str(marker)!r}).write_text('imported', encoding='utf-8')\n"
            "async def setup(ctx): pass\n",
            encoding="utf-8",
        )
    bad = external / "bad"
    bad.mkdir()
    (bad / "manifest.yaml").write_text("api: 2\ncapabilities: [", encoding="utf-8")
    monkeypatch.setattr(
        "bootstrap.tools._resolve_plugin_dirs", lambda _: [builtin, external]
    )
    service, path, app = await _start_service(tmp_path)
    try:
        response = await _request(service, "plugins.list")
        rows = response.payload["plugins"]
        assert len(rows) == 5
        assert len({row["candidate_id"] for row in rows}) == 5
        conflicts = [row for row in rows if row["id"] == "hello"]
        assert len(conflicts) == 2
        assert {row["source"] for row in conflicts} == {"builtin", "workspace"}
        assert {row["state"] for row in conflicts} == {"CONFLICT"}
        assert all(row["directory"] and row["version"] for row in conflicts)
        assert all(row["diagnostic"]["code"] == "duplicate_id" for row in conflicts)
        manual = next(row for row in rows if row["id"] == "manual")
        assert manual["state"] == "UNTRUSTED"
        assert manual["enabled"] is True
        assert not manual["can_toggle"]
        assert next(row for row in rows if row["id"] == "bad")["state"] == "BLOCKED"
        before = path.read_text(encoding="utf-8")
        for plugin_id in ("hello", "manual", "bad"):
            rejected = await _request(
                service,
                "plugins.setEnabled",
                {
                    "plugin_id": plugin_id,
                    "enabled": True,
                    "operation_id": plugin_id,
                },
            )
            assert rejected.error.code == "plugin_not_admitted"
            assert path.read_text(encoding="utf-8") == before
        # A valid builtin toggle prepares a strict generation. Bad external
        # packages must remain diagnostics rather than aborting unrelated apply.
        changed = await _request(
            service,
            "plugins.setEnabled",
            {
                "plugin_id": "qqbot",
                "enabled": False,
                "operation_id": "disable-builtin",
            },
        )
        assert changed.error is None
        again = await _request(service, "plugins.list")
        assert len(again.payload["plugins"]) == 5
        assert not marker.exists()
    finally:
        await service.aclose()
        await app.shutdown()


@pytest.mark.asyncio
async def test_workspace_directory_changes_wait_for_application_restart(
    tmp_path, monkeypatch
):
    _stage_plugin_dirs(tmp_path, monkeypatch, with_rpc_demo=True)
    builtin, external = tmp_path / "plugin_dirs", tmp_path / "plugins"
    monkeypatch.setattr(
        "bootstrap.tools._resolve_plugin_dirs", lambda _: [builtin, external]
    )

    def stage_external(name, plugin_id, *, version="1.0.0", runtime=">=2.0.0 <3.0.0"):
        package = external / name
        (package / "backend").mkdir(parents=True, exist_ok=True)
        (package / "manifest.yaml").write_text(
            f"api: 2\nid: {plugin_id}\ncapabilities: []\npackage_contract: 1\n"
            f"version: {version}\nruntime_api: '{runtime}'\nentry: backend/plugin.py\n",
            encoding="utf-8",
        )
        (package / "backend/plugin.py").write_text(
            "async def setup(ctx): pass\n", encoding="utf-8"
        )
        return package

    stage_external("manual", "manual")
    removed = stage_external("removed", "removed")
    service, _, app = await _start_service(tmp_path)
    try:
        before = (await _request(service, "plugins.list")).payload["plugins"]
        before_by_id = {row["id"]: row for row in before}
        assert before_by_id["rpc_demo"]["state"] == "ACTIVE"
        assert before_by_id["manual"]["state"] == "UNTRUSTED"
        stage_external("new-copy", "rpc_demo")
        stage_external("manual", "manual", version="2.0.0", runtime=">=3.0.0 <4.0.0")
        shutil.rmtree(removed)

        for index, enabled in enumerate((False, True)):
            changed = await _request(
                service,
                "plugins.setEnabled",
                {
                    "plugin_id": "qqbot",
                    "enabled": enabled,
                    "operation_id": f"toggle-{index}",
                },
            )
            assert changed.error is None
            assert changed.payload["generation"] == index + 2
            rows = (await _request(service, "plugins.list")).payload["plugins"]
            assert {row["candidate_id"] for row in rows} == {
                row["candidate_id"] for row in before
            }
            by_id = {row["id"]: row for row in rows}
            for plugin_id in ("rpc_demo", "hello", "manual", "removed"):
                assert by_id[plugin_id] == before_by_id[plugin_id]
            ping = await _request(service, "plugin.rpc_demo.ping", {"value": index})
            assert ping.error is None
            assert ping.payload == {"pong": index}
    finally:
        await service.aclose()
        await app.shutdown()

    restarted, _, restarted_app = await _start_service(tmp_path)
    try:
        rows = (await _request(restarted, "plugins.list")).payload["plugins"]
        conflict = [row for row in rows if row["id"] == "rpc_demo"]
        assert len(conflict) == 2
        assert {row["state"] for row in conflict} == {"CONFLICT"}
        assert not any(row["id"] == "removed" for row in rows)
        manual = next(row for row in rows if row["id"] == "manual")
        assert manual["version"] == "2.0.0"
        assert manual["state"] == "BLOCKED"
        assert manual["diagnostic"]["code"] == "incompatible_runtime"
        ping = await _request(restarted, "plugin.rpc_demo.ping")
        assert ping.error.code == "unknown_method"
    finally:
        await restarted.aclose()
        await restarted_app.shutdown()
