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
        resolved = app.core.plugin_rpc.resolve("proactive.settings_set")
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


async def test_user_skill_mentions_activate_complete_documents_and_follow_plugin_unload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exercise actual message preparation, plugin events and final model frames."""
    import re
    from dataclasses import replace

    from agent.provider import LLMProvider, LLMResponse
    from conversation.service import desktop_thread_id
    from shiori_sdk.prompting import is_context_frame

    selected_documents: list[list[tuple[str, str]]] = []

    async def answer(_self, **kwargs):
        if kwargs.get("response_format"):
            return LLMResponse(content='{"mood":"平静","thought":"我想想。"}')
        frames = [
            message["content"]
            for message in kwargs["messages"]
            if isinstance(message.get("content"), str)
            and is_context_frame(message["content"])
        ]
        # Parse complete skill documents from the latest assembled context
        # frame. Catalog names or a title alone cannot satisfy this assertion.
        selected_documents.append(
            [
                (name, body.strip())
                for name, body in re.findall(
                    r"### Skill: ([a-zA-Z0-9_-]+)\n\n(.*?)"
                    r"(?=\n\n---\n\n### Skill: |\n\n## [a-z_]+\n|"
                    r"\n\n</system-reminder>|$)",
                    frames[-1] if frames else "",
                    re.S,
                )
            ]
        )
        return LLMResponse(content="完成")

    monkeypatch.setattr(LLMProvider, "chat", answer)
    root = tmp_path / "plugins"
    package = stage_plugin_package(plugin_directory("proactive"), root / "proactive")
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
    roles = RoleStore(workspace)
    for role_id in ("initial", "override", "disabled"):
        roles.create_role(
            role_id=role_id,
            name=role_id,
            system_prompt="test",
            runtime_config={
                "dialogue_model_registration_id": config.model_registrations[0].id
            },
        )
    expected = {
        name: (package / "skills" / name / "SKILL.md")
        .read_text(encoding="utf-8")
        .split("\n---", 1)[1]
        .strip()
        for name in ("meme-manage", "create-drift-skill")
    }
    app = AppRuntime(
        config, workspace, features=RuntimeFeatures(enable_message_channels=False)
    )
    await app.start()
    try:
        assert app.core is not None and app.core.plugin_manager is not None

        async def chat(role_id):
            return await app._dispatcher.process_direct(
                "$meme-manage $create-drift-skill $meme-manage $missing-skill",
                channel="desktop",
                chat_id=f"role:{role_id}",
                metadata={
                    "role_id": role_id,
                    "thread_id": desktop_thread_id(role_id),
                    "transport_channel": "desktop",
                    "transport_chat_id": f"role:{role_id}",
                },
            )

        assert await chat("initial") == "完成"
        assert len(selected_documents[-1]) == 2
        assert dict(selected_documents[-1]) == expected

        override = workspace / "skills" / "meme-manage" / "SKILL.md"
        override.parent.mkdir(parents=True)
        override.write_text(
            "---\nname: meme-manage\n---\n# 工作区技能\n\n只执行用户的自定义步骤。",
            encoding="utf-8",
        )
        expected["meme-manage"] = "# 工作区技能\n\n只执行用户的自定义步骤。"
        assert await chat("override") == "完成"
        assert len(selected_documents[-1]) == 2
        assert dict(selected_documents[-1]) == expected

        await app.core.plugin_manager.set_enabled(
            "proactive",
            values={"enabled": False},
            raw_values={"enabled": False},
            drain_timeout=5,
        )
        assert await chat("disabled") == "完成"
        assert selected_documents[-1] == [("meme-manage", expected["meme-manage"])]
    finally:
        await app.shutdown()


async def test_disabling_proactive_and_optimizer_keeps_chat_and_core_presence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Real plugin toggles remove their contributions without breaking a turn."""
    from dataclasses import replace
    import re
    from xml.etree.ElementTree import fromstring
    from agent.provider import LLMProvider, LLMResponse
    from conversation.service import desktop_thread_id
    from shiori_sdk.core.conversation import PromptRendering
    from shiori_sdk.core.memory import MEMORY_ENGINE
    from shiori_sdk.core.memory_optimizer import MEMORY_OPTIMIZER

    advertised_skills: list[dict[str, Path]] = []

    async def answer(_self, **kwargs):
        if kwargs.get("response_format"):
            return LLMResponse(content='{"mood":"平静","thought":"我想想。"}')
        # Inspect the assembled model request, then read the advertised files.
        # This exercises plugin loading, prompt assembly and real packaged paths.
        advertised: dict[str, Path] = {}
        for message in kwargs["messages"]:
            if message["role"] != "system":
                continue
            for xml in re.findall(r"<skills>.*?</skills>", message["content"], re.S):
                for item in fromstring(xml):
                    if item.get("source") == "proactive":
                        name, location = item.findtext("name"), item.findtext(
                            "location"
                        )
                        assert name is not None and location is not None
                        advertised[name] = Path(location)
        advertised_skills.append(advertised)
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
        assert set(advertised_skills[-1]) == {"meme-manage", "create-drift-skill"}
        assert all(
            path.read_text(encoding="utf-8") for path in advertised_skills[-1].values()
        )
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
        assert advertised_skills[-1] == {}
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
