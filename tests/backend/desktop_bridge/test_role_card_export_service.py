import base64
import json

import pytest
from PIL import Image

from core.roles import RoleAggregateService, RoleStore
from desktop_bridge.role_card_export_service import DesktopRoleCardExportService
from desktop_bridge.role_card_import_service import DesktopRoleCardImportService
from session.manager import SessionManager


@pytest.mark.asyncio
async def test_snapshot_reads_original_bytes_after_role_edits_and_can_be_released(
    tmp_path,
):
    store = RoleStore(tmp_path)
    role = store.create_role(name="原角色", description="简介", system_prompt="规则")
    service = DesktopRoleCardExportService(store)
    preview = await service.preview({"role_id": role.id, "format": "json"})
    store.update_role(role.id, name="后来的名字")
    first = await service.read({"export_id": preview["export_id"]})
    assert (
        json.loads(base64.b64decode(first["data_base64"]))["data"]["name"]
        == preview["name"]
        == "原角色"
    )
    assert await service.read({"export_id": preview["export_id"]}) == first
    await service.release({"export_id": preview["export_id"]})
    with pytest.raises(ValueError, match="失效"):
        await service.read({"export_id": preview["export_id"]})
    assert store.get_role(role.id).name == "后来的名字"


@pytest.mark.asyncio
async def test_charx_export_reimports_fields_images_and_mood_bindings(tmp_path):
    store = RoleStore(tmp_path)
    image = tmp_path / "image.png"
    Image.new("RGB", (8, 10), "red").save(image)
    character = {
        "profile": "资料",
        "personality": "性格",
        "behavior_rules": "规则",
        "response_constraints": "约束",
        "nickname": "昵称",
    }
    role = store.create_role(
        name="分享角色",
        description="简介",
        system_prompt="规则",
        profile={"character": character},
        avatar_source=image,
        illustration_sources=[image],
    )
    role = store.update_role(
        role.id,
        chat_background=role.illustrations[0],
        runtime_config={
            "mood_illustration_bindings": {"neutral": role.illustrations[0]}
        },
    )
    original = role.to_dict()
    exporter = DesktopRoleCardExportService(store)
    preview = await exporter.preview({"role_id": role.id, "format": "charx"})
    exported = await exporter.read({"export_id": preview["export_id"]})
    importer = DesktopRoleCardImportService(
        workspace=tmp_path,
        role_store=store,
        role_service=RoleAggregateService.from_runtime(
            workspace=tmp_path,
            role_store=store,
            session_manager=SessionManager(tmp_path),
        ),
    )
    path = tmp_path / "private_runtime/imports/role-cards/shared.charx"
    path.write_bytes(base64.b64decode(exported["data_base64"]))
    imported = await importer.preview({"source": str(path)})
    result = await importer.commit({"import_id": imported["import_id"]})
    restored = store.get_role(result["role"]["id"])
    assert restored.profile.character.to_dict() == character
    assert restored.description == role.description
    assert restored.avatar and restored.chat_background
    assert (
        restored.runtime_config["mood_illustration_bindings"]["neutral"]
        in restored.illustrations
    )
    assert store.get_role(role.id).to_dict() == original


@pytest.mark.asyncio
async def test_invalid_targets_formats_and_old_snapshot_eviction(tmp_path):
    store = RoleStore(tmp_path)
    role = store.create_role(name="角色", system_prompt="规则")
    service = DesktopRoleCardExportService(store)
    with pytest.raises(ValueError, match="不存在"):
        await service.preview({"role_id": "missing", "format": "json"})
    with pytest.raises(ValueError, match="格式"):
        await service.preview({"role_id": role.id, "format": "exe"})
    first = await service.preview({"role_id": role.id, "format": "json"})
    for _ in range(4):
        await service.preview({"role_id": role.id, "format": "json"})
    with pytest.raises(ValueError, match="失效"):
        await service.read({"export_id": first["export_id"]})
