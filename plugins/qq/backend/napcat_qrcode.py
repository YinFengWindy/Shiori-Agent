"""Fresh, bounded QR images from an account's official NapCat cache."""

from __future__ import annotations

import base64
import hashlib
from pathlib import Path
from typing import Callable

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_PNG_END = b"\x00\x00\x00\x00IEND\xaeB`\x82"
_MAX_QR_BYTES = 2 * 1024 * 1024


class NapCatQrCache:
    """Exposes only complete PNGs matching this account's current scan URL."""

    def __init__(self, account_dir: Callable[[str], Path]) -> None:
        self._account_dir = account_dir
        self._urls: dict[str, str] = {}
        self._digests: dict[str, str] = {}
        self._image_urls: dict[str, str] = {}

    def _path(self, ref: str) -> Path:
        return self._account_dir(ref) / "napcat" / "cache" / "qrcode.png"

    def _image(self, ref: str) -> bytes:
        path = self._path(ref)
        if not path.is_file() or not path.resolve().is_relative_to(
            self._account_dir(ref).resolve()
        ):
            return b""
        with path.open("rb") as source:
            image = source.read(_MAX_QR_BYTES + 1)
        if len(image) > _MAX_QR_BYTES:
            raise ValueError("NapCat 登录二维码图片过大")
        return (
            image
            if image.startswith(_PNG_SIGNATURE) and image.endswith(_PNG_END)
            else b""
        )

    def clear(self, ref: str) -> None:
        """Prevents a prior session's QR image from appearing after a restart."""
        self._urls.pop(ref, None)
        self._digests.pop(ref, None)
        self._image_urls.pop(ref, None)
        self._path(ref).unlink(missing_ok=True)

    def scan_url(self, ref: str) -> str:
        """Returns the latest scan URL observed for this account."""
        return self._urls.get(ref, "")

    def digest(self, ref: str) -> str:
        """Returns the current complete PNG digest before a refresh starts."""
        image = self._image(ref)
        return hashlib.sha256(image).hexdigest() if image else ""

    def image_uri(self, ref: str, scan_url: str, *, reject_digest: str = "") -> str:
        """Returns this account's fresh official PNG as a data URI."""
        if not scan_url:
            return ""
        self._urls[ref] = scan_url
        image = self._image(ref)
        if not image:
            return ""
        digest = hashlib.sha256(image).hexdigest()
        if digest == reject_digest or (
            self._image_urls.get(ref) != scan_url and digest == self._digests.get(ref)
        ):
            return ""
        self._digests[ref] = digest
        self._image_urls[ref] = scan_url
        return "data:image/png;base64," + base64.b64encode(image).decode("ascii")
