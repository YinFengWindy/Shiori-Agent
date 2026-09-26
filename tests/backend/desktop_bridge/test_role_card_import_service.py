from __future__ import annotations

import base64
import io
import json
import zipfile
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, Mock, create_autospec

import pytest
from PIL import Image, PngImagePlugin

from bus.event_bus import EventBus
from agent.looping.core import AgentLoop
from core.roles import RoleAggregateService, RoleStore
from desktop_bridge.role_card_import_service import DesktopRoleCardImportService
from desktop_bridge import role_card_import_service as import_service_module
from desktop_bridge.service import DesktopBridgeService
from session.manager import SessionManager


def _card(*, name: str = "小诗") -> dict[str, object]:
    return {
        "spec": "chara_card_v2",
        "data": {
            "name": name,
            "description": "角色资料",
            "personality": "安静、细心",
            "system_prompt": "遵守边界",
            "first_mes": "你好。",
        },
    }


def _service(tmp_path, *, on_role_deleted=None):
    store = RoleStore(tmp_path)
    aggregate_service = RoleAggregateService.from_runtime(
        workspace=tmp_path,
        role_store=store,
        session_manager=SessionManager(tmp_path),
        on_role_deleted=on_role_deleted,
    )
    return (
        DesktopRoleCardImportService(
            workspace=tmp_path,
            role_service=aggregate_service,
            role_store=store,
        ),
        store,
    )


def _stage_card(tmp_path, payload: dict[str, object]):
    source = tmp_path / "private_runtime" / "imports" / "role-cards" / "card.json"
    source.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return source


def _png_role_card(payload: dict[str, object]) -> bytes:
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text(
        "chara",
        base64.b64encode(
            json.dumps(payload, ensure_ascii=False).encode("utf-8")
        ).decode(),
    )
    image = Image.new("RGBA", (8, 8), (255, 0, 0, 255))
    output = io.BytesIO()
    image.save(output, format="PNG", pnginfo=metadata)
    return output.getvalue()


@pytest.mark.asyncio
async def test_preview_stages_card_without_creating_a_role(tmp_path) -> None:
    service, store = _service(tmp_path)
    source = _stage_card(tmp_path, _card())

    preview = await service.preview({"source": str(source)})

    assert preview["name"] == "小诗"
    assert preview["import_id"]
    assert preview["system_prompt"] == "遵守边界"
    assert store.list_roles() == []


@pytest.mark.asyncio
async def test_commit_discards_character_book_and_keeps_character_fields(tmp_path):
    service, store = _service(tmp_path)
    card = _card()
    card["data"]["character_book"] = {"entries": [{"content": "旧知识"}]}
    source = _stage_card(tmp_path, card)
    preview = await service.preview({"source": str(source)})

    assert "character_book" in preview["report"]["discarded_fields"]
    result = await service.commit(
        {
            "import_id": preview["import_id"],
            "overrides": {
                "profile": {
                    "character": {"response_constraints": "简洁"},
                    "knowledge_base": {
                        "enabled": True,
                        "entries": [{"content": "注入"}],
                    },
                }
            },
        }
    )

    profile = result["role"]["profile"]
    assert profile["character"]["profile"] == "角色资料"
    assert profile["character"]["response_constraints"] == "简洁"
    assert "knowledge_base" not in profile
    assert "旧知识" not in str(store.get_role(result["role"]["id"]).to_dict())


@pytest.mark.asyncio
async def test_staging_failure_retains_preview_and_can_retry(tmp_path, monkeypatch):
    service, store = _service(tmp_path)
    preview = await service.preview({"source": str(_stage_card(tmp_path, _card()))})
    original_stage = import_service_module.stage_assets

    def fail_stage(*_args):
        raise PermissionError("staging unavailable")

    monkeypatch.setattr(import_service_module, "stage_assets", fail_stage)
    with pytest.raises(PermissionError, match="staging unavailable"):
        await service.commit({"import_id": preview["import_id"]})
    assert store.list_roles() == []
    monkeypatch.setattr(import_service_module, "stage_assets", original_stage)
    result = await service.commit({"import_id": preview["import_id"]})
    assert store.list_roles()[0].id == result["role"]["id"]


@pytest.mark.asyncio
async def test_metadata_failure_rolls_back_role_session_and_memory_then_retries(
    tmp_path, monkeypatch
):
    deleted_roles = []
    service, store = _service(tmp_path, on_role_deleted=deleted_roles.append)
    source = tmp_path / "private_runtime/imports/role-cards/card.png"
    source.write_bytes(_png_role_card(_card()))
    preview = await service.preview({"source": str(source)})
    original_apply = import_service_module.apply_asset_metadata
    monkeypatch.setattr(
        import_service_module,
        "apply_asset_metadata",
        AsyncMock(side_effect=PermissionError("metadata unavailable")),
    )
    with pytest.raises(PermissionError, match="metadata unavailable"):
        await service.commit({"import_id": preview["import_id"]})
    assert len(deleted_roles) == 1
    assert store.list_roles() == []
    assert SessionManager(tmp_path).list_sessions() == []
    assert not (tmp_path / "roles" / deleted_roles[0]).exists()
    assert list(store.assets_dir.iterdir()) == []
    assert all(Path(asset["preview_abs"]).is_file() for asset in preview["assets"])
    monkeypatch.setattr(import_service_module, "apply_asset_metadata", original_apply)
    result = await service.commit({"import_id": preview["import_id"]})
    assert len(store.list_roles()) == 1
    assert store.list_roles()[0].id == result["role"]["id"]
    assert len(SessionManager(tmp_path).list_sessions()) == 1


@pytest.mark.asyncio
async def test_memory_initialization_failure_rolls_back_already_persisted_role(
    tmp_path, monkeypatch
):
    deleted_roles = []
    service, store = _service(tmp_path, on_role_deleted=deleted_roles.append)
    preview = await service.preview({"source": str(_stage_card(tmp_path, _card()))})
    memory = service._role_service.memory
    original_seed = memory.prepare_memory
    monkeypatch.setattr(
        memory,
        "prepare_memory",
        Mock(side_effect=RuntimeError("seed unavailable")),
    )
    with pytest.raises(RuntimeError, match="seed unavailable"):
        await service.commit({"import_id": preview["import_id"]})
    assert len(deleted_roles) == 1
    assert store.list_roles() == []
    monkeypatch.setattr(memory, "prepare_memory", original_seed)
    assert (await service.commit({"import_id": preview["import_id"]}))["role"]["id"]


@pytest.mark.asyncio
async def test_retry_finishes_failed_rollback_before_creating_another_role(
    tmp_path, monkeypatch
):
    deleted_roles = []
    service, store = _service(tmp_path, on_role_deleted=deleted_roles.append)
    source = tmp_path / "private_runtime/imports/role-cards/card.png"
    source.write_bytes(_png_role_card(_card()))
    preview = await service.preview({"source": str(source)})
    original_apply = import_service_module.apply_asset_metadata
    original_delete = service._role_service.delete_role

    def fail_delete(*_args):
        raise PermissionError("rollback unavailable")

    monkeypatch.setattr(
        import_service_module,
        "apply_asset_metadata",
        AsyncMock(side_effect=RuntimeError("metadata unavailable")),
    )
    monkeypatch.setattr(service._role_service, "delete_role", fail_delete)
    with pytest.raises(PermissionError, match="rollback unavailable"):
        await service.commit({"import_id": preview["import_id"]})
    incomplete_id = store.list_roles()[0].id
    with pytest.raises(PermissionError, match="rollback unavailable"):
        await service.commit({"import_id": preview["import_id"]})
    assert [role.id for role in store.list_roles()] == [incomplete_id]
    monkeypatch.setattr(service._role_service, "delete_role", original_delete)
    monkeypatch.setattr(import_service_module, "apply_asset_metadata", original_apply)
    result = await service.commit({"import_id": preview["import_id"]})
    assert deleted_roles == [incomplete_id]
    assert [role.id for role in store.list_roles()] == [result["role"]["id"]]


@pytest.mark.asyncio
async def test_commit_cancellation_rolls_back_and_rejects_concurrent_commit_or_cancel(
    tmp_path, monkeypatch
):
    deleted_roles = []
    service, store = _service(tmp_path, on_role_deleted=deleted_roles.append)
    source = tmp_path / "private_runtime/imports/role-cards/card.png"
    source.write_bytes(_png_role_card(_card()))
    preview = await service.preview({"source": str(source)})
    started = asyncio.Event()
    original_apply = import_service_module.apply_asset_metadata

    async def waiting_metadata(*_args):
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(import_service_module, "apply_asset_metadata", waiting_metadata)
    task = asyncio.create_task(service.commit({"import_id": preview["import_id"]}))
    await started.wait()
    with pytest.raises(ValueError, match="正在提交"):
        await service.commit({"import_id": preview["import_id"]})
    with pytest.raises(ValueError, match="正在提交"):
        await service.cancel({"import_id": preview["import_id"]})
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert len(deleted_roles) == 1
    assert store.list_roles() == []
    assert SessionManager(tmp_path).list_sessions() == []
    monkeypatch.setattr(import_service_module, "apply_asset_metadata", original_apply)
    assert (await service.commit({"import_id": preview["import_id"]}))["role"]["id"]


@pytest.mark.asyncio
async def test_commit_creates_role_only_after_preview_confirmation(tmp_path) -> None:
    service, store = _service(tmp_path)
    source = _stage_card(tmp_path, _card())
    preview = await service.preview({"source": str(source)})

    result = await service.commit(
        {
            "import_id": preview["import_id"],
            "overrides": {"name": "已导入的小诗"},
        }
    )

    assert result["role"]["name"] == "已导入的小诗"
    imported = store.list_roles()
    assert len(imported) == 1
    assert imported[0].profile.character.personality == "安静、细心"
    assert "greetings" not in imported[0].profile.to_dict()
    with pytest.raises(ValueError, match="导入预览已失效"):
        await service.commit({"import_id": preview["import_id"]})


@pytest.mark.asyncio
async def test_cancel_invalidates_preview_without_creating_a_role(tmp_path) -> None:
    service, store = _service(tmp_path)
    source = _stage_card(tmp_path, _card())
    preview = await service.preview({"source": str(source)})

    assert await service.cancel({"import_id": preview["import_id"]}) == {
        "cancelled": True
    }
    with pytest.raises(ValueError, match="导入预览已失效"):
        await service.commit({"import_id": preview["import_id"]})
    assert store.list_roles() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("remove", [False, True])
async def test_commit_can_replace_or_remove_imported_avatar(tmp_path, remove):
    service, store = _service(tmp_path)
    source = tmp_path / "private_runtime/imports/role-cards/card.png"
    source.write_bytes(_png_role_card(_card()))
    replacement = tmp_path / "replacement.png"
    Image.new("RGB", (12, 12), (0, 255, 0)).save(replacement)
    preview = await service.preview({"source": str(source)})

    result = await service.commit(
        {
            "import_id": preview["import_id"],
            "overrides": {"avatar_source": "" if remove else str(replacement)},
        }
    )

    role = store.get_role(result["role"]["id"])
    assert role is not None
    if remove:
        assert role.avatar is None
    else:
        assert role.avatar
        with Image.open(store.assets_dir.parent / role.avatar) as avatar:
            assert avatar.getpixel((0, 0)) == (0, 255, 0)


@pytest.mark.asyncio
async def test_avatar_failure_rolls_back_import_and_retains_retry(tmp_path):
    service, store = _service(tmp_path)
    preview = await service.preview({"source": str(_stage_card(tmp_path, _card()))})
    with pytest.raises(FileNotFoundError):
        await service.commit(
            {
                "import_id": preview["import_id"],
                "overrides": {"avatar_source": str(tmp_path / "missing.png")},
            }
        )
    assert store.list_roles() == []
    assert (await service.commit({"import_id": preview["import_id"]}))["role"]["id"]


@pytest.mark.asyncio
async def test_commit_defaults_description_to_imported_card_description(
    tmp_path,
) -> None:
    service, store = _service(tmp_path)
    card = _card()
    data = card["data"]
    assert isinstance(data, dict)
    data["description"] = "完整角色设定"
    data["system_prompt"] = ""
    source = _stage_card(tmp_path, card)
    preview = await service.preview({"source": str(source)})

    await service.commit(
        {
            "import_id": preview["import_id"],
            "overrides": {"profile": {"character": {"personality": "自定义性格"}}},
        }
    )

    imported = store.list_roles()[0]
    assert imported.description == "完整角色设定"
    assert imported.profile.character.profile == "完整角色设定"
    assert imported.profile.character.personality == "自定义性格"
    assert imported.system_prompt == "请遵循角色资料进行自然对话。"
    assert imported.profile.import_provenance is not None
    assert imported.profile.import_provenance.format == "tavern-json"


@pytest.mark.asyncio
async def test_commit_preserves_explicitly_cleared_description(tmp_path):
    service, store = _service(tmp_path)
    preview = await service.preview({"source": str(_stage_card(tmp_path, _card()))})
    await service.commit(
        {"import_id": preview["import_id"], "overrides": {"description": ""}}
    )
    assert store.list_roles()[0].description == ""


@pytest.mark.asyncio
async def test_charx_commit_requires_duplicate_emotion_choice_and_binds_selected_image(
    tmp_path,
):
    service, store = _service(tmp_path)
    source = tmp_path / "private_runtime/imports/role-cards/card.charx"
    declarations = [
        {"type": "icon", "name": "main", "uri": "embeded://a.png", "ext": "png"},
        {"type": "background", "name": "main", "uri": "embeded://b.png", "ext": "png"},
        {"type": "emotion", "name": "neutral", "uri": "embeded://c.png", "ext": "png"},
        {"type": "emotion", "name": "neutral", "uri": "embeded://d.png", "ext": "png"},
    ]
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr(
            "card.json",
            json.dumps(
                {
                    "spec": "chara_card_v3",
                    "data": {"name": "Test", "assets": declarations},
                }
            ),
        )
        for filename in ("a.png", "b.png", "c.png", "d.png"):
            archive.writestr(filename, _png_role_card(_card()))
    preview = await service.preview({"source": str(source)})
    with pytest.raises(ValueError, match="请选择心情"):
        await service.commit({"import_id": preview["import_id"]})
    with pytest.raises(ValueError, match="选择无效"):
        await service.commit(
            {
                "import_id": preview["import_id"],
                "emotion_selections": {"neutral": "asset-0"},
            }
        )
    assert store.list_roles() == []
    await service.commit(
        {
            "import_id": preview["import_id"],
            "emotion_selections": {"neutral": "asset-2"},
        }
    )
    role = store.list_roles()[0]
    assert role.avatar
    assert len(role.illustrations) == 4
    assert role.chat_background == role.illustrations[1]
    assert role.runtime_config["mood_illustration_bindings"] == {
        "neutral": role.illustrations[2]
    }
    assert role.runtime_config["default_mood"] == "neutral"
    assert not list(source.parent.glob("shiori-role-card-*"))


@pytest.mark.asyncio
async def test_preview_thumbnail_write_error_propagates_and_cleans_partial_preview(
    tmp_path, monkeypatch
):
    service, store = _service(tmp_path)
    source = tmp_path / "private_runtime/imports/role-cards/card.png"
    source.write_bytes(_png_role_card(_card()))
    original_save = Image.Image.save

    def failed_save(image, target, **kwargs):
        Path(target).write_bytes(b"partial")
        raise PermissionError("cannot write thumbnail")

    monkeypatch.setattr(Image.Image, "save", failed_save)
    with pytest.raises(PermissionError, match="cannot write thumbnail"):
        await service.preview({"source": str(source)})
    assert list(source.parent.iterdir()) == [source]
    assert store.list_roles() == []
    monkeypatch.setattr(Image.Image, "save", original_save)
    assert (await service.preview({"source": str(source)}))["import_id"]


@pytest.mark.asyncio
async def test_preview_rejects_sources_outside_the_staging_directory(tmp_path) -> None:
    service, _store = _service(tmp_path)
    source = tmp_path / "outside.json"
    source.write_text(json.dumps(_card(), ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="受控导入目录"):
        await service.preview({"source": str(source)})


@pytest.mark.asyncio
async def test_default_desktop_bridge_service_exposes_role_card_preview(
    tmp_path,
) -> None:
    role_store = RoleStore(tmp_path)
    service = DesktopBridgeService(
        workspace=tmp_path,
        role_store=role_store,
        session_manager=SessionManager(tmp_path),
        agent_loop=create_autospec(AgentLoop, instance=True),
        event_bus=EventBus(),
    )
    source = _stage_card(tmp_path, _card())

    response = await service.handle(
        {
            "id": "role-card-preview",
            "method": "roles.cardImport.preview",
            "payload": {"source": str(source)},
        },
        emit_event=lambda _payload: None,
    )

    assert response.error is None
    assert response.payload["name"] == "小诗"
    assert response.payload["import_id"]
    await service.aclose()


@pytest.mark.asyncio
async def test_commit_keeps_png_card_as_avatar_and_imported_asset(tmp_path) -> None:
    role_store = RoleStore(tmp_path)
    service = DesktopBridgeService(
        workspace=tmp_path,
        role_store=role_store,
        session_manager=SessionManager(tmp_path),
        agent_loop=create_autospec(AgentLoop, instance=True),
        event_bus=EventBus(),
    )
    source = tmp_path / "private_runtime" / "imports" / "role-cards" / "card.png"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(_png_role_card(_card()))

    preview = await service.handle(
        {
            "id": "preview",
            "method": "roles.cardImport.preview",
            "payload": {"source": str(source)},
        },
        emit_event=lambda _payload: None,
    )
    preview_paths = [
        str(asset.get("preview_abs") or "")
        for asset in preview.payload["assets"]
        if asset.get("preview_abs")
    ]
    assert preview_paths, "expected at least one asset preview thumbnail"
    assert all(Path(path).is_file() for path in preview_paths)
    committed = await service.handle(
        {
            "id": "commit",
            "method": "roles.cardImport.commit",
            "payload": {"import_id": preview.payload["import_id"]},
        },
        emit_event=lambda _payload: None,
    )

    assert committed.error is None
    role = committed.payload["role"]
    assert role["avatar"]
    assert role["avatar_abs"]
    assert len(role["illustrations"]) == 1
    category = next(
        item for item in role["asset_categories"] if item["id"] == "imported-role-card"
    )
    assert category["name"] == "导入角色卡"
    assert role["asset_category_bindings"][role["illustrations"][0]] == category["id"]
    await service.aclose()


@pytest.mark.asyncio
async def test_native_staged_flat_source_survives_service_reinitialization(tmp_path):
    _service(tmp_path)
    staging = tmp_path / "private_runtime" / "imports" / "role-cards"
    # Native staging preserves the historical flat UUID-basename contract;
    # directories here belong to disposable preview assets, not selected files.
    source = staging / "00000000-0000-4000-8000-000000000000-character.json"
    source.write_text(json.dumps(_card(name="Persistent card")), encoding="utf-8")
    preview_assets = staging / "old-preview"
    preview_assets.mkdir()
    (preview_assets / "thumbnail.png").write_bytes(b"obsolete")
    restored, _store = _service(tmp_path)
    assert source.is_file()
    assert not preview_assets.exists()
    preview = await restored.preview({"source": str(source)})
    assert preview["name"] == "Persistent card"
