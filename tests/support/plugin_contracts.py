"""Execute manifest lifecycle contracts through the production plugin host."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from agent.config_models import Config
from agent.plugin_host.manifest import PluginManifest, load_manifest
from agent.plugin_host.record import PluginRecord
from agent.plugin_host.unload import PluginReloadUnsupported, PluginRestartRequired
from bootstrap.tools import CoreRuntime, build_core_runtime
from core.net.http import SharedHttpResources
from infra.process.resources import ProcessResourceOwner
from shiori_sdk.core.scene import SCENE_HOST
from shiori_sdk.core.services import CHANNELS
from shiori_sdk.kernel import Key
from tests.support.plugin_contract_observation import (
    observe_lifecycle,
    snapshot,
    assert_snapshot,
    retained_tasks,
)

ROOT = Path(__file__).resolve().parents[2]

# Explicit valid setup profiles. A new manifest must choose an appropriate case.
PLUGINS = frozenset(
    {
        "affection",
        "browser_use",
        "computer_use",
        "context_pressure",
        "default_memory",
        "desktop_pet",
        "feishu",
        "gpt_sovits_tts",
        "grok_bot",
        "herdr",
        "mcp",
        "meme",
        "memory_optimizer",
        "natural_chat",
        "novelai",
        "observe",
        "plugin_undo",
        "proactive",
        "qq",
        "qqbot",
        "scene",
        "schedule",
        "screen_perception",
        "sensevoice_asr",
        "shell_restore",
        "shell_safety",
        "status_commands",
        "story",
        "telegram",
        "tool_loop_guard",
    }
)


def manifest_ids() -> list[str]:
    """All current manifests, requiring explicit fixture coverage for additions."""
    found = {p.parent.name for p in (ROOT / "plugins").glob("*/manifest.yaml")}
    assert PLUGINS <= found, f"Obsolete contract fixtures: {PLUGINS - found}"
    for plugin_id in found - PLUGINS:
        profile_for(ROOT / "plugins" / plugin_id)
    return sorted(found)


def records_for(plugin_id: str, directory: Path | None = None) -> list[PluginRecord]:
    """Admit repository source packages as test-owned sources, preserving manifests.

    Distribution/ZIP trust is checked separately by installer contracts. These
    snapshots avoid pretending a source frontend is an installed built artifact.
    """
    records: dict[str, PluginRecord] = {}

    def add(name: str) -> None:
        if name in records:
            return
        source = (
            directory
            if name == plugin_id and directory is not None
            else ROOT / "plugins" / name
        )
        manifest = load_manifest(source)
        assert manifest is not None
        records[name] = PluginRecord(
            name, source, source / manifest.entry, "", manifest
        )
        for dependency in manifest.dependencies:
            add(dependency)

    add(plugin_id)
    return list(records.values())


def _require_rpc_profile(manifest: PluginManifest) -> None:
    assert set(manifest.inject) <= {"rpc"} and not (
        manifest.optional_inject
        or manifest.optional_dependencies
        or manifest.provides
        or manifest.dependencies
        or manifest.channels
        or manifest.metadata.get("replaces")
        or manifest.metadata.get("conflicts")
    ), "The rpc fixture only supports plugins needing the RPC binder"


@asynccontextmanager
async def contract_runtime(
    plugin_id: str,
    workspace: Path,
    *,
    directory: Path | None = None,
    profile: str = "repository",
) -> AsyncIterator[tuple[CoreRuntime, ProcessResourceOwner]]:
    """Build real host binders with isolated data and a valid non-network config."""
    records = records_for(plugin_id, directory)
    if profile == "rpc":
        _require_rpc_profile(records[0].manifest)
    else:
        assert (
            profile == "repository" and plugin_id in PLUGINS
        ), "Explicit lifecycle fixture required"
    consumer = workspace / "contract-consumer"
    consumer.mkdir(parents=True)
    (consumer / "manifest.yaml").write_text(
        "api: 4\nsdk: '>=4.0.0'\nid: contract_consumer\nentry: plugin.py\ndependencies: ["
        + plugin_id
        + "]\n"
        + "inject: "
        + json.dumps(list(records[0].manifest.provides))
        + "\n",
        encoding="utf-8",
    )
    (consumer / "plugin.py").write_text(
        "from shiori_sdk.kernel import Key, PluginStarted\n"
        "async def setup(ctx):\n"
        "    async def echo(event): return event\n"
        "    ctx.on(PluginStarted, echo)\n"
        "    ctx.expose({'token': object(), 'values': {name: ctx.require(Key(name)) for name in "
        + repr(list(records[0].manifest.provides))
        + "}})\n",
        encoding="utf-8",
    )
    manifest = load_manifest(consumer)
    assert manifest is not None
    records.append(
        PluginRecord(
            "contract_consumer", consumer, consumer / "plugin.py", "", manifest
        )
    )
    values = {r.manifest.id: {"enabled": True} for r in records}
    if "default_memory" in values:
        values["default_memory"].update(
            embedding_api_key="contract",
            embedding_model="contract",
            embedding_base_url="http://127.0.0.1:1",
        )
    config = Config(
        provider="openai",
        model="contract",
        api_key="contract",
        base_url="http://127.0.0.1:1",
        plugins=values,
        raw_plugin_configs=values,
    )
    http = SharedHttpResources()
    resources = ProcessResourceOwner()
    publication = SimpleNamespace(core=None)
    core = build_core_runtime(
        config,
        workspace,
        http,
        process_resources=resources,
        plugin_discovery_snapshot=records,
        published_runtime=lambda: publication,
    )
    publication.core = core
    try:
        yield core, resources
    finally:
        await resources.close()
        await core.stop(force=True)
        await core.memory_runtime.aclose()
        core.session_manager._store.close()
        await http.aclose()


async def verify_contract(
    plugin_id: str,
    workspace: Path,
    *,
    directory: Path | None = None,
    profile: str = "repository",
    rpc_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Real setup/reload/stop, with a real dependent and pre-teardown leak checks."""
    async with contract_runtime(
        plugin_id, workspace, directory=directory, profile=profile
    ) as (core, resources):
        manager = core.plugin_manager
        assert manager is not None
        baseline = snapshot(core)
        # Cold instance and replacement both enter an already-published host.
        # Publication timing itself has separate cold-start lifecycle coverage.
        resources.publish(manager.namespace)
        scene_host = manager.kernel.get(SCENE_HOST)
        if scene_host is not None:
            scene_host.publish()
        with observe_lifecycle() as observation:
            try:
                await manager.load_all()
                assert all(view.state == "ACTIVE" for view in manager.views()), [
                    v.describe() for v in manager.views()
                ]
                for record in manager.discover():
                    for key in record.manifest.provides:
                        supplied = manager.kernel._providers.get(key)
                        assert (
                            supplied is not None and supplied[0] == record.manifest.id
                        ), f"{record.manifest.id} did not provide declared {key}"
                consumer_key = Key("plugin:contract_consumer")
                consumer = manager.kernel.get(consumer_key)
                assert consumer is not None
                for key, value in consumer["values"].items():
                    assert value is manager.kernel.get(Key(key))
                channels = manager.kernel.get(CHANNELS)
                for candidate in manager.discover():
                    declared = {channel.name for channel in candidate.manifest.channels}
                    contributed = {
                        channel.name
                        for channel in channels._by_plugin.get(
                            candidate.manifest.id, ()
                        )
                    }
                    assert contributed == declared, (
                        candidate.manifest.id,
                        declared,
                        contributed,
                    )
                cold = snapshot(core)
                cold_registration = observation.registration_order()
                cold_tasks = list(observation.spawned)
                retained = dict(resources._resources)
                persistent_tasks = retained_tasks(retained)
                record = next(
                    r for r in manager.discover() if r.manifest.id == plugin_id
                )
                values = dict(manager._settings.plugin_configs[plugin_id])
                raw = dict(manager._settings.raw_plugin_configs[plugin_id])
                if record.manifest.channels or not record.manifest.supports_hot_unload:
                    scope = manager.kernel.scope(plugin_id)
                    for operation in (
                        lambda: manager.reload(
                            plugin_id, values=values, raw_values=raw, drain_timeout=1
                        ),
                        lambda: manager.set_enabled(
                            plugin_id,
                            values={**values, "enabled": False},
                            raw_values={**raw, "enabled": False},
                            drain_timeout=1,
                        ),
                    ):
                        try:
                            await operation()
                        except (PluginReloadUnsupported, PluginRestartRequired):
                            pass
                        else:
                            raise AssertionError("restart-only closure was replaced")
                        assert manager.kernel.scope(plugin_id) is scope
                        assert_snapshot(snapshot(core), cold)
                else:
                    observation.registrations.clear()
                    observation.spawned.clear()
                    result = await manager.reload(
                        plugin_id, values=values, raw_values=raw, drain_timeout=1
                    )
                    assert not result.cleanup_errors, (
                        "reload reported cleanup errors",
                        result.cleanup_errors,
                    )
                    assert all(view.state == "ACTIVE" for view in manager.views()), [
                        v.describe() for v in manager.views()
                    ]
                    assert_snapshot(snapshot(core), cold)
                    assert observation.registration_order() == [
                        item
                        for item in cold_registration
                        if item[0] in result.plugin_ids
                    ], "scope registration order differs from cold setup"
                    assert (
                        resources._resources == retained
                    ), "process resources were not retained across reload"
                    assert all(not task.done() for task in persistent_tasks)
                    assert [
                        (owner, name) for owner, name, _ in observation.spawned
                    ] == [
                        (owner, name)
                        for owner, name, task in cold_tasks
                        if owner in result.plugin_ids and task not in persistent_tasks
                    ], "task creation order differs from cold setup (retained tasks are unchanged)"
                    replacement = manager.kernel.get(consumer_key)
                    assert (
                        replacement is not None
                        and replacement["token"] is not consumer["token"]
                    ), "dependent was not set up again"
                    for key, value in replacement["values"].items():
                        assert value is manager.kernel.get(
                            Key(key)
                        ), "dependent retained an old provider"
                methods = sorted(
                    name.removeprefix(plugin_id + ".")
                    for name in core.plugin_rpc._entries
                    if name.startswith(plugin_id + ".")
                )
                services = [
                    {
                        "service_id": key[1],
                        "contract": entry.descriptor["contract"],
                        "methods": sorted(entry.methods),
                    }
                    for key, entry in core.plugin_rpc.services._entries.items()
                    if key[0] == plugin_id
                ]
                if rpc_contract is not None:
                    assert methods == rpc_contract["methods"], (
                        "RPC registration coverage differs from generated contract",
                        plugin_id,
                        methods,
                        rpc_contract["methods"],
                    )
                    assert services == rpc_contract["services"], (
                        "Service registration coverage differs from generated contract",
                        plugin_id,
                        services,
                        rpc_contract["services"],
                    )
                if profile == "rpc":
                    from desktop_bridge.plugin_requests import (
                        DesktopPluginRequestHandler,
                    )

                    handler = DesktopPluginRequestHandler(core.plugin_rpc)
                    opened = await handler.handle(
                        "plugins.communication.open",
                        {"plugin_id": "contract_consumer", "owner": "contract"},
                    )
                    assert opened is not None
                    reply = await handler.handle(
                        plugin_id + ".ping",
                        {
                            "__plugin_context": {
                                **opened,
                                "plugin_id": "contract_consumer",
                                "owner": "contract",
                            }
                        },
                    )
                    assert reply is not None
                if not (
                    record.manifest.channels or not record.manifest.supports_hot_unload
                ):
                    disabled = await manager.set_enabled(
                        plugin_id,
                        values={**values, "enabled": False},
                        raw_values={**raw, "enabled": False},
                        drain_timeout=1,
                    )
                    assert not disabled.cleanup_errors, (
                        "disable reported cleanup errors",
                        disabled.cleanup_errors,
                    )
                    assert not {plugin_id, "contract_consumer"}.intersection(
                        manager.kernel._scopes
                    ), "disable left a scope alive before final host shutdown"
                    assert not any(
                        key[0] in {plugin_id, "contract_consumer"}
                        for key in resources._resources
                    ), "disable retained a plugin process resource"
                await manager.terminate_all(force=True)
                await resources.drain()
                assert_snapshot(snapshot(core), baseline)
                assert not manager.kernel._scopes
                assert (
                    not resources._resources
                    and not resources._attachments
                    and not resources._retained
                    and not resources._publication_callbacks
                )
                await asyncio.sleep(0)
                observation.assert_closed()
                if plugin_id in {"observe", "default_memory"} and directory in (
                    None,
                    ROOT / "plugins" / plugin_id,
                ):
                    assert (
                        observation.connections
                    ), "database fixture did not open a real connection"
                return {
                    "plugin_id": plugin_id,
                    "case_id": "configured",
                    "rpc_methods": methods,
                    "services": services,
                    "observed_tasks": len(observation.tasks),
                    "closed_sqlite_connections": len(observation.connections),
                    "retained_process_resources": len(retained),
                }
            finally:
                await observation.emergency_cleanup()


def profile_for(directory: Path) -> str:
    """Resolve repository fixtures or the RPC-only scaffold's real ``ping`` case."""
    if (
        directory.parent.resolve() == (ROOT / "plugins").resolve()
        and directory.name in PLUGINS
    ):
        return "repository"
    file = directory / "tests/contract.json"
    assert (
        file.is_file()
    ), f"{directory.name}: add an explicit lifecycle fixture or tests/contract.json"
    value = json.loads(file.read_text(encoding="utf-8"))
    assert value == {"profile": "rpc"}, f"Unsupported plugin lifecycle profile: {file}"
    manifest = load_manifest(directory)
    assert manifest is not None
    _require_rpc_profile(manifest)
    return "rpc"
