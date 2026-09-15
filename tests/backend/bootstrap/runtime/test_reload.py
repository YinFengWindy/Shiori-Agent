from dataclasses import replace
from unittest.mock import AsyncMock

import pytest

from agent.config_models import Config, ModelRegistration
from bootstrap.app import AppRuntime, RuntimeFeatures


@pytest.mark.asyncio
async def test_empty_application_hot_reload_preserves_shared_state_and_old_lease(
    tmp_path, monkeypatch
):
    monkeypatch.setattr("bootstrap.tools._resolve_plugin_dirs", lambda _: [])
    config = Config(
        provider="",
        model="",
        api_key="",
        model_registrations=[],
        memory_optimizer_enabled=False,
    )
    app = AppRuntime(
        config,
        tmp_path,
        features=RuntimeFeatures(enable_message_channels=False, enable_proactive=False),
    )
    await app.start()
    lease = app.acquire()
    original = app.core
    try:
        prepared = await app.prepare(replace(config, max_tokens=2048))
        assert app.generation == 1
        assert prepared.core.loop is not original.loop
        assert prepared.core.session_manager is original.session_manager
        assert prepared.core.bus is original.bus
        commits = []
        await app.publish(prepared, commit=lambda: commits.append(app.generation))
        assert commits == [1]
        assert app.generation == 2
        assert app.agent_loop.max_iterations == config.max_iterations
        assert lease.core is original
        assert not original.event_bus._closed
        await lease.release()
        assert original.event_bus._closed
    finally:
        await lease.release()
        await app.shutdown()


@pytest.mark.asyncio
async def test_persistence_failure_keeps_live_runtime(tmp_path, monkeypatch):
    monkeypatch.setattr("bootstrap.tools._resolve_plugin_dirs", lambda _: [])
    config = Config(
        provider="",
        model="",
        api_key="",
        model_registrations=[],
        memory_optimizer_enabled=False,
    )
    app = AppRuntime(
        config,
        tmp_path,
        features=RuntimeFeatures(enable_message_channels=False, enable_proactive=False),
    )
    await app.start()
    original = app.core
    prepared = await app.prepare(replace(config, max_tokens=2048))

    def fail():
        raise OSError("disk full")

    try:
        with pytest.raises(OSError, match="disk full"):
            await app.publish(prepared, commit=fail)
        assert app.generation == 1
        assert app.core is original
        await app.discard(prepared)
        assert prepared.closed
        assert not original.event_bus._closed
    finally:
        await app.shutdown()


@pytest.mark.asyncio
async def test_partial_candidate_construction_closes_new_provider_and_preserves_live_core(
    tmp_path, monkeypatch
):
    monkeypatch.setattr("bootstrap.tools._resolve_plugin_dirs", lambda _: [])
    config = Config(
        provider="",
        model="",
        api_key="",
        model_registrations=[],
        memory_optimizer_enabled=False,
    )
    app = AppRuntime(
        config,
        tmp_path,
        features=RuntimeFeatures(enable_message_channels=False, enable_proactive=False),
    )
    await app.start()
    original = app.core
    allocated = []

    class Provider:
        def __init__(self, **kwargs):
            self.aclose = AsyncMock()
            allocated.append(self)

    def fail(**kwargs):
        raise ValueError("context assembly failed")

    monkeypatch.setattr("bootstrap.providers.LLMProvider", Provider)
    monkeypatch.setattr("bootstrap.tools._build_loop_deps", fail)
    changed = replace(
        config,
        provider="openai",
        model="configured",
        api_key="key",
        model_registrations=[
            ModelRegistration(
                id="model",
                provider="openai",
                model="configured",
                api_key="key",
                base_url="",
            ),
        ],
    )
    try:
        with pytest.raises(ValueError, match="context assembly failed"):
            await app.prepare(changed)
        assert len(allocated) == 1
        allocated[0].aclose.assert_awaited_once()
        assert app.core is original
        assert app.generation == 1
        assert not original.event_bus._closed
    finally:
        await app.shutdown()


@pytest.mark.asyncio
async def test_core_motives_follow_generation_publication_and_rollback(
    tmp_path, monkeypatch
):
    from unittest.mock import MagicMock
    from bus.events_lifecycle import SceneObservationCommitted
    from proactive_v2.config import ProactiveStrategiesConfig

    monkeypatch.setattr("bootstrap.tools._resolve_plugin_dirs", lambda _: [])
    config = Config(
        provider="",
        model="",
        api_key="",
        model_registrations=[],
        memory_optimizer_enabled=False,
    )
    app = AppRuntime(
        config,
        tmp_path,
        features=RuntimeFeatures(enable_message_channels=False, enable_proactive=False),
    )
    await app.start()
    lease = app.acquire()
    original = lease.core
    apply = MagicMock()
    monkeypatch.setattr(original.relationship_runtime, "apply_scene_decision", apply)
    event = SceneObservationCommitted(
        session_key="role:mira",
        channel="desktop",
        chat_id="role:mira",
        role_id="mira",
        source="passive",
        transition="started",
        scene_key="rain",
        visual_description="雨夜车站的少女",
    )
    try:
        assert [strategy.name for strategy in original.proactive_motives] == [
            "relationship.scene_followup",
            "relationship.loneliness",
        ]
        prepared = await app.prepare(replace(config, max_tokens=2048))
        await prepared.core.event_bus.fanout(event)
        apply.assert_not_called()
        await original.event_bus.fanout(event)
        assert apply.call_count == 1
        await app.publish(prepared)
        await prepared.core.event_bus.fanout(event)
        assert apply.call_count == 2
        await original.event_bus.fanout(event)
        assert apply.call_count == 3
        await lease.release()
        await original.event_bus.fanout(event)
        assert apply.call_count == 3
        failed = await app.prepare(replace(prepared.config, max_tokens=4096))
        await app.discard(failed)
        await failed.core.event_bus.fanout(event)
        assert apply.call_count == 3
        disabled = await app.prepare(
            replace(
                prepared.config,
                proactive_strategies=ProactiveStrategiesConfig(False, False),
            )
        )
        assert disabled.core.proactive_motives == []
        assert disabled.core.scene_followup_subscription is None
        await app.publish(disabled)
        await disabled.core.event_bus.fanout(event)
        assert apply.call_count == 3
    finally:
        await lease.release()
        await app.shutdown()


@pytest.mark.asyncio
async def test_publish_rechecks_hot_unload_before_handover_or_commit(
    tmp_path, monkeypatch
):
    from pathlib import Path
    from shiori_plugin_testkit.packages import stage_plugin_package
    from agent.plugin_host import PluginRestartRequired

    root = tmp_path / "host_plugins"
    stage_plugin_package(
        Path(__file__).resolve().parents[3] / "fixtures/plugins/restart_required",
        root / "restart_required",
    )
    monkeypatch.setattr("bootstrap.tools._resolve_plugin_dirs", lambda _: [root])
    config = Config(
        provider="",
        model="",
        api_key="",
        model_registrations=[],
        memory_optimizer_enabled=False,
        plugins={"restart_required": {"enabled": False}},
    )
    app = AppRuntime(
        config,
        tmp_path,
        features=RuntimeFeatures(enable_message_channels=False, enable_proactive=False),
    )
    await app.start()
    prepared = await app.prepare(replace(config, max_tokens=2048))
    original = app.core
    committed = []
    try:
        # An active unsafe instance can appear after preparation; publication
        # must recheck the live owner, not rely solely on the initial check.
        original.plugin_manager._services.plugin_configs = {
            "restart_required": {"enabled": True}
        }
        original.plugin_manager._handles.pop(
            str((root / "restart_required").absolute()), None
        )
        assert await original.plugin_manager.load("restart_required")
        with pytest.raises(PluginRestartRequired):
            await app.publish(prepared, commit=lambda: committed.append(True))
        assert committed == []
        assert app.core is original
        assert app.generation == 1
        assert app.accepting_work
        assert not app._generation_manager.current.retired
    finally:
        await app.discard(prepared)
        await app.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
async def test_unpublished_unsafe_candidate_is_forcibly_reclaimed_on_failure(
    tmp_path, monkeypatch, cancel
):
    import asyncio
    from pathlib import Path
    from shiori_plugin_testkit.packages import stage_plugin_package
    import bootstrap.runtime.reload as reload_module

    root = tmp_path / "host_plugins"
    stage_plugin_package(
        Path(__file__).resolve().parents[3] / "fixtures/plugins/restart_required",
        root / "restart_required",
    )
    monkeypatch.setattr("bootstrap.tools._resolve_plugin_dirs", lambda _: [root])
    config = Config(
        provider="",
        model="",
        api_key="",
        model_registrations=[],
        memory_optimizer_enabled=False,
        plugins={"restart_required": {"enabled": False}},
    )
    app = AppRuntime(
        config,
        tmp_path,
        features=RuntimeFeatures(enable_message_channels=False, enable_proactive=False),
    )
    await app.start()
    captured = []

    async def fail_channels(*args, **kwargs):
        # setup completed before channel construction, so the declaration is live.
        if cancel:
            raise asyncio.CancelledError()
        raise RuntimeError("candidate channels failed")

    build = reload_module.prepare_core_runtime

    async def capture_core(*args, **kwargs):
        core = await build(*args, **kwargs)
        captured.append(core)
        return core

    monkeypatch.setattr(reload_module, "prepare_core_runtime", capture_core)
    monkeypatch.setattr(reload_module, "start_channels", fail_channels)
    try:
        with pytest.raises(asyncio.CancelledError if cancel else RuntimeError):
            await app.prepare(
                replace(config, plugins={"restart_required": {"enabled": True}})
            )
        assert len(captured) == 1
        assert captured[0].plugin_manager.states() == []
        assert captured[0].event_bus._closed
        assert not app.core.event_bus._closed
        assert app.generation == 1
    finally:
        await app.shutdown()
