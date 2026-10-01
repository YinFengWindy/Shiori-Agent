import io
import json
import zipfile

from PIL import Image

from core.roles.card_import.charx_adapter import adapt_charx_bytes


def test_archive_loads_only_declared_supported_images_and_reports_missing_or_invalid_bytes():
    image = io.BytesIO()
    Image.new("RGB", (8, 8)).save(image, format="PNG")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "card.json",
            json.dumps(
                {
                    "data": {
                        "name": "Test",
                        "assets": [
                            {
                                "type": "icon",
                                "name": "main",
                                "uri": "embeded://random.png",
                                "ext": "png",
                            },
                            {
                                "type": "emotion",
                                "name": "neutral",
                                "uri": "embeded://missing.png",
                                "ext": "png",
                            },
                            {
                                "type": "emotion",
                                "name": "sad",
                                "uri": "embeded://invalid.png",
                                "ext": "png",
                            },
                        ],
                    }
                }
            ),
        )
        archive.writestr("random.png", image.getvalue())
        archive.writestr("avatar/main.png", image.getvalue())
        archive.writestr("invalid.png", "not an image")
    preview = adapt_charx_bytes(buffer.getvalue())
    assert len(preview.assets) == 1
    assert preview.assets[0].kind == "avatar"
    assert preview.assets[0].path == "random.png"
    assert preview.assets[0].asset_id == "asset-0"
    assert set(preview.report.unsupported_resources) == {"missing.png", "invalid.png"}


def test_archive_reports_entry_count_instead_of_size():
    import pytest
    from core.roles.card_import.safety import MAX_ARCHIVE_MEMBERS

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for index in range(MAX_ARCHIVE_MEMBERS + 1):
            archive.writestr(f"{index}.txt", "")
    with pytest.raises(
        ValueError, match=f"条目过多（最多 {MAX_ARCHIVE_MEMBERS} 个条目）"
    ):
        adapt_charx_bytes(output.getvalue())


def test_archive_missing_metadata_is_not_reported_as_corruption():
    import pytest

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("nested/card.json", "{}")
    with pytest.raises(ValueError, match="缺少角色信息文件"):
        adapt_charx_bytes(output.getvalue())


def test_archive_size_messages_name_the_limit_that_failed(monkeypatch):
    import pytest
    from core.roles.card_import import charx_adapter

    one_mib = 1024 * 1024
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("card.json", "x" * (one_mib + 1))
    monkeypatch.setattr(charx_adapter, "MAX_MEMBER_BYTES", one_mib)
    with pytest.raises(ValueError, match="单条目.*1 MiB"):
        adapt_charx_bytes(output.getvalue())
    monkeypatch.setattr(charx_adapter, "MAX_MEMBER_BYTES", 2 * one_mib)
    monkeypatch.setattr(charx_adapter, "MAX_ARCHIVE_BYTES", one_mib)
    with pytest.raises(ValueError, match="解压总大小.*1 MiB"):
        adapt_charx_bytes(output.getvalue())
    monkeypatch.setattr(charx_adapter, "MAX_SOURCE_BYTES", one_mib)
    with pytest.raises(ValueError, match="源文件.*1 MiB"):
        adapt_charx_bytes(b"x" * (one_mib + 1))
