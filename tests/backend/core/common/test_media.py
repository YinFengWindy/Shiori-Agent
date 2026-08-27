from __future__ import annotations

import pytest

from core.common.media import detect_image_mime_from_header


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        (b"\x89PNG\r\n\x1a\nrest", "image/png"),
        (b"\xff\xd8\xffrest", "image/jpeg"),
        (b"GIF87arest", "image/gif"),
        (b"GIF89arest", "image/gif"),
        (b"BMrest", "image/bmp"),
        (b"RIFF1234WEBPrest", "image/webp"),
        (b"not-an-image", None),
    ],
)
def test_detect_image_mime_from_header(header: bytes, expected: str | None) -> None:
    assert detect_image_mime_from_header(header) == expected
