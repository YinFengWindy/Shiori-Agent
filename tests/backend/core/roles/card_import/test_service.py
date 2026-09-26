import base64
import io
import json
import zipfile

import pytest
from PIL import Image, PngImagePlugin

from core.roles.card_import import RoleCardImportService
from core.roles.card_import.charx_adapter import adapt_charx
from core.roles.card_import.png_adapter import adapt_png


def _png(*, metadata: dict[str, str] | None = None) -> bytes:
    image = Image.new("RGBA", (8, 8), (255, 0, 0, 255))
    info = PngImagePlugin.PngInfo()
    for key, value in (metadata or {}).items():
        info.add_text(key, value)
    output = io.BytesIO()
    image.save(output, format="PNG", pnginfo=info)
    return output.getvalue()


def _card(**overrides):
    card = {
        "spec": "chara_card_v2",
        "data": {
            "name": "小诗",
            "description": "角色资料",
            "personality": "安静、细心",
            "system_prompt": "遵守边界",
            "post_history_instructions": "保持角色口吻",
            "first_mes": "你好。",
            "alternate_greetings": ["晚上好。"],
            "character_book": {
                "entries": [
                    {
                        "title": "雨天",
                        "keys": ["雨"],
                        "content": "她喜欢听雨。",
                        "constant": True,
                        "priority": 2,
                    },
                ]
            },
            "scenario": "discard me",
        },
    }
    card["data"].update(overrides)
    return card


def test_json_adapter_normalizes_profile_and_report(tmp_path):
    source = tmp_path / "card.json"
    source.write_text(json.dumps(_card(), ensure_ascii=False), encoding="utf-8")

    preview = RoleCardImportService().preview(source)

    assert preview.name == "小诗"
    assert preview.profile["character"]["behavior_rules"] == "遵守边界"
    assert preview.profile["character"]["response_constraints"] == "保持角色口吻"
    assert "greetings" not in preview.profile
    assert "knowledge_base" not in preview.profile
    assert "character_book" in preview.report.discarded_fields
    assert {"first_mes", "alternate_greetings"} <= set(preview.report.discarded_fields)
    assert "scenario" in preview.report.discarded_fields
    assert preview.provenance.card_version == "V2"


def test_json_adapter_reports_macros_and_does_not_persist_source_metadata():
    payload = _card(system_prompt="{{user}} says hello")
    preview = RoleCardImportService().preview_bytes(
        json.dumps(payload).encode(), filename="card.json"
    )

    assert "{{user}}" not in preview.report.unsupported_macros
    assert "source" not in preview.profile
    assert "creator" not in preview.profile


def test_png_prefers_ccv3_metadata(tmp_path):
    ccv3 = base64.b64encode(json.dumps(_card(name="ccv3")).encode()).decode()
    chara = base64.b64encode(json.dumps(_card(name="chara")).encode()).decode()
    source = tmp_path / "card.png"
    source.write_bytes(_png(metadata={"chara": chara, "ccv3": ccv3}))

    preview = adapt_png(source)

    assert preview.name == "ccv3"
    assert preview.assets[0].kind == "avatar"
    assert preview.assets[0].data


def test_preview_bytes_supports_png_and_charx(tmp_path):
    png = _png(
        metadata={"chara": base64.b64encode(json.dumps(_card()).encode()).decode()}
    )
    service = RoleCardImportService()
    assert service.preview_bytes(png, filename="card.png").name == "小诗"

    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as writer:
        writer.writestr("card.json", json.dumps(_card()))
    assert (
        service.preview_bytes(archive.getvalue(), filename="card.charx").name == "小诗"
    )


def test_charx_requires_root_card_json_and_maps_images(tmp_path):
    source = tmp_path / "card.charx"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr(
            "card.json",
            json.dumps(
                _card(
                    assets=[
                        {
                            "type": "icon",
                            "name": "main",
                            "uri": "embeded://icon/main.png",
                            "ext": "png",
                        },
                        {
                            "type": "background",
                            "name": "main",
                            "uri": "embeded://background/main.png",
                            "ext": "png",
                        },
                    ]
                )
            ),
        )
        archive.writestr("icon/main.png", _png())
        archive.writestr("background/main.png", _png())

    preview = adapt_charx(source)

    assert preview.provenance.format == "charx"
    assert {asset.kind for asset in preview.assets} >= {"avatar", "background"}
    assert all(asset.data for asset in preview.assets)


def test_charx_rejects_traversal_and_encrypted_archive(tmp_path):
    traversal = tmp_path / "traversal.charx"
    with zipfile.ZipFile(traversal, "w") as archive:
        archive.writestr("../card.json", "{}")
    with pytest.raises(ValueError, match="路径不安全"):
        adapt_charx(traversal)

    missing = tmp_path / "missing.charx"
    with zipfile.ZipFile(missing, "w") as archive:
        archive.writestr("nested/card.json", "{}")
    with pytest.raises(ValueError, match="根目录缺少 card.json"):
        adapt_charx(missing)


def test_preview_has_no_filesystem_side_effect(tmp_path):
    source = tmp_path / "card.json"
    source.write_text(json.dumps(_card()), encoding="utf-8")
    before = set(tmp_path.iterdir())

    RoleCardImportService().preview(source)

    assert set(tmp_path.iterdir()) == before
