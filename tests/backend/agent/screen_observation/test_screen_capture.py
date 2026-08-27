from __future__ import annotations

import base64
from PIL import Image

from infra.screen_capture import PrimaryScreenCapture


def test_capture_returns_an_ephemeral_primary_screen_png_for_any_role() -> None:
    capture = PrimaryScreenCapture(
        grab=lambda: Image.new("RGB", (32, 18), "black"),
    )

    frame = capture.capture("mira")

    assert frame["role_id"] == "mira"
    assert frame["width"] == 32
    assert frame["height"] == 18
    assert base64.b64decode(frame["image_base64"]).startswith(b"\x89PNG\r\n\x1a\n")


def test_capture_tags_the_requested_role_without_reading_pet_settings() -> None:
    capture = PrimaryScreenCapture(
        grab=lambda: Image.new("RGB", (32, 18), "black"),
    )

    assert capture.capture("other")["role_id"] == "other"
