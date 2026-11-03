"""The actual reloadable bridge keeps plugin wire ownership across toggles."""

import asyncio
import sys
from types import ModuleType, SimpleNamespace
import pytest

from desktop_bridge.request_dispatcher import BridgeRequestDispatcher
from desktop_bridge.runtime.service import ReloadableDesktopService
from shiori_host_testing.bridge import plugin_bridge_request


@pytest.fixture
async def rollback_runtime(plugin_runtime, tmp_path, monkeypatch):
    state = SimpleNamespace(
        new_attempted=False,
        fail_consumer_restore=False,
        setup_entered=asyncio.Event(),
        setup_release=asyncio.Event(),
        call_entered=asyncio.Event(),
        call_release=asyncio.Event(),
    )
    state.setup_release.set()
    module = ModuleType("rollback_lifecycle_test")
    vars(module)["state"] = state
    monkeypatch.setitem(sys.modules, module.__name__, module)
    common = """
from shiori_sdk.core.services import RPC, CONFIG, DEPENDENCIES
from pydantic import BaseModel
from rollback_lifecycle_test import state
class Config(BaseModel):
    label: str = 'old'
"""
    rpc = """
    calls = []
    async def echo(payload):
        calls.append(label)
        return {'labels': list(calls)}
    async def block(payload):
        state.call_entered.set()
        await state.call_release.wait()
        return {'label': label}
    ctx.require(RPC).register('echo', echo)
    ctx.require(RPC).register('block', block)
    ctx.expose({'label': label})
"""
    sources = {
        "rollback_target": (
            "inject: [rpc, config]\nconfig_model: Config\n",
            """
async def setup(ctx):
    label = ctx.require(CONFIG).get('label')
    if label == 'fail':
        state.new_attempted = True
        state.setup_entered.set()
        await state.setup_release.wait()
        raise RuntimeError('new configuration cannot start')
""",
        ),
        "rollback_consumer": (
            "inject: [rpc, dependencies]\ndependencies: [rollback_target]\n",
            """
async def setup(ctx):
    label = ctx.require(DEPENDENCIES).require('rollback_target')['label']
    if state.fail_consumer_restore and state.new_attempted and label == 'old':
        raise RuntimeError('consumer cannot restore')
""",
        ),
        "rollback_bystander": (
            "inject: [rpc]\n",
            "\nasync def setup(ctx):\n    label = 'bystander'\n",
        ),
    }
    packages = {}
    for plugin_id, (manifest, setup) in sources.items():
        package = tmp_path / "source" / plugin_id
        (package / "backend").mkdir(parents=True)
        (package / "manifest.yaml").write_text(
            f"api: 4\nsdk: '>=4.0.0'\nid: {plugin_id}\n{manifest}", encoding="utf-8"
        )
        (package / "backend/plugin.py").write_text(
            common + setup + rpc, encoding="utf-8"
        )
        packages[plugin_id] = package
    monkeypatch.setattr(
        "shiori_host_testing.pytest_plugin.plugin_directory", packages.__getitem__
    )
    async with plugin_runtime(
        tuple(packages), '[plugins.rollback_target]\nlabel="old"\n'
    ) as (bridge, path):
        assert isinstance(bridge, ReloadableDesktopService)
        yield bridge, path, state


async def _open_context(bridge, plugin_id, owner):
    opened = await plugin_bridge_request(
        bridge, "plugins.communication.open", {"plugin_id": plugin_id, "owner": owner}
    )
    assert opened.error is None
    return {"plugin_id": plugin_id, "owner": owner, **opened.payload}


async def _save_target(bridge, label, operation_id):
    return await plugin_bridge_request(
        bridge,
        "plugin.config.set",
        {
            "plugin_id": "rollback_target",
            "values": {"label": label},
            "operation_id": operation_id,
        },
    )


async def _start_background_call(bridge, context, events):
    registered = await plugin_bridge_request(
        bridge, "plugins.communication.register", {**context, "name": "wait"}
    )
    assert registered.error is None
    requested = asyncio.Event()

    def receive(event):
        if event["method"] == f"{context['plugin_id']}.__request":
            events.append(event)
            requested.set()

    bridge.add_event_listener(receive)
    pending = asyncio.create_task(
        plugin_bridge_request(
            bridge,
            "plugins.communication.call",
            {**context, "name": "wait", "payload": {}},
        )
    )
    try:
        await asyncio.wait_for(requested.wait(), timeout=1)
    finally:
        bridge.remove_event_listener(receive)
    return pending


async def test_queued_old_rpc_cannot_mutate_reloaded_instance(rollback_runtime):
    bridge, _path, _state = rollback_runtime
    old = await _open_context(bridge, "rollback_target", "old")
    dispatcher = BridgeRequestDispatcher(policy_resolver=bridge.resolve_method_policy)
    entered, release, reloaded = asyncio.Event(), asyncio.Event(), asyncio.Event()
    results = {}

    async def hold_write_lane():
        entered.set()
        await release.wait()

    async def queued_rpc():
        results["stale"] = await plugin_bridge_request(
            bridge, "rollback_target.echo", {"__plugin_context": old}
        )

    async def reload():
        results["reload"] = await _save_target(bridge, "new", "queued-rpc-reload")
        reloaded.set()

    dispatcher.submit({"method": "roles.update"}, hold_write_lane)
    try:
        await asyncio.wait_for(entered.wait(), timeout=1)
        dispatcher.submit({"method": "rollback_target.echo"}, queued_rpc)
        dispatcher.submit({"method": "plugin.config.set"}, reload)
        await asyncio.wait_for(reloaded.wait(), timeout=1)
        assert results["reload"].error is None
        assert "stale" not in results
    finally:
        release.set()
        await dispatcher.aclose()

    stale = results["stale"]
    assert stale.error is not None and stale.error.code == "plugin_invalid_owner"
    fresh = await _open_context(bridge, "rollback_target", "new")
    assert fresh["generation"] == old["generation"]
    accepted = await plugin_bridge_request(
        bridge, "rollback_target.echo", {"__plugin_context": fresh}
    )
    # A rejected queued call must not have reached the replacement handler.
    assert accepted.error is None and accepted.payload == {"labels": ["new"]}


async def test_failed_reload_renews_entire_restored_closure_before_error_response(
    rollback_runtime,
):
    bridge, path, _state = rollback_runtime
    before = path.read_text(encoding="utf-8")
    contexts = {
        name: await _open_context(bridge, name, f"old-{name}")
        for name in ("rollback_target", "rollback_consumer", "rollback_bystander")
    }
    bystander = await plugin_bridge_request(bridge, "rollback_bystander.echo")
    assert bystander.payload == {"labels": ["bystander"]}
    requests = []
    pending = await _start_background_call(
        bridge, contexts["rollback_consumer"], requests
    )
    notifications = []
    notification_started, deliver_notification = asyncio.Event(), asyncio.Event()

    async def receive(event):
        if event["method"] == "plugins.reloaded":
            notification_started.set()
            await deliver_notification.wait()
            notifications.append(event)

    bridge.add_event_listener(receive)
    saving = asyncio.create_task(_save_target(bridge, "fail", "failed-save"))
    try:
        await asyncio.wait_for(notification_started.wait(), timeout=1)
        assert (
            not saving.done()
        ), "failed-save response overtook its recovery notification"
    finally:
        deliver_notification.set()
    result = await saving
    assert result.error is not None and result.error.code == "plugin_reload_failed"
    assert result.error.details["restore_failed"] == []
    assert [event["id"] for event in notifications] == ["failed-save"]
    assert notifications[0]["payload"] == {
        "generation": bridge.app.generation,
        "plugin_ids": ["rollback_target", "rollback_consumer"],
        "disabled_plugin_ids": [],
    }
    assert path.read_text(encoding="utf-8") == before == bridge.settings.config_text
    assert bridge.app.config.plugins["rollback_target"] == {"label": "old"}
    cancelled = await pending
    assert cancelled.error is not None and cancelled.error.code == "plugin_reloading"

    for plugin_id in ("rollback_target", "rollback_consumer"):
        revoked = await plugin_bridge_request(
            bridge, "plugins.communication.native.authorize", contexts[plugin_id]
        )
        assert (
            revoked.error is not None and revoked.error.code == "plugin_invalid_owner"
        )
        stale_registration = await plugin_bridge_request(
            bridge,
            "plugins.communication.register",
            {**contexts[plugin_id], "name": "wait"},
        )
        assert (
            stale_registration.error is not None
            and stale_registration.error.code == "plugin_invalid_owner"
        )
        fresh = await _open_context(bridge, plugin_id, f"new-{plugin_id}")
        native = await plugin_bridge_request(
            bridge, "plugins.communication.native.authorize", fresh
        )
        assert native.error is None
        echo = await plugin_bridge_request(bridge, f"{plugin_id}.echo")
        assert echo.error is None and echo.payload == {"labels": ["old"]}
        pending = await _start_background_call(bridge, fresh, requests)
        reply = await plugin_bridge_request(
            bridge,
            "plugins.communication.reply",
            {
                **fresh,
                "request_id": requests[-1]["payload"]["request_id"],
                "result": "restored",
            },
        )
        assert reply.error is None
        received = await pending
        assert received.error is None and received.payload == {"result": "restored"}

    retained = await plugin_bridge_request(
        bridge, "plugins.communication.native.authorize", contexts["rollback_bystander"]
    )
    assert retained.error is None
    bystander = await plugin_bridge_request(bridge, "rollback_bystander.echo")
    assert bystander.payload == {"labels": ["bystander", "bystander"]}
    # A failed operation never becomes a successful idempotency memo.
    retried = await _save_target(bridge, "new", "failed-save")
    assert retried.error is None
    assert (await plugin_bridge_request(bridge, "rollback_target.echo")).payload == {
        "labels": ["new"]
    }
    assert len(notifications) == 2
    replay = await _save_target(bridge, "new", "failed-save")
    assert replay == retried
    assert len(notifications) == 2
    assert (await plugin_bridge_request(bridge, "rollback_target.echo")).payload == {
        "labels": ["new", "new"]
    }
    disabled = await plugin_bridge_request(
        bridge,
        "plugins.setEnabled",
        {
            "plugin_id": "rollback_target",
            "enabled": False,
            "operation_id": "disable-restored",
        },
    )
    assert disabled.error is None
    assert notifications[-1]["payload"]["disabled_plugin_ids"] == [
        "rollback_target",
        "rollback_consumer",
    ]


async def test_generated_trust_operation_waits_for_publication_and_replay_is_quiet(
    tmp_path, monkeypatch
):
    from agent.config import load_config_text
    from bootstrap.app import AppRuntime, RuntimeFeatures

    package = tmp_path / "plugins" / "trust_probe"
    (package / "backend").mkdir(parents=True)
    (package / "manifest.yaml").write_text(
        "api: 4\nsdk: '>=4.0.0'\nid: trust_probe\nversion: 1.0.0\nentry: backend/plugin.py\ninject: [rpc]\n",
        encoding="utf-8",
    )
    (package / "backend/plugin.py").write_text(
        "from shiori_sdk.core.services import RPC\n"
        "async def setup(ctx):\n"
        "    values = []\n"
        "    async def echo(payload):\n"
        "        values.append('active')\n"
        "        return {'values': list(values)}\n"
        "    ctx.require(RPC).register('echo', echo)\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "bootstrap.tools._resolve_plugin_dirs", lambda _: [package.parent]
    )
    text = "[llm]\nregistrations = []\n[plugins.trust_probe]\nenabled = false\n"
    path = tmp_path / "config.toml"
    path.write_text(text, encoding="utf-8")
    app = AppRuntime(
        load_config_text(text),
        tmp_path,
        features=RuntimeFeatures(enable_message_channels=False),
    )
    try:
        await app.start()
        assert app.core is not None
        bridge = ReloadableDesktopService(
            app, path, app.core.role_runtime_registry.repository.store
        )
        try:
            roster = await plugin_bridge_request(bridge, "plugins.list")
            candidate = roster.payload["plugins"][0]
            assert candidate["can_trust"] is True, candidate["diagnostic"]
            payload = {
                "candidate_id": candidate["candidate_id"],
                "fingerprint": candidate["trust_fingerprint"],
                "enable": True,
            }
            notifications = []
            entered, deliver = asyncio.Event(), asyncio.Event()

            async def receive(event):
                if event["method"] == "plugins.reloaded":
                    entered.set()
                    await deliver.wait()
                    notifications.append(event)

            bridge.add_event_listener(receive)
            trusting = asyncio.create_task(
                plugin_bridge_request(bridge, "plugins.trust", payload)
            )
            try:
                await asyncio.wait_for(entered.wait(), timeout=1)
                assert not trusting.done()
            finally:
                deliver.set()
            result = await trusting
            assert result.error is None
            assert [event["id"] for event in notifications] == [
                result.payload["operation_id"]
            ]
            assert (
                await plugin_bridge_request(bridge, "trust_probe.echo")
            ).payload == {"values": ["active"]}
            replay = await plugin_bridge_request(
                bridge,
                "plugins.trust",
                {**payload, "operation_id": result.payload["operation_id"]},
            )
            assert replay.error is None and replay.payload == result.payload
            assert len(notifications) == 1
            assert (
                await plugin_bridge_request(bridge, "trust_probe.echo")
            ).payload == {"values": ["active", "active"]}
        finally:
            await bridge.aclose()
    finally:
        await app.shutdown()


async def test_commit_failure_publishes_restored_instances_without_saving(
    rollback_runtime, monkeypatch
):
    bridge, path, _state = rollback_runtime
    before = path.read_text(encoding="utf-8")
    notifications = []
    bridge.add_event_listener(notifications.append)

    from desktop_bridge import config_transaction

    save_json = config_transaction.atomic_save_json

    def fail_commit(path, data, **kwargs):
        if data["state"] == "committed":
            raise OSError("disk unavailable")
        return save_json(path, data, **kwargs)

    monkeypatch.setattr(config_transaction, "atomic_save_json", fail_commit)
    failed = await _save_target(bridge, "new", "commit-failure")
    assert failed.error is not None and failed.error.code == "runtime_commit_failed"
    assert failed.error.message == "disk unavailable"
    assert failed.error.details["restore_failed"] == []
    assert len(notifications) == 1 and notifications[0]["method"] == "plugins.reloaded"
    assert notifications[0]["payload"]["plugin_ids"] == [
        "rollback_target",
        "rollback_consumer",
    ]
    assert notifications[0]["payload"]["disabled_plugin_ids"] == []
    assert path.read_text(encoding="utf-8") == before == bridge.settings.config_text
    assert bridge.app.config.plugins["rollback_target"] == {"label": "old"}
    assert (await plugin_bridge_request(bridge, "rollback_target.echo")).payload == {
        "labels": ["old"]
    }


async def test_partial_restore_publishes_current_failed_roster(rollback_runtime):
    bridge, path, state = rollback_runtime
    before = path.read_text(encoding="utf-8")
    state.fail_consumer_restore = True
    notifications = []
    bridge.add_event_listener(notifications.append)
    failed = await _save_target(bridge, "fail", "partial-restore")
    assert failed.error is not None and failed.error.code == "plugin_reload_failed"
    assert failed.error.details["restore_failed"] == ["rollback_consumer"]
    assert len(notifications) == 1 and notifications[0]["method"] == "plugins.reloaded"
    assert notifications[0]["payload"]["plugin_ids"] == [
        "rollback_target",
        "rollback_consumer",
    ]
    assert notifications[0]["payload"]["disabled_plugin_ids"] == []
    roster = await plugin_bridge_request(bridge, "plugins.list")
    states = {row["id"]: row["state"] for row in roster.payload["plugins"]}
    assert states == {
        "rollback_target": "ACTIVE",
        "rollback_consumer": "FAILED",
        "rollback_bystander": "ACTIVE",
    }
    unavailable = await plugin_bridge_request(
        bridge,
        "plugins.communication.open",
        {"plugin_id": "rollback_consumer", "owner": "retry"},
    )
    assert (
        unavailable.error is not None and unavailable.error.code == "plugin_unavailable"
    )
    fresh = await _open_context(bridge, "rollback_target", "restored")
    assert (
        await plugin_bridge_request(
            bridge, "plugins.communication.native.authorize", fresh
        )
    ).error is None
    assert path.read_text(encoding="utf-8") == before == bridge.settings.config_text


async def test_abandoned_drain_keeps_mounted_owner_without_replacement_event(
    rollback_runtime, monkeypatch
):
    bridge, path, state = rollback_runtime
    before = path.read_text(encoding="utf-8")
    old = await _open_context(bridge, "rollback_target", "mounted")
    events = []
    pending = await _start_background_call(bridge, old, events)
    bridge.add_event_listener(events.append)
    monkeypatch.setattr(
        "desktop_bridge.runtime.apply.PLUGIN_RELOAD_DRAIN_TIMEOUT_SECONDS", 0.001
    )
    blocked = asyncio.create_task(
        plugin_bridge_request(bridge, "rollback_target.block")
    )
    await asyncio.wait_for(state.call_entered.wait(), timeout=1)
    try:
        failed = await _save_target(bridge, "new", "drain-failure")
        assert failed.error is not None and failed.error.code == "plugin_reload_busy"
        assert not pending.done()
        assert [
            event for event in events if event["method"] == "plugins.reloaded"
        ] == []
        assert (
            await plugin_bridge_request(
                bridge, "plugins.communication.native.authorize", old
            )
        ).error is None
        await plugin_bridge_request(
            bridge,
            "plugins.communication.reply",
            {
                **old,
                "request_id": events[0]["payload"]["request_id"],
                "result": "unchanged",
            },
        )
        assert (await pending).payload == {"result": "unchanged"}
        assert path.read_text(encoding="utf-8") == before == bridge.settings.config_text
    finally:
        state.call_release.set()
        await blocked


async def test_cancelled_failed_save_still_publishes_restored_closure(rollback_runtime):
    bridge, path, state = rollback_runtime
    before = path.read_text(encoding="utf-8")
    state.setup_release.clear()
    notifications = []
    bridge.add_event_listener(notifications.append)
    saving = asyncio.create_task(_save_target(bridge, "fail", "cancelled-failure"))
    await asyncio.wait_for(state.setup_entered.wait(), timeout=1)
    saving.cancel()
    state.setup_release.set()
    with pytest.raises(asyncio.CancelledError):
        await saving
    assert [event["id"] for event in notifications] == ["cancelled-failure"]
    assert notifications[0]["method"] == "plugins.reloaded"
    assert notifications[0]["payload"]["plugin_ids"] == [
        "rollback_target",
        "rollback_consumer",
    ]
    assert notifications[0]["payload"]["disabled_plugin_ids"] == []
    fresh = await _open_context(bridge, "rollback_target", "after-cancellation")
    assert (
        await plugin_bridge_request(
            bridge, "plugins.communication.native.authorize", fresh
        )
    ).error is None
    assert (await plugin_bridge_request(bridge, "rollback_target.echo")).payload == {
        "labels": ["old"]
    }
    assert path.read_text(encoding="utf-8") == before == bridge.settings.config_text


async def test_plugin_wire_routes_events_and_reports_disabled_contexts(
    plugin_runtime, tmp_path, monkeypatch
):
    packages = {}
    for plugin_id in ("wire_probe", "bystander"):
        package = tmp_path / "source" / plugin_id
        (package / "backend").mkdir(parents=True)
        (package / "manifest.yaml").write_text(
            f"api: 4\nsdk: '>=4.0.0'\nid: {plugin_id}\ninject: [rpc]\n"
            "config_model: Config\n",
            encoding="utf-8",
        )
        (package / "backend/plugin.py").write_text(
            "from shiori_sdk.core.services import RPC\n"
            "from pydantic import BaseModel\n"
            "class Config(BaseModel):\n"
            "    label: str = 'v1'\n"
            "async def setup(ctx):\n"
            "    items = []\n"
            "    rpc = ctx.require(RPC)\n"
            "    async def append(payload):\n"
            "        items.append(payload['text'])\n"
            "        await rpc.emit('changed', {'items': list(items)})\n"
            "        return {'items': list(items)}\n"
            "    rpc.register('append', append)\n",
            encoding="utf-8",
        )
        packages[plugin_id] = package
    monkeypatch.setattr(
        "shiori_host_testing.pytest_plugin.plugin_directory", packages.__getitem__
    )
    async with plugin_runtime(tuple(packages)) as (bridge, _path):
        assert isinstance(bridge, ReloadableDesktopService)
        events = []
        requested = asyncio.Event()

        def receive(event):
            events.append(event)
            if event["method"] == "wire_probe.__request":
                requested.set()

        bridge.add_event_listener(receive)

        async def start_background_request():
            requested.clear()
            contexts = {}
            for owner in ("background", "caller"):
                opened = await plugin_bridge_request(
                    bridge,
                    "plugins.communication.open",
                    {"plugin_id": "wire_probe", "owner": owner},
                )
                assert opened.error is None
                contexts[owner] = {
                    "plugin_id": "wire_probe",
                    "owner": owner,
                    **opened.payload,
                }
            registered = await plugin_bridge_request(
                bridge,
                "plugins.communication.register",
                {**contexts["background"], "name": "wait"},
            )
            assert registered.error is None
            pending = asyncio.create_task(
                plugin_bridge_request(
                    bridge,
                    "plugins.communication.call",
                    {**contexts["caller"], "name": "wait", "payload": {}},
                )
            )
            await asyncio.wait_for(requested.wait(), timeout=1)
            return pending

        result = await plugin_bridge_request(
            bridge, "wire_probe.append", {"text": "one"}
        )
        assert result.error is None
        assert result.payload == {"items": ["one"]}
        changed = next(
            event for event in events if event["method"] == "wire_probe.changed"
        )
        assert changed["payload"] == {"items": ["one"]}
        assert changed["pluginGeneration"]
        legacy = await plugin_bridge_request(
            bridge, "plugin.wire_probe.append", {"text": "legacy"}
        )
        assert legacy.error is not None and legacy.error.code == "unknown_method"

        pending = await start_background_request()
        reloaded = await plugin_bridge_request(
            bridge,
            "plugin.config.set",
            {
                "plugin_id": "wire_probe",
                "values": {"label": "v2"},
                "operation_id": "reload-probe",
            },
        )
        assert reloaded.error is None
        cancelled = await pending
        assert cancelled.error is not None
        assert cancelled.error.code == "plugin_reloading"
        assert cancelled.error.message == "插件正在重载"
        assert cancelled.error.details == {"reason": "plugin_reloading"}

        pending = await start_background_request()
        disabled = await plugin_bridge_request(
            bridge,
            "plugins.setEnabled",
            {
                "plugin_id": "wire_probe",
                "enabled": False,
                "operation_id": "disable-probe",
            },
        )
        assert disabled.error is None
        cancelled = await pending
        assert cancelled.error is not None
        assert cancelled.error.code == "plugin_unavailable"
        assert cancelled.error.details == {"reason": "plugin_disabled"}
        notification = next(event for event in events if event["id"] == "disable-probe")
        assert notification["method"] == "plugins.reloaded"
        assert notification["payload"]["plugin_ids"] == ["wire_probe"]
        assert notification["payload"]["disabled_plugin_ids"] == ["wire_probe"]
        other = await plugin_bridge_request(
            bridge, "bystander.append", {"text": "unaffected"}
        )
        assert other.error is None and other.payload == {"items": ["unaffected"]}
        enabled = await plugin_bridge_request(
            bridge,
            "plugins.setEnabled",
            {
                "plugin_id": "wire_probe",
                "enabled": True,
                "operation_id": "enable-probe",
            },
        )
        assert enabled.error is None
        notification = next(event for event in events if event["id"] == "enable-probe")
        assert notification["payload"]["disabled_plugin_ids"] == []
        fresh = await plugin_bridge_request(
            bridge, "wire_probe.append", {"text": "fresh"}
        )
        assert fresh.error is None and fresh.payload == {"items": ["fresh"]}
