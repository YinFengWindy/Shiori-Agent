"""Host-owned primary-screen capture for role tools."""

from __future__ import annotations

import base64
import io
from datetime import UTC, datetime
from typing import Any, Callable
from uuid import uuid4

from PIL import Image, ImageGrab

class PrimaryScreenCapture:
    """Captures one primary display without coupling capture to a desktop pet."""

    def __init__(
        self,
        *,
        grab: Callable[[], Image.Image] | None = None,
    ) -> None:
        self._grab = grab or (lambda: ImageGrab.grab(all_screens=False))

    def capture(self, role_id: str) -> dict[str, Any]:
        """Returns one ephemeral PNG frame tagged with the active role context."""

        image = self._grab()
        if image.width <= 0 or image.height <= 0:
            raise RuntimeError("主屏幕捕获返回空帧")
        buffer = io.BytesIO()
        image.convert("RGB").save(buffer, format="PNG", optimize=True)
        return {
            "role_id": role_id,
            "frame_id": str(uuid4()),
            "captured_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "width": image.width,
            "height": image.height,
            "scale_factor": 1.0,
            "image_base64": base64.b64encode(buffer.getvalue()).decode("ascii"),
        }
