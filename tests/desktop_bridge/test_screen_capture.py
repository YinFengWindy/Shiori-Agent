from __future__ import annotations

import base64
import json

import pytest
from PIL import Image

from desktop_bridge.screen_capture import DesktopScreenCapture


def _write_settings(tmp_path, **overrides):
    settings = {
        "visible": True,
        "observationEnabled": True,
        "roleId": "mira",
        **overrides,
    }
    (tmp_path / "desktop-pet.json").write_text(
        json.dumps(settings), encoding="utf-8"
    )


def test_capture_returns_an_ephemeral_primary_screen_png_when_role_is_authorized(
    tmp_path,
) -> None:
    _write_settings(tmp_path)
    capture = DesktopScreenCapture(
        user_data_dir=tmp_path,
        grab=lambda: Image.new("RGB", (32, 18), "black"),
    )

    frame = capture.capture("mira")

    assert frame["role_id"] == "mira"
    assert frame["width"] == 32
    assert frame["height"] == 18
    assert base64.b64decode(frame["image_base64"]).startswith(b"\x89PNG\r\n\x1a\n")


@pytest.mark.parametrize(
    ("overrides", "role_id", "message"),
    [
        ({"observationEnabled": False}, "mira", "尚未授权"),
        ({"visible": False}, "mira", "未显示"),
        ({}, "other", "不拥有"),
    ],
)
def test_capture_fails_closed_without_the_active_role_consent(
    tmp_path,
    overrides,
    role_id,
    message,
) -> None:
    _write_settings(tmp_path, **overrides)
    capture = DesktopScreenCapture(
        user_data_dir=tmp_path,
        grab=lambda: pytest.fail("capture must not run without consent"),
    )

    with pytest.raises(ValueError, match=message):
        capture.capture(role_id)
