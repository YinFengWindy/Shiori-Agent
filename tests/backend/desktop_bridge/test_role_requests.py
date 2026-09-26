from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from PIL import Image

from bus.event_bus import EventBus
from core.roles import RoleStore
from desktop_bridge.service import DesktopBridgeService
from desktop_bridge.role_requests import DesktopRoleRequestHandler
from session.manager import SessionManager


def _write_image(path: Path, color: tuple[int, int, int]) -> None:
    image = Image.new("RGB", (20, 20), "white")
    for x in range(6, 14):
        for y in range(4, 17):
            image.putpixel((x, y), color)
    image.save(path)


@pytest.mark.asyncio
async def test_old_role_update_cannot_recreate_channel_bindings() -> None:
    handler = DesktopRoleRequestHandler(
        role_service=SimpleNamespace(),
        role_presenter=SimpleNamespace(),
        voice_handler=SimpleNamespace(),
        publish_event=AsyncMock(),
    )
    with pytest.raises(ValueError, match="账号归属"):
        await handler.handle(
            "roles.update",
            {
                "role_id": "mira",
                "channel_bindings": [
                    {"channel": "qq", "chat_id": "gqq:42", "chat_type": "group"}
                ],
            },
        )


@pytest.mark.asyncio
async def test_role_card_preview_forwards_the_full_payload_to_its_service() -> None:
    card_import = SimpleNamespace(
        preview=AsyncMock(return_value={"import_id": "preview-1"})
    )
    handler = DesktopRoleRequestHandler(
        role_service=SimpleNamespace(),
        role_presenter=SimpleNamespace(),
        voice_handler=SimpleNamespace(),
        card_import_service=card_import,
        publish_event=AsyncMock(),
    )

    result = await handler.handle(
        "roles.cardImport.preview",
        {"source": "C:/workspace/private_runtime/imports/role-cards/card.json"},
    )

    card_import.preview.assert_awaited_once_with(
        {"source": "C:/workspace/private_runtime/imports/role-cards/card.json"}
    )
    assert result == {"import_id": "preview-1"}


@pytest.mark.asyncio
async def test_role_create_persists_structured_profile(tmp_path: Path) -> None:
    role_store = RoleStore(tmp_path)
    service = DesktopBridgeService(
        workspace=tmp_path,
        role_store=role_store,
        session_manager=SessionManager(tmp_path),
        agent_loop=SimpleNamespace(process_direct=AsyncMock()),
        event_bus=EventBus(),
    )
    profile = {
        "character": {
            "profile": "A meticulous archivist.",
            "personality": "Calm and precise.",
            "behavior_rules": "Use concise answers and cite the archive.",
            "response_constraints": "Use short paragraphs.",
            "nickname": "",
        },
        "knowledge_base": {"enabled": True, "entries": [], "raw_source": {}},
    }

    response = await service.handle(
        {
            "id": "create-structured-role",
            "method": "roles.create",
            "payload": {
                "name": "Mira",
                "description": "A role",
                "system_prompt": profile["character"]["behavior_rules"],
                "profile": profile,
            },
        },
        emit_event=lambda _payload: None,
    )

    assert response.error is None
    assert response.payload["role"]["profile"] == {
        "version": 1,
        "character": profile["character"],
    }
    persisted = role_store.get_role(response.payload["role"]["id"])
    assert persisted is not None
    assert persisted.profile.to_dict() == {
        "version": 1,
        "character": profile["character"],
    }

    update = await service.handle(
        {
            "id": "update-role-knowledge",
            "method": "roles.update",
            "payload": {
                "role_id": response.payload["role"]["id"],
                "profile": {
                    "knowledge_base": {
                        "enabled": False,
                        "entries": [],
                    }
                },
            },
        },
        emit_event=lambda _payload: None,
    )

    assert update.error is None
    assert update.payload["role"]["profile"]["character"] == profile["character"]
    assert "knowledge_base" not in update.payload["role"]["profile"]

    cleared_rules = await service.handle(
        {
            "id": "clear-role-behavior-rules",
            "method": "roles.update",
            "payload": {
                "role_id": response.payload["role"]["id"],
                "system_prompt": "",
                "profile": {"character": {"behavior_rules": ""}},
            },
        },
        emit_event=lambda _payload: None,
    )
    assert cleared_rules.error is None
    character = cleared_rules.payload["role"]["profile"]["character"]
    assert character["behavior_rules"] == ""
    assert character["response_constraints"] == "Use short paragraphs."
    assert character["profile"] == "A meticulous archivist."
    await service.aclose()


@pytest.mark.asyncio
async def test_the_core_bridge_no_longer_answers_pet_package_methods() -> None:
    """#181-D: pet package management belongs to the plugin that owns it.

    `handle` returning `None` is how this router says "not mine", which lets
    the plugin RPC dispatcher downstream pick the method up as
    `plugin.desktop_pet.pets.*`. If these branches came back, the core bridge
    would answer first and the plugin's copy would silently never run.
    """
    handler = DesktopRoleRequestHandler(
        role_service=SimpleNamespace(),
        role_presenter=SimpleNamespace(),
        voice_handler=SimpleNamespace(),
        card_import_service=SimpleNamespace(),
        publish_event=AsyncMock(),
    )

    for method in ("roles.pets.import", "roles.pets.remove", "roles.pets.select"):
        assert (
            await handler.handle(method, {"role_id": "mira", "package_id": "pet-1"})
            is None
        )


@pytest.mark.asyncio
async def test_role_update_commits_generic_plugin_draft_and_projects_its_owner(
    tmp_path,
):
    store = RoleStore(tmp_path)
    store.create_role(role_id="mira", name="Before", system_prompt="test")

    def write(role_id, draft, data):
        data[role_id] = draft

    store.extensions.register(
        "sample", write, lambda role_id, data: data.get(role_id, {})
    )
    service = DesktopBridgeService(
        workspace=tmp_path,
        role_store=store,
        session_manager=SessionManager(tmp_path),
        agent_loop=SimpleNamespace(process_direct=AsyncMock()),
        event_bus=EventBus(),
    )
    response = await service.handle(
        {
            "id": "save",
            "method": "roles.update",
            "payload": {
                "role_id": "mira",
                "name": "After",
                "plugin_drafts": {"sample": {"enabled": True}},
            },
        },
        emit_event=lambda _payload: None,
    )
    assert response.error is None
    assert response.payload["role"]["plugin_state"] == {"sample": {"enabled": True}}
    assert store.get_role("mira").name == "After"
    assert "plugin_state" not in store.get_role("mira").to_dict()
