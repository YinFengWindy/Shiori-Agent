"""The production host exposes proactive settings without owning their schema."""

from pathlib import Path

import pytest

from agent.config_models import Config
from bootstrap.app import AppRuntime, RuntimeFeatures
from core.roles import RoleAggregateService, RoleStore
from desktop_bridge.role_presenter import DesktopRolePresenter
from desktop_bridge.role_requests import DesktopRoleRequestHandler
from shiori_sdk.testing.packages import plugin_directory, stage_plugin_package


async def test_settings_rpc_writes_original_role_data_and_releases_projection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "plugins"
    stage_plugin_package(plugin_directory("proactive"), root / "proactive")
    monkeypatch.setattr("bootstrap.tools._resolve_plugin_dirs", lambda _: [root])
    workspace = tmp_path / "workspace"
    roles = RoleStore(workspace)
    roles.create_role(role_id="mira", name="Mira", system_prompt="test")
    roles.write_plugin_proactive(
        "mira", {"enabled": False, "profile": "quiet", "agent": {"max_steps": 12}}
    )
    app = AppRuntime(
        Config(provider="", model="", api_key="", model_registrations=[]),
        workspace,
        features=RuntimeFeatures(enable_message_channels=False),
    )
    await app.start()
    try:
        assert app.core is not None
        runtime_roles = app.core.role_runtime_registry.repository.store
        presenter = DesktopRolePresenter(runtime_roles)
        role = runtime_roles.get_role("mira")
        assert role is not None
        projected = presenter.serialize(role)
        assert "proactive" not in projected
        assert projected["plugin_state"]["proactive"]["proactiveProfile"] == "quiet"
        resolved = app.core.plugin_rpc.resolve("plugin.proactive.settings_set")
        assert resolved is not None
        await resolved[1]({"role_id": "mira", "values": {"proactiveEnabled": True}})
        saved = RoleStore(workspace).get_role("mira")
        assert saved is not None
        assert saved.proactive["enabled"] is True
        assert saved.proactive["profile"] == "quiet"
        assert saved.proactive["agent"] == {"max_steps": 12}

        async def publish(_event):
            pass

        handler = DesktopRoleRequestHandler(
            role_service=RoleAggregateService.from_runtime(
                workspace=workspace,
                role_store=runtime_roles,
                session_manager=app.core.session_manager,
            ),
            role_presenter=presenter,
            publish_event=publish,
        )
        with pytest.raises(ValueError, match="主动设置"):
            await handler.handle(
                "roles.update", {"role_id": "mira", "proactive": {"enabled": False}}
            )
        reloaded = RoleStore(workspace).get_role("mira")
        assert reloaded is not None and reloaded.proactive == saved.proactive
    finally:
        await app.shutdown()
    assert runtime_roles.extensions.project("mira") == {}
    reloaded = RoleStore(workspace).get_role("mira")
    assert reloaded is not None and reloaded.proactive == saved.proactive
