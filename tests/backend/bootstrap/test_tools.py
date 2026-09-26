from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from bootstrap.tools import (
    _bind_memory_lifecycle_if_supported,
    _resolve_plugin_dirs,
    _role_owns_channel_target,
    _validate_role_target,
)
from core.roles import RoleRepository, RoleStore
from core.memory.markdown import MarkdownMemoryMaintenance, MarkdownMemoryStore
from session.manager import SessionManager

_REPO_ROOT = Path(__file__).resolve().parents[3]


def test_memory_lifecycle_binds_the_session_owner_commit_operation(tmp_path: Path):
    manager = SessionManager(tmp_path)
    maintenance = MarkdownMemoryMaintenance(
        store=MarkdownMemoryStore(tmp_path),
        provider=cast(Any, SimpleNamespace()),
        model="test",
        keep_count=0,
    )

    _bind_memory_lifecycle_if_supported(
        markdown=maintenance,
        session_manager=manager,
        relationship_runtime=cast(
            Any, SimpleNamespace(refresh_snapshot_after_consolidation=AsyncMock())
        ),
        relationship_optimizer=cast(Any, object()),
    )

    assert maintenance._get_session == manager.get_or_create
    assert maintenance._commit_consolidation == manager.commit_consolidation


def test_resolve_plugin_dirs_uses_repository_root_in_dev(tmp_path: Path) -> None:
    dirs = _resolve_plugin_dirs(tmp_path)

    assert dirs == [_REPO_ROOT / "plugins", tmp_path / "plugins"]
    assert dirs[0].is_dir()


def test_resolve_plugin_dirs_uses_meipass_when_frozen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sys

    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)

    dirs = _resolve_plugin_dirs(tmp_path)

    assert dirs == [tmp_path / "plugins", tmp_path / "plugins"]


def test_role_target_validation_rejects_bare_id_for_bound_qq_group(
    tmp_path: Path,
) -> None:
    store = RoleStore(tmp_path)
    role = store.create_role(
        role_id="mira",
        name="Mira",
        description="",
        system_prompt="You are Mira.",
    )

    repository = RoleRepository(store)
    # Neither a private ID nor an old bound group authorizes external push.
    assert not _role_owns_channel_target(
        repository, role_id=role.id, channel="qq", chat_id="42"
    )
    assert not _role_owns_channel_target(
        repository, role_id=role.id, channel="qq", chat_id="gqq:42"
    )
    # message_push directs both external targets to account-owned delivery.
    private_result = _validate_role_target(
        repository, role_id=role.id, channel="qq", chat_id="42"
    )
    group_result = _validate_role_target(
        repository, role_id=role.id, channel="qq", chat_id="gqq:42"
    )
    assert isinstance(private_result, str) and "account_send" in private_result
    assert isinstance(group_result, str) and "account_send" in group_result
    assert (
        _validate_role_target(
            repository, role_id=role.id, channel="desktop", chat_id="role:mira"
        )
        is True
    )


def test_role_target_validation_explains_wrong_channel_for_bound_chat(
    tmp_path: Path,
) -> None:
    store = RoleStore(tmp_path)
    role = store.create_role(
        role_id="mira",
        name="Mira",
        description="",
        system_prompt="You are Mira.",
    )

    result = _validate_role_target(
        RoleRepository(store),
        role_id=role.id,
        channel="qq",
        chat_id="c2c:user-1",
    )

    assert isinstance(result, str)
    assert "account_send" in result


def test_actual_runtime_observes_and_follows_scene_without_novelai_package(tmp_path):
    """A fresh interpreter blocks every NovelAI import while assembling a real runtime."""
    import subprocess
    import sys
    import textwrap

    script = textwrap.dedent("""
        import asyncio, importlib.abc, sys
        from pathlib import Path
        from datetime import datetime, timedelta, timezone
        from unittest.mock import AsyncMock
        root, workspace = Path(sys.argv[1]), Path(sys.argv[2])
        sys.path[:0] = [str(root / "apps/backend"), str(root)]
        class NoNovelAI(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                if fullname.startswith("plugins.novelai"):
                    raise ModuleNotFoundError("NovelAI package is absent")
        sys.meta_path.insert(0, NoNovelAI())
        from agent.config_models import Config
        from bootstrap.app import AppRuntime, RuntimeFeatures
        import bootstrap.tools as tools
        from core.roles.store import RoleStore
        from core.scene.contracts import SceneDecision
        from bus.events_lifecycle import ProactiveMessageCommitted
        from core.common.runtime_scope import bind_runtime
        plugin_root = workspace / "available-plugins"
        plugin_root.mkdir(parents=True)
        tools._resolve_plugin_dirs = lambda _: [plugin_root]
        async def run():
            roles = RoleStore(workspace)
            roles.create_role(role_id="mira", name="Mira", system_prompt="role")
            roles.update_role("mira", proactive={"enabled": True, "candidates": [{"channel": "telegram", "chat_id": "chat"}]})
            config = Config(provider="", model="", api_key="", model_registrations=[], memory_optimizer_enabled=False)
            app = AppRuntime(config, workspace, features=RuntimeFeatures(enable_message_channels=False, enable_proactive=False))
            await app.start()
            try:
                from core.roles.scene_followup_runtime import SceneFollowupRuntime
                SceneFollowupRuntime(workspace).handle_user_message("role:mira")
                controller = app.core.scene_service.controller
                controller._light_model = "fake-light"
                controller._decision_provider = AsyncMock(return_value=SceneDecision("started", "rain", "umbrella", "少女撑伞"))
                lease = app.acquire()
                with bind_runtime(lease):
                    await app.core.event_bus.fanout(ProactiveMessageCommitted("role:mira", "desktop", "mira", assistant_response="她撑开雨伞"))
                await asyncio.gather(*controller.tasks.values())
                await lease.release()
                controller._decision_provider.assert_awaited_once()
                assert controller.state.current("role:mira")["scene_key"] == "rain"
                allowed, details = app.relationship_runtime.should_trigger_scene_followup("role:mira", datetime.now(timezone.utc) + timedelta(minutes=30))
                assert allowed, details
                assert not any(name.startswith("plugins.novelai") for name in sys.modules)
            finally:
                await app.shutdown()
        asyncio.run(run())
    """)
    result = subprocess.run(
        [sys.executable, "-X", "utf8", "-c", script, str(_REPO_ROOT), str(tmp_path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.asyncio
async def test_published_generation_keeps_before_turn_capture_until_old_after_turn(
    tmp_path, monkeypatch
):
    import asyncio
    from dataclasses import replace
    from datetime import datetime
    from unittest.mock import AsyncMock
    from agent.config_models import Config
    from agent.lifecycle.types import BeforeTurnCtx, AfterTurnCtx
    from bootstrap.app import AppRuntime, RuntimeFeatures
    from bus.events_lifecycle import SceneObservationCommitted
    from core.common.runtime_scope import bind_runtime
    from core.scene.contracts import SceneDecision

    monkeypatch.setattr("bootstrap.tools._resolve_plugin_dirs", lambda _: [])
    roles = RoleStore(tmp_path)
    roles.create_role(role_id="mira", name="Mira", system_prompt="role")
    roles.update_role(
        "mira",
        proactive={
            "enabled": True,
            "candidates": [{"channel": "telegram", "chat_id": "chat"}],
        },
    )
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
    try:
        old = app.core
        old.session_manager.open_role_session("mira", role_name="Mira")
        controller = old.scene_service.controller
        controller._light_model = "mock"
        controller._decision_provider = AsyncMock(
            return_value=SceneDecision("started", "rain", "umbrella", "少女撑伞")
        )
        observations = []
        app.event_bus.on(SceneObservationCommitted, observations.append)
        with bind_runtime(lease):
            await old.event_bus.emit(
                BeforeTurnCtx(
                    session_key="role:mira",
                    channel="desktop",
                    chat_id="role:mira",
                    content="下雨了",
                    timestamp=datetime.now(),
                    retrieved_memory_block="",
                    retrieval_trace_raw=None,
                    history_messages=(),
                )
            )
        candidate = await app.prepare(replace(config, dev_mode=True))
        assert not controller.state.path.exists()
        assert candidate.core.scene_service.controller.state is controller.state
        await app.publish(candidate)
        with bind_runtime(lease):
            await old.event_bus.fanout(
                AfterTurnCtx(
                    session_key="role:mira",
                    channel="desktop",
                    chat_id="role:mira",
                    reply="她撑开雨伞",
                    tools_used=(),
                    thinking=None,
                    will_dispatch=False,
                )
            )
        await asyncio.gather(*controller.tasks.values())
        assert len(observations) == 1
        assert observations[0].assistant_reply == "她撑开雨伞"
        assert (
            candidate.core.scene_service.controller.state.current("role:mira")[
                "scene_key"
            ]
            == "rain"
        )
        # A prepared candidate that is discarded never subscribes or writes.
        rejected = await app.prepare(replace(app.config, max_tokens=1234))
        rejected_scene = rejected.core.scene_service
        await app.discard(rejected)
        assert not rejected_scene.controller.tasks
    finally:
        await lease.release()
        await app.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "core_enabled,role_enabled,followup_enabled,consumer_needed,expected",
    [
        (True, True, False, False, 0),
        (True, True, True, False, 1),
        (True, False, True, False, 0),
        (True, True, False, True, 1),
        (False, True, True, True, 0),
    ],
)
async def test_core_scene_demand_respects_followup_strategy_and_independent_consumers(
    tmp_path,
    monkeypatch,
    core_enabled,
    role_enabled,
    followup_enabled,
    consumer_needed,
    expected,
):
    import asyncio
    from unittest.mock import AsyncMock
    from agent.config_models import Config
    from bootstrap.app import AppRuntime, RuntimeFeatures
    from bus.events_lifecycle import ProactiveMessageCommitted
    from core.scene.contracts import SceneDecision
    from proactive_v2.config import ProactiveStrategiesConfig

    monkeypatch.setattr("bootstrap.tools._resolve_plugin_dirs", lambda _: [])
    monkeypatch.setattr(
        "core.scene.demand.SceneObservationDemand.needed",
        lambda self, role: consumer_needed,
    )
    roles = RoleStore(tmp_path)
    roles.create_role(role_id="mira", name="Mira", system_prompt="role")
    roles.update_role(
        "mira",
        proactive={
            "enabled": role_enabled,
            "candidates": [{"channel": "telegram", "chat_id": "chat"}],
        },
    )
    config = Config(
        provider="",
        model="",
        api_key="",
        model_registrations=[],
        memory_optimizer_enabled=False,
        scene_observation_enabled=core_enabled,
        proactive_strategies=ProactiveStrategiesConfig(scene_followup=followup_enabled),
    )
    app = AppRuntime(
        config,
        tmp_path,
        features=RuntimeFeatures(enable_message_channels=False, enable_proactive=False),
    )
    await app.start()
    try:
        controller = app.core.scene_service.controller
        controller._light_model = "mock"
        model = AsyncMock(
            return_value=SceneDecision("started", "rain", "umbrella", "少女撑伞")
        )
        controller._decision_provider = model
        await app.core.event_bus.fanout(
            ProactiveMessageCommitted(
                "role:mira", "desktop", "mira", assistant_response="雨中"
            )
        )
        await asyncio.gather(*controller.tasks.values())
        assert model.await_count == expected
    finally:
        await app.shutdown()


@pytest.mark.asyncio
async def test_core_stop_preflights_before_teardown_and_force_continues_after_failure(
    tmp_path, monkeypatch
):
    from shiori_plugin_testkit.packages import stage_plugin_package
    from agent.config_models import Config
    from agent.plugin_host import PluginRestartRequired
    from bootstrap.app import AppRuntime, RuntimeFeatures

    root = tmp_path / "host_plugins"
    stage_plugin_package(
        _REPO_ROOT / "tests/fixtures/plugins/restart_required",
        root / "restart_required",
    )
    monkeypatch.setattr("bootstrap.tools._resolve_plugin_dirs", lambda _: [root])
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
    core = app.core
    state = core.plugin_manager._dependency_api("restart_required")
    scene_close = AsyncMock(wraps=core.scene_service.close)
    monkeypatch.setattr(core.scene_service, "close", scene_close)
    try:
        with pytest.raises(PluginRestartRequired):
            await core.stop()
        scene_close.assert_not_awaited()
        assert not core.event_bus._closed
        assert state == ["started"]
        scene_close.side_effect = OSError("scene close failed")
        with pytest.raises(OSError, match="scene close failed"):
            await core.stop(force=True)
        assert state == ["started", "closed"]
        assert core.event_bus._closed
    finally:
        scene_close.side_effect = None
        await app.shutdown()
