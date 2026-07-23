"""Backend-owned, role-bound primary-screen capture for role tools."""

from __future__ import annotations

import base64
import io
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from PIL import Image, ImageGrab

_USER_DATA_ENV = "MIRA_DESKTOP_USER_DATA_DIR"
_SETTINGS_FILE = "desktop-pet.json"


class DesktopScreenCapture:
    """Captures a primary display only for the desktop role bound to the pet."""

    def __init__(
        self,
        *,
        user_data_dir: Path | None = None,
        grab: Callable[[], Image.Image] | None = None,
    ) -> None:
        self._user_data_dir = user_data_dir
        self._grab = grab or (lambda: ImageGrab.grab(all_screens=False))

    def capture(self, role_id: str) -> dict[str, Any]:
        """Returns one ephemeral PNG frame after checking the persisted role binding."""

        self._require_role_binding(role_id)
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

    def _require_role_binding(self, role_id: str) -> None:
        settings_path = self._settings_path()
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ValueError("桌宠未绑定角色") from exc
        except json.JSONDecodeError as exc:
            raise ValueError("桌宠角色配置无效") from exc
        if not isinstance(settings, dict):
            raise ValueError("桌宠角色配置无效")
        if str(settings.get("roleId") or "").strip() != role_id:
            raise ValueError("当前角色不拥有屏幕观察授权")

    def _settings_path(self) -> Path:
        if self._user_data_dir is not None:
            return self._user_data_dir / _SETTINGS_FILE
        raw_path = os.environ.get(_USER_DATA_ENV, "").strip()
        if not raw_path:
            raise ValueError("桌面运行时未提供屏幕观察授权状态")
        return Path(raw_path) / _SETTINGS_FILE
