"""Complete official PNG images and stale QR rejection."""

from __future__ import annotations

import base64
import io

import pytest
import qrcode

from plugins.qq.backend.napcat_qrcode import NapCatQrCache


def _qr_png(value: str) -> bytes:
    output = io.BytesIO()
    qrcode.make(value).save(output)
    return output.getvalue()


def test_qr_image_uses_private_png_and_rejects_stale_refresh(tmp_path):
    qr = NapCatQrCache(lambda ref: tmp_path / ref)
    ref = "c" * 32
    image_path = tmp_path / ref / "napcat/cache/qrcode.png"
    image_path.parent.mkdir(parents=True)
    old_image = _qr_png("https://qq.example/first")
    image_path.write_bytes(old_image)
    old_uri = qr.image_uri(ref, "https://qq.example/first")
    assert old_uri.startswith("data:image/png;base64,")
    assert base64.b64decode(old_uri.partition(",")[2]) == old_image

    assert qr.image_uri(ref, "https://qq.example/second") == ""
    assert qr.image_uri(ref, "https://qq.example/second") == ""
    new_image = _qr_png("https://qq.example/second")
    image_path.write_bytes(new_image)
    new_uri = qr.image_uri(ref, "https://qq.example/second")
    assert base64.b64decode(new_uri.partition(",")[2]) == new_image

    qr.clear(ref)
    assert qr.scan_url(ref) == ""
    assert not image_path.exists()
    assert qr.image_uri(ref, "https://qq.example/third") == ""


def test_qr_image_rejects_oversized_file(tmp_path):
    qr = NapCatQrCache(lambda ref: tmp_path / ref)
    ref = "d" * 32
    image_path = tmp_path / ref / "napcat/cache/qrcode.png"
    image_path.parent.mkdir(parents=True)
    image_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * (2 * 1024 * 1024))
    with pytest.raises(ValueError, match="过大"):
        qr.image_uri(ref, "https://qq.example/oversized")


def test_qr_image_waits_for_complete_png(tmp_path):
    qr = NapCatQrCache(lambda ref: tmp_path / ref)
    ref = "e" * 32
    image_path = tmp_path / ref / "napcat/cache/qrcode.png"
    image_path.parent.mkdir(parents=True)
    full_image = _qr_png("https://qq.example/current")
    image_path.write_bytes(full_image[:-12])
    assert qr.image_uri(ref, "https://qq.example/current") == ""
    image_path.write_bytes(full_image)
    assert qr.image_uri(ref, "https://qq.example/current").startswith(
        "data:image/png;base64,"
    )
