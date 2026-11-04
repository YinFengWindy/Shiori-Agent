import sys
from unittest.mock import AsyncMock

import pytest

from agent.config_models import Config
from bootstrap.app import AppRuntime, DESKTOP_RUNTIME_FEATURES
from bootstrap.channels import start_channels


@pytest.fixture
def empty_config(monkeypatch):
    monkeypatch.setattr("bootstrap.tools._resolve_plugin_dirs", lambda _: [])
    return Config(provider="", model="", api_key="", model_registrations=[])


@pytest.mark.asyncio
async def test_app_runtime_desktop_mode_enables_message_channels(
    monkeypatch,
    tmp_path,
    empty_config,
):
    start_channel_host = AsyncMock(wraps=start_channels)
    monkeypatch.setattr("bootstrap.app.start_channels", start_channel_host)
    (tmp_path / "scene").mkdir()
    (tmp_path / "scene/state.json").write_text("{}", encoding="utf-8")
    app = AppRuntime(empty_config, tmp_path, features=DESKTOP_RUNTIME_FEATURES)

    try:
        await app.start()

        start_channel_host.assert_awaited_once()
        assert start_channel_host.call_args.kwargs["enable_message_channels"] is True
        assert app.channel_host is not None
        assert (tmp_path / "plugin-data/scene/state.json").read_text() == "{}"
        assert not (tmp_path / "scene/state.json").exists()
    finally:
        await app.shutdown()


@pytest.mark.asyncio
async def test_app_runtime_resolves_channel_hooks_through_its_channel_host(
    tmp_path,
    empty_config,
):
    class _Streaming:
        name = "qqbot"

        async def stop(self):
            pass

        def supports_stream_events(self, chat_id: str) -> bool:
            return True

    app = AppRuntime(empty_config, tmp_path, features=DESKTOP_RUNTIME_FEATURES)

    try:
        await app.start()
        assert app.core is not None and app.channel_host is not None
        directory = app.core.channel_directory
        assert app.core.loop._channel_directory is directory
        assert not directory.supports_stream_events("qqbot", "c2c:u1")

        # Handover swaps the connections of this same long-lived host.
        app.channel_host._channels.append(_Streaming())
        assert directory.supports_stream_events("qqbot", "c2c:u1")
    finally:
        await app.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
async def test_initial_partial_core_failure_forces_unsafe_plugin_cleanup(
    tmp_path, monkeypatch, cancel
):
    import asyncio
    from pathlib import Path
    from shiori_sdk.testing.packages import stage_plugin_package
    from bootstrap.tools import CoreRuntime

    packages = tmp_path / "host_plugins"
    stage_plugin_package(
        Path(__file__).resolve().parents[3] / "tests/fixtures/plugins/restart_required",
        packages / "restart_required",
    )
    monkeypatch.setattr("bootstrap.tools._resolve_plugin_dirs", lambda _: [packages])
    from agent.config_models import Config
    from bootstrap.app import AppRuntime, RuntimeFeatures

    config = Config(
        provider="",
        model="",
        api_key="",
        model_registrations=[],
    )
    app = AppRuntime(
        config,
        tmp_path,
        features=RuntimeFeatures(enable_message_channels=False),
    )
    states = []
    original_start = CoreRuntime.start

    async def partial_start(core):
        await original_start(core)
        states.append(core.plugin_manager._dependency_api("restart_required"))
        if cancel:
            raise asyncio.CancelledError()
        raise RuntimeError("initial start failed")

    monkeypatch.setattr(CoreRuntime, "start", partial_start)
    with pytest.raises(asyncio.CancelledError if cancel else RuntimeError):
        await app.start()
    assert states == [["started", "closed"]]
    assert app.core.plugin_manager.active_plugin_ids == []
    assert app.core.event_bus._closed
    assert app.http_resources._closed


@pytest.mark.asyncio
async def test_initial_setup_cancellation_releases_plugin_and_runtime(
    tmp_path, monkeypatch
):
    import asyncio
    from bootstrap.app import RuntimeFeatures

    package = tmp_path / "host_plugins/waiting"
    (package / "backend").mkdir(parents=True)
    (package / "manifest.yaml").write_text(
        "api: 4\nsdk: '>=4.0.0'\nid: waiting\ninject: [events]\nsupports_hot_unload: false\n",
        encoding="utf-8",
    )
    (package / "backend/plugin.py").write_text(
        "import asyncio\n"
        "from shiori_sdk.core.services import EVENTS\n"
        "async def setup(ctx):\n"
        "    global state\n"
        "    state = ['started']\n"
        "    ctx.expose(state)\n"
        "    ctx.effect('close', lambda: state.append('closed'))\n"
        "    async def on_event(event):\n"
        "        return event\n"
        "    ctx.require(EVENTS).on(str, on_event)\n"
        "    await asyncio.Event().wait()\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "bootstrap.tools._resolve_plugin_dirs", lambda _: [package.parent]
    )
    app = AppRuntime(
        Config(
            provider="",
            model="",
            api_key="",
            model_registrations=[],
        ),
        tmp_path,
        features=RuntimeFeatures(enable_message_channels=False),
    )
    starting = asyncio.create_task(app.start())

    async def wait_for_setup():
        while True:
            if app.core is not None:
                record = next(
                    (
                        record
                        for record in app.core.plugin_manager.discover()
                        if record.plugin_dir == package
                    ),
                    None,
                )
                module = sys.modules.get(record.import_path) if record else None
                if module is not None and hasattr(module, "state"):
                    return module.state
            if starting.done():
                await starting
                raise AssertionError("runtime finished without entering plugin setup")
            await asyncio.sleep(0)

    try:
        state = await asyncio.wait_for(wait_for_setup(), timeout=10)
        assert state == ["started"]
    finally:
        starting.cancel()
        with pytest.raises(asyncio.CancelledError):
            await starting
    assert state == ["started", "closed"]
    assert app.core.plugin_manager.active_plugin_ids == []
    assert app.core.event_bus._closed
    assert app.http_resources._closed


@pytest.mark.asyncio
async def test_start_publishes_accounts_and_stop_drops_the_generation(
    tmp_path, monkeypatch
):
    """Load registers accounts; start is what publishes them and process resources.

    Stop drops the account generation itself. An account registered into that
    generation with no plugin effect would survive plugin teardown, so an
    empty list afterwards means the generation index was discarded.
    """
    from shiori_sdk.core.services import ACCOUNTS
    from bootstrap.app import RuntimeFeatures
    from core.roles.store import RoleStore

    package = tmp_path / "host_plugins" / "account_demo"
    (package / "backend").mkdir(parents=True)
    (package / "manifest.yaml").write_text(
        "api: 4\nsdk: '>=4.0.0'\nid: account_demo\ninject: [accounts]\n",
        encoding="utf-8",
    )
    (package / "backend/plugin.py").write_text(
        "from shiori_sdk.core.services import ACCOUNTS\n"
        "async def setup(ctx):\n"
        "    ctx.require(ACCOUNTS).register(platform='demo', platform_account_id='101',\n"
        "        config_ref='one', role_id='mira', display_name='One')\n",
        encoding="utf-8",
    )
    RoleStore(tmp_path).create_role(role_id="mira", name="Mira", system_prompt="Mira")
    monkeypatch.setattr(
        "bootstrap.tools._resolve_plugin_dirs", lambda _: [package.parent]
    )
    app = AppRuntime(
        Config(
            provider="",
            model="",
            api_key="",
            model_registrations=[],
        ),
        tmp_path,
        features=RuntimeFeatures(enable_message_channels=False),
    )
    await app.start()
    assert app.core is not None and app.core.plugin_manager is not None
    registry = app.core.role_runtime_registry.repository.store.accounts
    assert [row.record.platform_account_id for row in registry.list()] == ["101"]
    assert app._plugin_process_resources._active == app.core.plugin_manager.namespace
    service = app.core.plugin_manager.kernel.get(ACCOUNTS)
    assert service is not None
    registry.register(
        plugin_id="lingering",
        platform="demo",
        platform_account_id="orphan",
        config_ref="orphan",
        token="kept",
        role_id="mira",
        generation=service._generation,
    )
    assert {row.record.platform_account_id for row in registry.list()} == {
        "101",
        "orphan",
    }
    await app.shutdown()
    assert registry.list() == []


def test_desktop_presence_is_app_owned_and_present_before_any_report(
    tmp_path, empty_config
):
    app = AppRuntime(empty_config, tmp_path, features=DESKTOP_RUNTIME_FEATURES)
    assert app.desktop_presence.is_desktop_present() is True


@pytest.mark.asyncio
async def test_started_runtime_serves_proactive_host_and_conversation(
    tmp_path, empty_config
):
    """The kernel serves the proactive port and conversation; the port reads
    this app's desktop presence."""
    from bootstrap.app import RuntimeFeatures
    from shiori_sdk.core.conversation import CONVERSATION
    from shiori_sdk.core.proactive_host import PROACTIVE_HOST

    app = AppRuntime(
        empty_config,
        tmp_path,
        features=RuntimeFeatures(enable_message_channels=False),
    )
    await app.start()
    try:
        assert app.core is not None and app.core.plugin_manager is not None
        kernel = app.core.plugin_manager.kernel
        host = kernel.get(PROACTIVE_HOST)
        assert host is not None and kernel.get(CONVERSATION) is not None
        app.desktop_presence.report(False)
        assert host.user_at_desktop() is False
    finally:
        await app.shutdown()


@pytest.mark.asyncio
async def test_started_runtime_routes_renderer_calls_to_declared_plugin_peers(
    tmp_path, monkeypatch, empty_config
):
    """Real bootstrap must bind peer lookup before a renderer opens communication."""
    from bootstrap.app import RuntimeFeatures
    from desktop_bridge.plugin_requests import DesktopPluginRequestHandler

    packages = tmp_path / "host_plugins"
    for plugin_id, manifest, source in (
        (
            "provider",
            "inject: [rpc]\n",
            "from shiori_sdk.core.services import RPC\n"
            "async def accept(payload):\n"
            "    return {'accepted': payload['text']}\n"
            "async def setup(ctx):\n"
            "    ctx.require(RPC).register('accept', accept)\n",
        ),
        (
            "consumer",
            "dependencies: [provider]\n",
            "async def setup(ctx): pass\n",
        ),
    ):
        package = packages / plugin_id
        (package / "backend").mkdir(parents=True)
        (package / "manifest.yaml").write_text(
            f"api: 4\nsdk: '>=4.0.0'\nid: {plugin_id}\n{manifest}", encoding="utf-8"
        )
        (package / "backend/plugin.py").write_text(source, encoding="utf-8")
    monkeypatch.setattr("bootstrap.tools._resolve_plugin_dirs", lambda _: [packages])
    app = AppRuntime(
        empty_config,
        tmp_path,
        features=RuntimeFeatures(enable_message_channels=False),
    )
    try:
        await app.start()
        assert app.core is not None
        handler = DesktopPluginRequestHandler(app.core.plugin_rpc)
        opened = await handler.handle(
            "plugins.communication.open",
            {"plugin_id": "consumer", "owner": "document", "renderer": "main"},
        )
        assert opened is not None
        result = await handler.handle(
            "provider.accept",
            {
                "text": "delivered through bootstrap",
                "__plugin_context": {
                    "plugin_id": "consumer",
                    "owner": "document",
                    **opened,
                },
            },
        )
        assert result == {"accepted": "delivered through bootstrap"}
    finally:
        await app.shutdown()


@pytest.mark.asyncio
async def test_external_package_approval_is_live_and_bound_to_application_session(
    tmp_path, monkeypatch, empty_config
):
    """Real bootstrap honors old approval and rechecks persisted activation trust."""
    from bootstrap.app import RuntimeFeatures
    from agent.plugin_host.package_fingerprint import inspect_package_content
    from desktop_bridge.runtime.plugin_trust_store import PluginTrustStore

    package = tmp_path / "plugins" / "trusted_demo"
    (package / "backend").mkdir(parents=True)
    (package / "manifest.yaml").write_text(
        "api: 4\nsdk: '>=4.0.0'\nid: trusted_demo\nversion: 1.0.0\n"
        "entry: backend/plugin.py\n",
        encoding="utf-8",
    )
    (package / "backend/plugin.py").write_text(
        "async def setup(ctx):\n    ctx.expose({'ready': True})\n", encoding="utf-8"
    )
    monkeypatch.setattr(
        "bootstrap.tools._resolve_plugin_dirs", lambda _: [package.parent]
    )
    monkeypatch.setenv("SHIORI_DESKTOP_APPLICATION_SESSION_ID", "current-session")
    store = PluginTrustStore(tmp_path)
    fingerprint = inspect_package_content(package).fingerprint
    store.approve(package, fingerprint, approved_session="previous-session")
    app = AppRuntime(
        empty_config, tmp_path, features=RuntimeFeatures(enable_message_channels=False)
    )
    try:
        await app.start()
        assert app.core is not None
        kernel = app.core.plugin_manager
        assert kernel._dependency_api("trusted_demo") == {"ready": True}
        assert [view.describe() for view in kernel.views()][0]["state"] == "ACTIVE"
        # One running generation must observe changes; caching approvals here
        # could silently reactivate code whose permission was withdrawn.
        store.revoke(package)
        [record] = kernel.inspect_candidates()
        assert record.admission is not None
        assert record.admission.code == "trust_required"
        store.approve(package, fingerprint)
        [record] = kernel.inspect_candidates()
        assert record.admission is not None
        assert record.admission.code == "trust_required"
        store.approve(package, fingerprint, approved_session="previous-session")
        [record] = kernel.inspect_candidates()
        assert record.admission is None
    finally:
        await app.shutdown()
