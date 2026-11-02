"""The actual reloadable bridge keeps plugin wire ownership across toggles."""

import asyncio
import pytest

from agent.plugin_host.unload import PluginReloadTimeout
from desktop_bridge.runtime.service import ReloadableDesktopService
from shiori_host_testing.bridge import plugin_bridge_request


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
            "from asyncio import Event\n"
            "class Config(BaseModel):\n"
            "    label: str = 'v1'\n"
            "async def setup(ctx):\n"
            "    items = []\n"
            "    rpc = ctx.require(RPC)\n"
            "    entered, release = Event(), Event()\n"
            "    ctx.expose({'entered': entered, 'release': release})\n"
            "    async def block(payload):\n"
            "        entered.set()\n"
            "        await release.wait()\n"
            "        return {'finished': True}\n"
            "    rpc.register('block', block)\n"
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
        core = bridge.app.core
        assert core is not None and core.plugin_manager is not None
        probe = core.plugin_manager._dependency_api("wire_probe")
        blocked = asyncio.create_task(plugin_bridge_request(bridge, "wire_probe.block"))
        await asyncio.wait_for(probe["entered"].wait(), timeout=1)
        with pytest.raises(PluginReloadTimeout):
            await core.plugin_manager.reload(
                "wire_probe",
                values={"label": "abandoned"},
                raw_values={"label": "abandoned"},
                drain_timeout=0.001,
            )
        assert not pending.done()
        probe["release"].set()
        assert (await blocked).error is None
        request = next(
            event
            for event in reversed(events)
            if event["method"] == "wire_probe.__request"
        )
        await plugin_bridge_request(
            bridge,
            "plugins.communication.reply",
            {
                "plugin_id": "wire_probe",
                "owner": "background",
                "generation": core.plugin_rpc.communication.generation,
                "request_id": request["payload"]["request_id"],
                "result": "still active",
            },
        )
        retained = await pending
        assert retained.error is None and retained.payload == {"result": "still active"}
        for owner in ("background", "caller"):
            await plugin_bridge_request(
                bridge,
                "plugins.communication.close",
                {
                    "plugin_id": "wire_probe",
                    "owner": owner,
                    "generation": core.plugin_rpc.communication.generation,
                },
            )

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
