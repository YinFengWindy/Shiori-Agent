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


async def test_disabling_proactive_and_optimizer_keeps_chat_and_core_presence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Real plugin toggles remove their contributions without breaking a turn."""
    from dataclasses import replace
    from agent.provider import LLMProvider, LLMResponse
    from conversation.service import desktop_thread_id
    from shiori_sdk.core.conversation import PromptRendering
    from shiori_sdk.core.memory import MEMORY_ENGINE
    from shiori_sdk.core.memory_optimizer import MEMORY_OPTIMIZER

    async def answer(_self, **kwargs):
        if kwargs.get("response_format"):
            return LLMResponse(content='{"mood":"平静","thought":"我想想。"}')
        return LLMResponse(content="你好 §cited:[memory-1]§")

    monkeypatch.setattr(LLMProvider, "chat", answer)
    root = tmp_path / "plugins"
    for plugin_id in ("proactive", "memory_optimizer"):
        stage_plugin_package(plugin_directory(plugin_id), root / plugin_id)
    monkeypatch.setattr("bootstrap.tools._resolve_plugin_dirs", lambda _: [root])
    config = Config(
        provider="openai",
        model="test",
        api_key="test",
        base_url="http://127.0.0.1:1/v1",
    )
    config.model_registrations = [
        replace(config.model_registrations[0], model_context_window=128000)
    ]
    workspace = tmp_path / "workspace"
    RoleStore(workspace).create_role(
        role_id="mira",
        name="Mira",
        system_prompt="test",
        runtime_config={
            "dialogue_model_registration_id": config.model_registrations[0].id
        },
    )
    app = AppRuntime(
        config, workspace, features=RuntimeFeatures(enable_message_channels=False)
    )
    await app.start()
    try:
        assert app.core is not None and app.core.plugin_manager is not None
        manager = app.core.plugin_manager
        assert set(manager.active_plugin_ids) == {"proactive", "memory_optimizer"}
        assert manager.kernel.get(MEMORY_OPTIMIZER) is not None
        sections: list[tuple[str, ...]] = []
        app.event_bus.on(
            PromptRendering,
            lambda event: sections.append(
                tuple(section.name for section in event.system_sections_bottom)
            ),
        )

        async def chat():
            return await app._dispatcher.process_direct(
                "你好",
                channel="desktop",
                chat_id="role:mira",
                metadata={
                    "role_id": "mira",
                    "thread_id": desktop_thread_id("mira"),
                    "transport_channel": "desktop",
                    "transport_chat_id": "role:mira",
                },
            )

        assert await chat() == "你好"
        assert "proactive" in sections[-1]
        first_user_at = app.core.session_manager.presence.last_user_at("role:mira")
        for plugin_id in ("proactive", "memory_optimizer"):
            await manager.set_enabled(
                plugin_id,
                values={"enabled": False},
                raw_values={"enabled": False},
                drain_timeout=5,
            )
        assert not manager.active_plugin_ids
        assert manager.kernel.get(MEMORY_ENGINE) is None
        assert manager.kernel.get(MEMORY_OPTIMIZER) is None
        sections.clear()
        assert await chat() == "你好"
        assert sections and all("proactive" not in names for names in sections)
        persisted = app.core.session_manager.get_or_create("role:mira")
        assert [
            message["content"]
            for message in persisted.messages
            if message["role"] == "assistant"
        ] == ["你好", "你好"]
        last_user_at = app.core.session_manager.presence.last_user_at("role:mira")
        assert first_user_at is not None and last_user_at is not None
        assert last_user_at > first_user_at
    finally:
        await app.shutdown()
