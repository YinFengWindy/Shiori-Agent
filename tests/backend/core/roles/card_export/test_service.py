import base64
import io
import json
import zipfile

import pytest
from PIL import Image, PngImagePlugin

from core.roles import RoleStore
from core.roles.card_export import export_role_card
from core.roles.card_export import service as export_module
from core.roles.card_import import RoleCardImportService


@pytest.fixture
def role_data(tmp_path):
    store = RoleStore(tmp_path)
    role = store.create_role(
        role_id="export-me",
        name="小诗",
        description="卡片上的简介",
        system_prompt="Legacy prompt should not leak",
        profile={
            "character": {
                "profile": "独立的角色资料",
                "personality": "安静",
                "behavior_rules": "诚实",
                "response_constraints": "简洁",
                "nickname": "诗诗",
            }
        },
        runtime_config={"credentials": "DO-NOT-EXPORT", "plugin_state": "PRIVATE"},
    )
    return role, store


def add_image(tmp_path, store, role, name="portrait.png", color="red"):
    source = tmp_path / name
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("chara", "PRIVATE-OLD-CARD")
    Image.new("RGB", (12, 16), color).save(source, pnginfo=metadata)
    return store.import_asset(role.id, source, prefix="illustration")


@pytest.mark.parametrize("format_name", ["charx", "png", "json"])
def test_three_formats_roundtrip_independent_fields_without_private_state(
    role_data, format_name
):
    role, store = role_data
    original = role.to_dict()
    data, shown = export_role_card(role, store, format_name)
    imported = RoleCardImportService().preview_bytes(
        data, filename=f"share.{format_name}"
    )
    assert imported.name == shown["name"] == role.name
    assert imported.description == shown["description"] == role.description
    assert (
        imported.profile["character"]
        == shown["character"]
        == role.profile.character.to_dict()
    )
    assert not imported.report.unsupported_rules
    assert role.to_dict() == original
    if format_name == "charx":
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            card = json.loads(archive.read("card.json"))
    elif format_name == "png":
        with Image.open(io.BytesIO(data)) as image:
            card = json.loads(base64.b64decode(image.info["ccv3"]))
    else:
        card = json.loads(data)
    portable = json.dumps(card)
    for private in (
        "DO-NOT-EXPORT",
        "PRIVATE",
        "runtime_config",
        "memory_init_state",
        "plugin_state",
        "created_at",
        "Legacy prompt should not leak",
    ):
        assert private not in portable
    assert set(card["data"]["extensions"]) == {"shiori"}
    if format_name == "json":
        assert card["spec"] == "chara_card_v3"
        assert card["spec_version"] == "3.0"
        assert card["data"]["assets"] == []
        assert card["data"]["group_only_greetings"] == []
        assert shown["assets"] == []


def test_charx_deduplicates_images_but_preserves_all_semantic_uses(role_data, tmp_path):
    role, store = role_data
    avatar = add_image(tmp_path, store, role)
    background = add_image(tmp_path, store, role, "background.png", "blue")
    role.avatar = avatar
    role.chat_background = background
    role.illustrations = [avatar, background, avatar]
    role.runtime_config["mood_illustration_bindings"] = {
        "neutral": avatar,
        "happy": avatar,
    }
    data, shown = export_role_card(role, store, "charx")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        assert len(archive.namelist()) == 3
        card = json.loads(archive.read("card.json"))
        for asset in card["data"]["assets"]:
            path = asset["uri"].removeprefix("embeded://")
            assert path.isascii()
            with Image.open(io.BytesIO(archive.read(path))) as image:
                assert "chara" not in image.info
    imported = RoleCardImportService().preview_bytes(data, filename="share.charx")
    assert {(asset.kind, asset.name) for asset in imported.assets} == {
        ("avatar", "main"),
        ("background", "main"),
        ("emotion", "neutral"),
        ("emotion", "happy"),
    }
    assert len(shown["assets"]) == 2
    assert not imported.report.unsupported_resources


@pytest.mark.parametrize("cover", ["avatar", "mood", "background", "empty"])
def test_png_uses_the_actual_selected_cover_and_only_one_image(
    role_data, tmp_path, cover
):
    role, store = role_data
    red = add_image(tmp_path, store, role)
    blue = add_image(tmp_path, store, role, "background.png", "blue")
    if cover != "empty":
        role.chat_background = blue
    if cover in {"avatar", "mood"}:
        role.illustrations = [red]
        role.runtime_config.update(
            default_mood="happy", mood_illustration_bindings={"happy": red}
        )
    if cover == "avatar":
        role.avatar = blue
    data, shown = export_role_card(role, store, "png")
    imported = RoleCardImportService().preview_bytes(data, filename="share.png")
    assert len(imported.assets) == len(shown["assets"]) == 1
    thumbnail = base64.b64decode(shown["assets"][0]["preview_url"].split(",")[1])
    with (
        Image.open(io.BytesIO(data)) as image,
        Image.open(io.BytesIO(thumbnail)) as preview,
    ):
        assert image.convert("RGB").getpixel((0, 0)) == preview.convert("RGB").getpixel(
            (0, 0)
        )
        if cover != "empty":
            assert image.convert("RGB").getpixel((0, 0)) == (
                (255, 0, 0) if cover == "mood" else (0, 0, 255)
            )
        card = json.loads(base64.b64decode(image.info["ccv3"]))
        assert card["data"]["assets"][0]["uri"] == "ccdefault:"


def test_charx_keeps_non_png_formats_and_animation(role_data, tmp_path):
    role, store = role_data
    frames = [Image.new("RGB", (10, 10), color) for color in ("red", "blue")]
    source = tmp_path / "animation.gif"
    frames[0].save(
        source,
        save_all=True,
        append_images=frames[1:],
        duration=[100, 200],
        loop=0,
        comment=b"PRIVATE",
    )
    gif = store.import_asset(role.id, source, prefix="illustration")
    source = tmp_path / "photo.jpg"
    frames[0].save(source)
    jpg = store.import_asset(role.id, source, prefix="illustration")
    role.illustrations = [gif, jpg]
    data, _ = export_role_card(role, store, "charx")
    imported = RoleCardImportService().preview_bytes(data, filename="share.charx")
    assert {asset.media_type for asset in imported.assets} == {
        "image/gif",
        "image/jpeg",
    }
    for asset in imported.assets:
        with Image.open(io.BytesIO(asset.data)) as image:
            assert "comment" not in image.info
            if asset.media_type == "image/gif":
                assert image.n_frames == 2
                image.seek(1)
                assert image.convert("RGB").getpixel((0, 0)) == (0, 0, 255)
                assert image.info["duration"] == 200


def test_invalid_or_foreign_images_fail_but_text_export_remains_available(
    role_data, tmp_path
):
    role, store = role_data
    other = store.create_role(role_id="other", name="Other", system_prompt="Rules")
    role.avatar = add_image(tmp_path, store, other)
    with pytest.raises(ValueError, match="不属于"):
        export_role_card(role, store, "png")
    role.avatar = "assets/export-me/missing.png"
    with pytest.raises(ValueError, match="缺失"):
        export_role_card(role, store, "charx")
    assert export_role_card(role, store, "json")[1]["assets"] == []


def test_final_output_obeys_import_size_limits(role_data, monkeypatch):
    role, store = role_data
    monkeypatch.setattr(export_module, "MAX_SOURCE_BYTES", 16)
    with pytest.raises(ValueError, match="大小限制"):
        export_role_card(role, store, "json")
